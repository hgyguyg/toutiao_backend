from typing import List, Dict, Any
from typing import Optional

from cache.base_cache import get_cache_data, set_cache_data, delete_cache_data, \
    delete_cache_data_by_prefix
from config.redis_conf import get_cache_ttl

CATEGORIES_KEY = "news:categories"
NEWS_LIST_PREFIX = "news:list"
NEWS_DETAIL_PREFIX = "news:detail"
NEWS_COUNT_PREFIX = "news:count"

#分类变动频率低，缓存时间可以长一些
CATEGORIES_EXPIRE = 3600
#列表分页缓存时间适中
NEWS_LIST_EXPIRE = 600
#详情缓存时间适中
NEWS_DETAIL_EXPIRE = 600
#总数用于分页判断，缓存时间与列表保持一致
NEWS_COUNT_EXPIRE = 600

def build_news_list_key(page: int,page_size: int,category_id: Optional[int] = None) -> str:
    #分类为空时用 all 占位，保证 key 规则唯一
    category_part = category_id if category_id is not None else "all"
    return f"{NEWS_LIST_PREFIX}:{category_part}:{page}:{page_size}"

def build_news_detail_key(news_id: int) -> str:
    return f"{NEWS_DETAIL_PREFIX}:{news_id}"

def build_news_count_key(category_id: Optional[int] = None) -> str:
    category_part = category_id if category_id is not None else "all"
    return f"{NEWS_COUNT_PREFIX}:{category_part}"

async def get_cached_categories():
    return await get_cache_data(CATEGORIES_KEY)

async def set_cached_categories(data: List[Dict[str,Any]], expire: int = CATEGORIES_EXPIRE):
    return await set_cache_data(CATEGORIES_KEY, data, expire)

async def get_cached_news_list(page: int,page_size: int,category_id: Optional[int] = None):
    return await get_cache_data(build_news_list_key(page,page_size,category_id))

async def set_cached_news_list(news_list: List[Dict[str,Any]],page: int,page_size: int,category_id: Optional[int] = None,expire: int = NEWS_LIST_EXPIRE):
    return await set_cache_data(build_news_list_key(page,page_size,category_id),news_list,expire)

async def get_cached_news_detail(news_id: int):
    return await get_cache_data(build_news_detail_key(news_id))

async def set_cached_news_detail(news: Dict[str,Any],news_id: int,expire: int = NEWS_DETAIL_EXPIRE):
    return await set_cache_data(build_news_detail_key(news_id),news,expire)

async def get_cached_news_count(category_id: Optional[int] = None):
    return await get_cache_data(build_news_count_key(category_id))

async def set_cached_news_count(total: int,category_id: Optional[int] = None,expire: int = NEWS_COUNT_EXPIRE):
    return await set_cache_data(build_news_count_key(category_id),total,expire)

async def delete_cached_news_detail(news_id: int):
    #浏览量变化后只需失效该条详情
    return await delete_cache_data(build_news_detail_key(news_id))

async def update_cached_news_detail_views(news_id: int,views: int):
    """
    浏览量自增属于高频写操作，若直接删缓存会让每次浏览都失效缓存、缓存形同虚设。
    这里改为原地更新缓存里的浏览量，并保留原有剩余过期时间，
    既保证读到的浏览量准确，又不会反复回源数据库
    """
    cache_key = build_news_detail_key(news_id)
    cached = await get_cache_data(cache_key)
    #只有缓存中确实是该条详情时才更新，避免误写其它类型的数据
    if not isinstance(cached, dict):
        return False

    cached["views"] = views
    #沿用剩余过期时间，防止热点新闻因反复浏览而永不过期
    ttl = await get_cache_ttl(cache_key)
    expire = ttl if ttl and ttl > 0 else NEWS_DETAIL_EXPIRE

    return await set_cache_data(cache_key,cached,expire)

async def clear_cached_news():
    #新闻数据发生增删改时调用，清空全部新闻相关缓存
    await delete_cache_data(CATEGORIES_KEY)
    await delete_cache_data_by_prefix(NEWS_LIST_PREFIX)
    await delete_cache_data_by_prefix(NEWS_DETAIL_PREFIX)
    await delete_cache_data_by_prefix(NEWS_COUNT_PREFIX)
    return True