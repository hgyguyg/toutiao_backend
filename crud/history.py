from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from models.history import History
from models.news import News

from cache import history_cache
from cache.base_cache import get_or_set_cache_data, restore_model

async def add_history(
        db: AsyncSession,
        user_id: int,
        news_id: int
):
    db_history = History(user_id=user_id, news_id=news_id)
    db.add(db_history)
    await db.commit()
    await db.refresh(db_history)
    #新增浏览记录后该用户的浏览历史列表缓存失效
    await history_cache.clear_cached_history_list(user_id)
    return db_history

async def get_history_list(
        page: int,
        page_size: int,
        db: AsyncSession,
        user_id: int
):
    cache_key = history_cache.build_history_list_key(user_id,page,page_size)

    async def load_history_list():
        #scalar_one 要在 execute 的结果上调用，原本写在 select 对象上会直接抛AttributeError
        total = await db.execute(select(func.count(History.id)).where(History.user_id == user_id))
        total = total.scalar_one()
        result = await db.execute(select(News,History.view_time.label("history_time"),History.id.label("history_id"))
                                  .join(History,History.news_id == News.id)
                                  .where(History.user_id == user_id)
                                  .order_by(History.view_time.desc())
                                  .offset((page-1) * page_size)
                                  .limit(page_size)
                                  )
        result = result.all()
        #缓存里存 json 化后的结构，命中缓存时再还原成路由层需要的ORM 对象
        #history_id 必须一起缓存，否则前端删除单条历史时拿不到记录 id
        cache_data = {
            "total": total,
            "list": [
                {
                    "news": jsonable_encoder(news),
                    "history_id": history_id,
                    "history_time": history_time
                }
                for news,history_time,history_id in result
            ]
        }

        return cache_data

    cached = await get_or_set_cache_data(cache_key,load_history_list,history_cache.HISTORY_LIST_EXPIRE)
    if not cached:
        return [],0

    #还原成 (news,view_time,history_id) 结构，保持原有返回格式不变
    result = [
        (restore_model(item["news"],News),item["history_time"],item["history_id"])
        for item in cached["list"]
    ]

    return result,cached["total"]

async def delete_history(
        db: AsyncSession,
        history_id: int,
        user_id: int
):
    result = await db.execute(delete(History).where(History.user_id == user_id,History.id == history_id))
    await db.commit()
    #删除浏览记录后该用户的浏览历史列表缓存失效
    await history_cache.clear_cached_history_list(user_id)
    return result.rowcount > 0

async def clear(
        db: AsyncSession,
        user_id: int
):
    result = await db.execute(delete(History).where(History.user_id == user_id))
    await db.commit()
    #清空浏览记录后该用户的浏览历史列表缓存失效
    await history_cache.clear_cached_history_list(user_id)
    return result.rowcount