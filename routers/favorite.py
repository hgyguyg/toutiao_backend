from fastapi import APIRouter, HTTPException
from fastapi.params import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from config.db_conf import get_db
from models.users import User
from utils.auth import get_current_user
from utils.response import success_response
from crud import favorite
from schemas.favorite import FavoriteCheckResponse, FavoriteListResponse, FavoriteAddRequest

router = APIRouter(prefix="/api/favorite",tags=["favorite"])

@router.get("/check")
async def check_favorite(
        news_id: int = Query(...,alias="newsId"),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(get_current_user)
):
    is_favorite = await favorite.check_favorite(news_id, user.id, db)
    return success_response(message="检查收藏状态成功",data = FavoriteCheckResponse(isFavorite = is_favorite))

@router.post("/add")
async def add_favorite(
        data: FavoriteAddRequest,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(get_current_user)
):
    result = await favorite.add_favorite(data.news_id, user.id, db)
    return success_response(message="收藏成功", data=result)

@router.delete("/remove")
async def remove_favorite(
        news_id: int = Query(...,alias="newsId"),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(get_current_user)
):
    result = await favorite.remove_favorite(news_id, user.id, db)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="取消收藏失败")
    return success_response(message="取消收藏成功")

@router.get("/list")
async def get_favorite_list(
        page: int,
        page_size: int = Query(..., alias="pageSize"),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(get_current_user)
):
    result,total = await favorite.get_favorite_list(db,user.id,page, page_size)
    favorite_list = [{
        **news.__dict__,
        "favorite_id": favorite_id,
        "favorite_time": favorite_time
    }for news,favorite_id,favorite_time in result]
    has_more = total > page * page_size

    return success_response(message="获取收藏列表成功", data=FavoriteListResponse(list=favorite_list, total=total, hasMore=has_more))

@router.delete("/clear")
async def clear_favorite(
        db: AsyncSession = Depends(get_db),
        user: User = Depends(get_current_user)
):
    count = await favorite.clear_favorite(db,user.id)
    return success_response(message = f"成功清除{count}条记录")
