from datetime import datetime

from pydantic import BaseModel, Field
from pydantic import ConfigDict

from schemas.news import NewsBase


class HistoryAddRequest(BaseModel):
    news_id: int = Field(...,alias="newsId")
    model_config = ConfigDict(populate_by_name=True)

class HistoryNewsItemResponse(NewsBase):
    # 浏览记录自身的 id，前端删除单条历史时需要它
    history_id: int = Field(alias="historyId")
    history_time: datetime = Field(alias="historyTime")

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True
    )

class HistoryListResponse(BaseModel):
    list: list[HistoryNewsItemResponse]
    total: int
    has_more: bool = Field(alias="hasMore")

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True
    )
