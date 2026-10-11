from fastapi import APIRouter, Query, HTTPException
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from config.db_conf import get_db
from models.users import User
from schemas.history import HistoryAddRequest, HistoryListResponse
from utils.auth import get_current_user
from utils.response import success_response
from crud import history

router = APIRouter(prefix="/api/history",tags=["history"])

@router.post("/add")
async def add_history(
        data: HistoryAddRequest,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(get_current_user),
):
    result = await history.add_history(db,user.id,data.news_id)

    return success_response(message="添加成功",data=result)

@router.get("/list")
async def get_history_list(
        page: int = Query(1,ge=1,),
        page_size: int = Query(10,ge=1,le=100,alias="pageSize"),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(get_current_user),
):
    result,total = await history.get_history_list(page,page_size,db,user.id)
    history_list = [{
        **news.__dict__,
        "history_id": history_id,
        "history_time": view_time
    }for news,view_time,history_id in result]
    has_more = total > page * page_size

    data = HistoryListResponse(list = history_list,total = total,hasMore=has_more)

    return success_response(message="获取成功",data = data)

@router.delete("/delete/{history_id}")
async def delete_history(
        history_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(get_current_user),
):
    res = await history.delete_history(db,history_id,user.id)
    if not res:
        raise HTTPException(status_code=400, detail="删除失败")
    return success_response(message="删除成功")

@router.delete("/clear")
async def clear(
        db: AsyncSession = Depends(get_db),
        user: User = Depends(get_current_user),
):
    count = await history.clear(db,user.id)
    return success_response(message=f"成功清除{count}条记录")

