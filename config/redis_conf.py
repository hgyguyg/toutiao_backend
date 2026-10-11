import json
from typing import Any

import redis.asyncio as redis

REDIS_HOST = "localhost"
REDIS_PORT = 6379

#按前缀批量删除时每批游标扫描的键数量
SCAN_COUNT = 200

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=0,
    decode_responses=True
)

async def get_cache(key: str):
    try:
        return await redis_client.get(key)
    except Exception as e:
        print(f"读取缓存失败：{e}")
        return None

async def get_json_cache(key: str):
    try:
        data = await redis_client.get(key)
        if data:
            return json.loads(data)
        return None
    except Exception as e:
        print(f"读取缓存失败：{e}")
        return None

async def set_cache(key: str,value: Any,expire: int):
    try:
        if isinstance(value,(list,dict)):
            value = json.dumps(value,ensure_ascii=False)
        await redis_client.setex(key,expire,value)
        return True
    except Exception as e:
        print(f"写入缓存失败：{e}")
        return False

async def delete_cache(key: str):
    #删除单个缓存键，缓存失效时调用
    try:
        await redis_client.delete(key)
        return True
    except Exception as e:
        print(f"删除缓存失败：{e}")
        return False

async def delete_cache_by_prefix(prefix: str):
    #按前缀批量删除，用scan 分批游标遍历，避免 keys 命令阻塞redis
    try:
        deleted = 0
        async for key in redis_client.scan_iter(match=f"{prefix}*",count=SCAN_COUNT):
            await redis_client.delete(key)
            deleted += 1
        return deleted
    except Exception as e:
        print(f"按前缀删除缓存失败：{e}")
        return 0

async def get_cache_ttl(key: str):
    #获取剩余过期时间，更新缓存内容时用于保持原有生命周期，避免热点数据永不过期
    try:
        return await redis_client.ttl(key)
    except Exception as e:
        print(f"获取缓存过期时间失败：{e}")
        return None

async def set_cache_lock(key: str,value: str,expire: int):
    #尝试获取互斥锁，set的 nx 参数保证同一时刻只有一个请求能拿到锁
    try:
        return bool(await redis_client.set(key,value,nx=True,ex=expire))
    except Exception as e:
        print(f"获取缓存锁失败：{e}")
        return False

async def release_cache_lock(key: str,value: str):
    #释放互斥锁，校验value 避免误删其他请求持有的锁
    try:
        if await redis_client.get(key) == value:
            await redis_client.delete(key)
        return True
    except Exception as e:
        print(f"释放缓存锁失败：{e}")
        return False