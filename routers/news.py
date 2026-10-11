from fastapi import APIRouter,Depends,Query,HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from config.db_conf import get_db
from crud import news
from utils.response import success_response

router = APIRouter(prefix="/api/news",tags=["news"])
@router.get("/categories")
async def get_categories(db:AsyncSession = Depends(get_db),skip: int = 0,limit:int = 100):
    categories = await news.get_categories(db,skip,limit)

    return success_response(message = "获取分类成功",data = categories)

@router.get("/list")
async def get_news_list(
        category_id: int = Query(...,alias="categoryId"),
        page: int = Query(1,ge=1),
        pagesize: int = Query(10,le=100,alias="pageSize"),
        db:AsyncSession = Depends(get_db)
    ):

    total = await news.get_news_count(db,category_id)

    data = {
        "list": await news.get_news_list(db,category_id,page,pagesize),
        "total": total,
        "hasMore": page * pagesize < total
    }

    return success_response(message = "获取新闻列表成功",data = data)

@router.get("/detail")
async def read_news_detail(
        news_id: int = Query(...,alias="id"),
        db:AsyncSession = Depends(get_db)
    ):
    new = await news.read_news_details(db,news_id)
    if new is None:
        raise HTTPException(status_code = 404, detail="新闻不存在")

    #浏览量自增后同步刷新缓存中的浏览量，保证返回值与数据库一致
    views_res = await news.increase_news_views(db,news_id,new.views + 1)
    if not views_res:
        raise HTTPException(status_code = 404,detail = "更新新闻浏览量失败")

    related_news_list = await news.get_related_news_list(db,new.category_id,new.id)

    data = {
        "id":new.id,
        "title":new.title,
        "content":new.content,
        "image":new.image,
        "author":new.author,
        "publishTime": new.publish_time,
        "categoryId": new.category_id,
        "views":new.views,
        "relatedNews": related_news_list
    }

    return success_response(message = "获取新闻详情成功",data = data)