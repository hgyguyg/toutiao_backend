from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"] = Field("user", description="user / assistant")
    content: str = Field("", max_length=4000, description="发言内容")

class AskRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    question: str = Field(..., min_length=1, max_length=500, description="用户问题")
    history: list[ChatMessage] = Field(
        default_factory=list, max_length=40, description="最近若干轮对话（不传则由 checkpointer 承继）"
    )
    top_k: int = Field(6, ge=1, le=20, alias="topK", description="知识库召回条数")
    thread_id: str | None = Field(
        None,
        max_length=64,
        alias="threadId",
        description="会话 ID；不传则服务端新建会话，建议前端持久化后复用",
    )