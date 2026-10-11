from typing import Any

from cache.base_cache import get_cache_data, set_cache_data, delete_cache_data_by_prefix

FAVORITE_LIST_PREFIX = "favorite:list"

#收藏列表按用户维度缓存，用户操作不频繁，缓存时间可适当延长
FAVORITE_LIST_EXPIRE = 600

def build_favorite_list_key(user_id: int,page: int,page_size: int) -> str:
    return f"{FAVORITE_LIST_PREFIX}:{user_id}:{page}:{page_size}"

async def get_cached_favorite_list(user_id: int,page: int,page_size: int):
    return await get_cache_data(build_favorite_list_key(user_id,page,page_size))

async def set_cached_favorite_list(data: Any,user_id: int,page: int,page_size: int,expire: int = FAVORITE_LIST_EXPIRE):
    return await set_cache_data(build_favorite_list_key(user_id,page,page_size),data,expire)

async def clear_cached_favorite_list(user_id: int):
    #分页key 无法逐个枚举，新增/取消/清空收藏后按用户前缀批量失效
    await delete_cache_data_by_prefix(f"{FAVORITE_LIST_PREFIX}:{user_id}:")
    return True