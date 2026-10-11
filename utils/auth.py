from fastapi import HTTPException
from fastapi.params import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from config.db_conf import get_db
from crud.users import get_user_by_token


async def get_current_user(
        db: AsyncSession = Depends(get_db),
        authorization: str = Header(...,alias="")
):
    token = authorization.split()[1]
    user = await get_user_by_token(db,token)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="用户不存在")
    return user