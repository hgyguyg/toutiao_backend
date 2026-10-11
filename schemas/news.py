from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class NewsBase(BaseModel):
    id : int
    title: str
    description: Optional[str]
    content: str
    image: Optional[str]
    author: Optional[str]
    category_id: int = Field(alias="categoryId")
    views: int
    publish_time: datetime = Field(alias="publishTime")

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True
    )