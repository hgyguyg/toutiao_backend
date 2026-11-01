from fastapi import HTTPException
from fastapi.params import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from config.db_conf import get_db
from crud.users import get_user_by_token


async def get_current_user(
        db: AsyncSession = Depends(get_db),
        # 默认空串而不是 ...：缺认证头时走下面的 401，而不是被 FastAPI 判成 422 必填字段缺失
        authorization: str = Header("", alias="")
):
    parts = (authorization or "").split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少或非法的认证信息")
    user = await get_user_by_token(db, parts[1])
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或登录已过期")
    return user