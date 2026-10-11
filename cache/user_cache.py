from typing import Optional, Any

from cache.base_cache import get_cache_data, set_cache_data, delete_cache_data, \
    delete_cache_data_by_prefix

USER_INFO_PREFIX = "user:info"
USER_TOKEN_PREFIX = "user:token"

#用户信息缓存时间较短，改资料/改密码后能较快生效
USER_INFO_EXPIRE = 600
#令牌对应用户的缓存时间与令牌有效期(7天)保持一致由业务侧控制，这里取较短值便于及时失效
USER_TOKEN_EXPIRE = 1800

def build_user_info_key(user_id: int) -> str:
    return f"{USER_INFO_PREFIX}:{user_id}"

def build_user_token_key(token: str) -> str:
    return f"{USER_TOKEN_PREFIX}:{token}"

async def get_cached_user_info(user_id: int):
    return await get_cache_data(build_user_info_key(user_id))

async def set_cached_user_info(user: Any,user_id: int,expire: int = USER_INFO_EXPIRE):
    return await set_cache_data(build_user_info_key(user_id),user,expire)

async def get_cached_user_by_token(token: str):
    return await get_cache_data(build_user_token_key(token))

async def set_cached_user_by_token(user: Any,token: str,expire: int = USER_TOKEN_EXPIRE):
    return await set_cache_data(build_user_token_key(token),user,expire)

async def delete_cached_user_info(user_id: int):
    #用户资料或密码变更后失效用户维度缓存
    return await delete_cache_data(build_user_info_key(user_id))

async def delete_cached_user_by_token(token: str):
    return await delete_cache_data(build_user_token_key(token))

async def clear_cached_user(user_id: int):
    #用户相关数据变更后调用，同时清空该用户的资料缓存与全部令牌缓存
    await delete_cache_data(build_user_info_key(user_id))
    await delete_cache_data_by_prefix(f"{USER_TOKEN_PREFIX}:")
    return True