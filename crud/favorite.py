from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from models.favorite import Favorite
from sqlalchemy import select, delete, func

from models.news import News
from models.users import User

from cache import favorite_cache
from cache.base_cache import get_or_set_cache_data, restore_model

async def check_favorite(
        news_id: int,
        user_id: int,
        db: AsyncSession
):
    result = await db.execute(select(Favorite).where(Favorite.user_id == user_id,Favorite.news_id == news_id))
    return result.scalar_one_or_none() is not None

async def add_favorite(
        news_id: int,
        user_id: int,
        db: AsyncSession
):
    db_favorite = Favorite(news_id=news_id, user_id=user_id)
    db.add(db_favorite)
    await db.commit()
    await db.refresh(db_favorite)
    #新增收藏后该用户的收藏列表缓存失效
    await favorite_cache.clear_cached_favorite_list(user_id)
    return db_favorite

async def remove_favorite(
        news_id: int,
        user_id: int,
        db: AsyncSession
):
    result = await db.execute(delete(Favorite).where(Favorite.user_id == user_id,Favorite.news_id == news_id))
    await db.commit()
    #取消收藏后该用户的收藏列表缓存失效
    await favorite_cache.clear_cached_favorite_list(user_id)
    return result.rowcount > 0

async def get_favorite_list(
        db: AsyncSession,
        user_id: int,
        page: int,
        page_size: int
):
    cache_key = favorite_cache.build_favorite_list_key(user_id,page,page_size)

    async def load_favorite_list():
        total = await db.execute(select(func.count()).where(Favorite.user_id == user_id))
        total = total.scalar_one()

        result = await db.execute(select(News,Favorite.id.label("favorite_id"),Favorite.created_at.label("favorite_time"))
                                  .join(Favorite,Favorite.news_id == News.id)
                                  .where(Favorite.user_id == user_id)
                                  .order_by(Favorite.created_at.desc())
                                  .offset((page - 1) * page_size)
                                  .limit(page_size)
                                  )
        result = result.all()
        #缓存里存json 化后的结构，命中缓存时再还原成路由层需要的ORM 对象
        cache_data = {
            "total": total,
            "list": [
                {
                    "news": jsonable_encoder(news),
                    "favorite_id": favorite_id,
                    "favorite_time": favorite_time
                }
                for news,favorite_id,favorite_time in result
            ]
        }

        return cache_data

    cached = await get_or_set_cache_data(cache_key,load_favorite_list,favorite_cache.FAVORITE_LIST_EXPIRE)
    if not cached:
        return [],0

    #还原成 (news,favorite_id,favorite_time) 结构，保持原有返回格式不变
    result = [
        (restore_model(item["news"],News),item["favorite_id"],item["favorite_time"])
        for item in cached["list"]
    ]

    return result,cached["total"]

async def clear_favorite(
        db: AsyncSession,
        user_id: int
):
    result = await db.execute(delete(Favorite).where(Favorite.user_id == user_id))
    await db.commit()
    #清空收藏后该用户的收藏列表缓存失效
    await favorite_cache.clear_cached_favorite_list(user_id)
    return result.rowcount