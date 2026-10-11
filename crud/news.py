from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from models.news import Category,News
from fastapi import Query

from cache import news_cache
from cache.base_cache import get_or_set_cache_data, restore_model

async def get_categories(db:AsyncSession,skip: int = 0,limit: int = 100):
    #分类数据变动频率低，走统一缓存入口，未命中时回源并回填
    async def load_categories():
        result = await db.execute(select(Category).offset(skip).limit(limit))
        return jsonable_encoder(result.scalars().all())

    return await get_or_set_cache_data(
        news_cache.CATEGORIES_KEY,
        load_categories,
        news_cache.CATEGORIES_EXPIRE
    )

async def get_news_list(
        db:AsyncSession,
        category_id: int = Query(...,alias="categoryId"),
        page: int = 1,
        pagesize: int = Query(10,le=100,alias="pageSize")
    ):
    cache_key = news_cache.build_news_list_key(page,pagesize,category_id)

    async def load_news_list():
        result = await db.execute(select(News).where(News.category_id == category_id).offset((page-1) * pagesize).limit(pagesize))
        return jsonable_encoder(result.scalars().all())

    return await get_or_set_cache_data(cache_key,load_news_list,news_cache.NEWS_LIST_EXPIRE)

async def get_news_count(
        db:AsyncSession,
        category_id: int = Query(...,alias="categoryId")
    ) -> int:
    cache_key = news_cache.build_news_count_key(category_id)

    async def load_news_count():
        result = await db.execute(select(News).where(News.category_id == category_id))
        result = result.scalars().all()
        return len(result) if result else 0

    return await get_or_set_cache_data(
        cache_key,
        load_news_count,
        news_cache.NEWS_COUNT_EXPIRE,
        cache_empty = False
    )

async def read_news_details(
        db:AsyncSession,
        news_id: int = Query(...,alias="id")
    ):
    cache_key = news_cache.build_news_detail_key(news_id)

    async def load_news_detail():
        result = await db.execute(select(News).where(News.id == news_id))
        return result.scalar_one_or_none()

    #详情不存在时也要缓存空值，避免不存在的id 反复查库
    data = await get_or_set_cache_data(cache_key,load_news_detail,news_cache.NEWS_DETAIL_EXPIRE)
    #命中缓存时数据是字典，还原成ORM 对象供路由层按属性取值
    return restore_model(data,News)

async def increase_news_views(
        db:AsyncSession,
        news_id: int = Query(...,alias="id"),
        views: int = 0
    ):
    # update 返回的是 CursorResult，不是ORM 实例，不能对它调 refresh，否则抛 UnmappedInstanceError
    result = await db.execute(update(News).where(News.id == news_id).values(views = News.views + 1))
    await db.commit()

    if result.rowcount <= 0:
        return False

    #浏览量变化后同步更新详情缓存中的浏览量，保证读到的数据与数据库一致
    await news_cache.update_cached_news_detail_views(news_id,views)

    return True

async def get_related_news_list(
        db:AsyncSession,
        news_category_id: int,
        news_id: int,
        limit: int = 5
):
    result = await db.execute(select(News).where(
        News.id != news_id,
        News.category_id == news_category_id
    ).order_by(
        News.views.desc(),
        News.publish_time.desc()
    ).limit(limit)
    )
    result = result.scalars().all()

    return [{"id":new.id,
            "title":new.title,
            "content":new.content,
            "image":new.image,
            "author":new.author,
            "publish_time": new.publish_time,
            "category_id": new.category_id,
            "views":new.views
            } for new in result]