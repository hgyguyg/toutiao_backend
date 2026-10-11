import uuid
from datetime import timedelta, datetime

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from schemas.users import UserRequest, UserUpdateRequest
from models.users import User,UserToken
from utils.security import get_hash_password, verify_password

from cache import user_cache
from cache.base_cache import get_or_set_cache_data, restore_model

async def get_usr_by_username(
        db: AsyncSession,
        username:str
):
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()

async def create_user(
        db: AsyncSession,
        userdata: UserRequest
):
    hashed_password = get_hash_password(userdata.password)
    user = User(username=userdata.username, password=hashed_password)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    #新用户入库后清理用户维度缓存，避免命中旧的空值缓存
    await user_cache.clear_cached_user(user.id)

    return user

async def create_token(
        db: AsyncSession,
        user_id: int
):
    token = str(uuid.uuid4())
    expires_at = datetime.now() + timedelta(days=7)
    result = await db.execute(select(UserToken).where(UserToken.user_id == user_id))
    result = result.scalar_one_or_none()
    user_token = UserToken(user_id=user_id, token=token, expires_at=expires_at)
    if result is None:
        db.add(user_token)
    else:
        result.token = token
        result.expires_at = expires_at

    await db.commit()
    #旧令牌已失效，清空令牌缓存避免旧令牌继续命中缓存
    await user_cache.clear_cached_user(user_id)

    return token

async def authenticate_user(
        db:AsyncSession,
        username:str,
        password:str
):
    user = await get_usr_by_username(db,username)
    if not user:
        return None
    if not verify_password(password,user.password):
        return None
    return user

async def get_user_by_token(
        db: AsyncSession,
        token: str
):
    """
    令牌鉴权是每个需登录接口都会走的热点路径，这里走缓存
    注意：令牌本身过期时间在UserToken.expires_at 判断，缓存过期时间不能长于令牌有效期
    """
    cache_key = user_cache.build_user_token_key(token)

    async def load_user_by_token():
        result = await db.execute(select(UserToken).where(UserToken.token == token))
        result = result.scalar_one_or_none()

        if not result or result.expires_at < datetime.now():
            return None

        result = await db.execute(select(User).where(User.id == result.user_id))
        return result.scalar_one_or_none()

    #令牌无效时缓存空值，挡住恶意携带随机令牌的穿透攻击
    data = await get_or_set_cache_data(cache_key,load_user_by_token,user_cache.USER_TOKEN_EXPIRE)
    #鉴权结果需要属性访问，命中缓存时还原成ORM 对象
    return restore_model(data,User)

async def update_user(
        db: AsyncSession,
        username: str,
        user_data: UserUpdateRequest
):
    user = await get_usr_by_username(db, username)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    await db.execute(update(User).where(User.username == username).values(**user_data.model_dump(
        exclude_unset = True,
        exclude_none=True
    )))
    await db.commit()
    await db.refresh(user)
    #资料变更后清空该用户的资料与令牌缓存，下次请求回源拿最新数据
    await user_cache.clear_cached_user(user.id)
    return user

async def change_password(
        db: AsyncSession,
        user: User,
        old_password: str,
        new_password: str
):
    if not verify_password(old_password, user.password):
        raise HTTPException(status_code=400, detail="旧密码错误")
    user.password = get_hash_password(new_password)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    #密码变更必须清空缓存，否则旧密码仍可能被缓存命中导致鉴权不一致
    await user_cache.clear_cached_user(user.id)
    return True