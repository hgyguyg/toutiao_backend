from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.params import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from crud import users
from config.db_conf import get_db
from models.users import User
from schemas.users import UserRequest, UserAuthResponse, UserInfo, UserUpdateRequest, UserChangePasswordRequest, \
    UserLoginRequest
from utils.auth import get_current_user
from utils.response import success_response

router = APIRouter(prefix="/api/users", tags=["users"])


@router.post("/register")
async def register(
        userdata: UserRequest,
        db: AsyncSession = Depends(get_db)
):
    existing_user = await users.get_usr_by_username(db, userdata.username)
    if existing_user is not None:
        raise HTTPException(status_code=400, detail="用户名已存在")

    user = await users.create_user(db, userdata)

    token = await users.create_token(db, user.id)

    responses_data = UserAuthResponse(token=token, userInfo=UserInfo.model_validate(user))
    return success_response(message="注册成功", data=responses_data)


@router.post("/login")
async def login(
        # username: str,
        # password: str,
        userdata: UserLoginRequest,
        db: AsyncSession = Depends(get_db)
):
    user = await users.authenticate_user(db, userdata.username, userdata.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    token = await users.create_token(db, user.id)

    responses_data = UserAuthResponse(token=token, userInfo=UserInfo.model_validate(user))
    return success_response(message="登录成功", data=responses_data)

@router.get("/info")
async def get_user_info(user: User = Depends(get_current_user)):
    return success_response(message="获取用户信息成功",data = UserInfo.model_validate(user))

@router.put("/update")
async def update_user_info(
        user_data: UserUpdateRequest,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    user = await users.update_user(db, user.username, user_data)
    return success_response(message="更新成功",data=UserInfo.model_validate(user))

@router.put("/password")
async def update_password(
        password_data: UserChangePasswordRequest,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    res = await users.change_password(db, user, password_data.old_password, password_data.new_password)
    if not res:
        raise HTTPException(status_code=400, detail="修改密码失败")
    return success_response(message="修改密码成功")
