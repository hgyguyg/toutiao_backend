from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class UserRequest(BaseModel):
    username: str
    password: str

class UserInfoBase(BaseModel):
    nickname: Optional[str] = Field(None,max_length=50,description="昵称")
    avatar: Optional[str] = Field(None,max_length=255,description="头像URL")
    gender: Optional[str] = Field(None,max_length=10,description="性别")
    bio: Optional[str] = Field(None,max_length=500,description="个人简介")

class UserInfo(UserInfoBase):
    id: int
    username: str

    model_config = ConfigDict(
        from_attributes=True
    )

class UserAuthResponse(BaseModel):
    token: str
    user_info: UserInfo = Field(...,alias="userInfo")

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True
    )

class UserUpdateRequest(BaseModel):
    nickname: str
    avatar: str
    gender: str
    bio: str
    phone: str

class UserChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

class UserLoginRequest(BaseModel):
    username: str
    password: str