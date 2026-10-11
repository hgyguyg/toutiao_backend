from typing import Any

from cache.base_cache import get_cache_data, set_cache_data, delete_cache_data_by_prefix

HISTORY_LIST_PREFIX = "history:list"

#浏览历史写入频繁（每次浏览都会新增），缓存时间要短，避免用户看到过期记录
HISTORY_LIST_EXPIRE = 300

def build_history_list_key(user_id: int,page: int,page_size: int) -> str:
    return f"{HISTORY_LIST_PREFIX}:{user_id}:{page}:{page_size}"

async def get_cached_history_list(user_id: int,page: int,page_size: int):
    return await get_cache_data(build_history_list_key(user_id,page,page_size))

async def set_cached_history_list(data: Any,user_id: int,page: int,page_size: int,expire: int = HISTORY_LIST_EXPIRE):
    return await set_cache_data(build_history_list_key(user_id,page,page_size),data,expire)

async def clear_cached_history_list(user_id: int):
    #新增/删除/清空浏览记录后按用户前缀批量失效
    await delete_cache_data_by_prefix(f"{HISTORY_LIST_PREFIX}:{user_id}:")
    return True