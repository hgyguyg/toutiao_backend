import asyncio
import json
import random
import uuid
from typing import Any, Callable, Awaitable

from fastapi.encoders import jsonable_encoder

from config.redis_conf import get_json_cache, set_cache, delete_cache, delete_cache_by_prefix, \
    set_cache_lock, release_cache_lock

DEFAULT_EXPIRE = 3600
#空值缓存的过期时间要短，避免数据补上后仍长时间查不到
EMPTY_EXPIRE = 60
#互斥锁的持有时间，防止持锁进程崩溃后死锁
LOCK_EXPIRE = 5
#未抢到锁时的重试次数与间隔，总等待时间要明显小于锁持有时间
LOCK_WAIT_RETRY = 3
LOCK_WAIT_INTERVAL = 0.05
#随机偏移上限，用于打散集中过期造成的雪崩
TTL_JITTER_RATIO = 0.2
#空值占位符，redis 中不存在null，用该常量区分"查过但为空"
#必须是 dict，否则 set_cache 不会做 json 序列化，读回时 json.loads 会失败导致占位符失效
#用 list/none 区分空结果的原始形态，保证命中缓存与回源数据库的返回值完全一致
EMPTY_LIST_MARKER = {"__empty__": "list"}
EMPTY_NONE_MARKER = {"__empty__": "none"}

def build_lock_key(key: str) -> str:
    return f"lock:{key}"

def decode_empty_marker(cached: Any) -> Any:
    #命中空值占位符时还原成查询数据库时的原始返回形态，保证接口行为一致
    if cached == EMPTY_NONE_MARKER:
        return None
    if cached == EMPTY_LIST_MARKER:
        return []
    return cached

def is_empty_result(data: Any) -> bool:
    """
    判断是否为"查不到数据"：None、空列表、空字典都算空，
    整型 0 不是空（新闻总数为 0 是有效结果），因此不参与判断
    """
    if data is None:
        return True
    if isinstance(data,(list,tuple,dict,set,str)) and len(data) == 0:
        return True
    return False

def jitter_expire(expire: int) -> int:
    #在基础过期时间上叠加随机偏移，避免大量key 同一时刻集中失效
    offset = int(expire * TTL_JITTER_RATIO)
    return expire + random.randint(0,offset) if offset > 0 else expire

async def get_cache_data(key: str) -> Any:
    #查询缓存，缓存不存在或读取异常时统一返回 None，由调用方回源数据库
    return await get_json_cache(key)

async def set_cache_data(key: str,data: Any,expire: int = DEFAULT_EXPIRE) -> bool:
    """
    设置缓存，写入前统一转换为可 json 化格式，失败返回 False，不影响主流程
    这里先自己 json.dumps 成字符串再交给底层：底层只对 list/dict 做序列化，
    整型等标量会被原样写入，读回时 json.loads 直接报错
    """
    try:
        value = json.dumps(jsonable_encoder(data),ensure_ascii=False)
    except Exception as e:
        print(f"缓存数据序列化失败：{e}")
        return False
    return await set_cache(key,value,expire)

async def delete_cache_data(key: str) -> bool:
    #删除单个缓存键，数据变更后触发失效
    return await delete_cache(key)

async def delete_cache_data_by_prefix(prefix: str) -> int:
    #按前缀批量删除缓存键，用于分页列表等无法枚举的场景
    return await delete_cache_by_prefix(prefix)

def restore_model(data: Any,model_cls: Any) -> Any:
    """
    缓存里存的是json 化后的字典，而路由层依赖ORM 对象的属性访问，
    命中缓存时用该函数还原成ORM 实例，保证接口行为与走数据库时完全一致
    """
    if data is None:
        return None
    if isinstance(data, model_cls):
        return data
    if not isinstance(data, dict):
        return data
    #只取模型真实存在的字段，避免缓存里多出 created_at 之外的冗余键导致赋值报错
    valid_fields = {c.name for c in model_cls.__table__.columns}
    return model_cls(**{k:v for k,v in data.items() if k in valid_fields})

async def get_or_set_cache_data(
        key: str,
        loader: Callable[[], Awaitable[Any]],
        expire: int = DEFAULT_EXPIRE,
        cache_empty: bool = True
    ) -> Any:
    """
    统一的缓存读写入口，缓存穿透/击穿/雪崩都在这里处理：
    1. 先读缓存，未命中则查数据库并回填（cache-aside）
    2. 查不到数据时写入空值占位，防止不存在的 key 反复打到数据库（穿透）
    3. 回填时使用互斥锁，保证热点 key 失效瞬间只有一个请求重建缓存（击穿）
    4. 过期时间叠加随机偏移，打散集中失效（雪崩）
    """
    cached = await get_cache_data(key)
    if cached is not None:
        return decode_empty_marker(cached)

    lock_key = build_lock_key(key)
    lock_value = str(uuid.uuid4())

    #抢锁重建缓存，未抢到说明已有同key 请求在重建
    if await set_cache_lock(lock_key,lock_value,LOCK_EXPIRE):
        try:
            #拿到锁后二次检查，避免等待期间其它请求已经重建好缓存
            cached = await get_cache_data(key)
            if cached is not None:
                return decode_empty_marker(cached)

            data = await loader()

            if is_empty_result(data):
                #空结果写入短 TTL 占位挡住穿透，占位符要能还原成原始空值形态
                if cache_empty:
                    marker = EMPTY_NONE_MARKER if data is None else EMPTY_LIST_MARKER
                    await set_cache_data(key,marker,EMPTY_EXPIRE)
            else:
                await set_cache_data(key,data,jitter_expire(expire))

            return data
        finally:
            await release_cache_lock(lock_key,lock_value)

    #没抢到锁：短暂等待后重试读缓存，命中则直接复用，避免大量请求同时压向数据库
    for _ in range(LOCK_WAIT_RETRY):
        await asyncio.sleep(LOCK_WAIT_INTERVAL)
        cached = await get_cache_data(key)
        if cached is not None:
            return decode_empty_marker(cached)

    #等待后仍未拿到缓存（重建方异常或已超时），放行回源，保证功能可用
    return await loader()