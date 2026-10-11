from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, func, Integer, String, Text, ForeignKey, Index
from sqlalchemy.orm import DeclarativeBase,Mapped,mapped_column


class Base(DeclarativeBase):
    created_at: Mapped[datetime] = mapped_column(DateTime,default=func.now(),comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime,default=func.now(),onupdate=func.now(),comment="更新时间")

class Category(Base):
    __tablename__ = "news_category"

    id : Mapped[int] = mapped_column(Integer,primary_key=True,autoincrement=True,nullable=False,comment="新闻分类id")
    name : Mapped[str] = mapped_column(String(50),nullable=False,comment="种类名字")
    sort_order : Mapped[int] = mapped_column(Integer,default=0,comment="排序指令")

    def __repr__(self) -> str:
        return f"<Category id={self.id}, name={self.name}, sort_order={self.sort_order}>"

class News(Base):
    __tablename__ = "news"

    __table_args__ = (
        Index("fk_news_category_idx","category_id"),
        Index("idx_publish_time","publish_time")
    )

    id : Mapped[int] = mapped_column(Integer,primary_key=True,autoincrement=True,comment="新闻ID")
    title: Mapped[str] = mapped_column(String(255),comment="新闻标题")
    description: Mapped[Optional[str]] = mapped_column(String(500),comment="新闻描述")
    content: Mapped[str] = mapped_column(Text,comment="新闻内容")
    image: Mapped[Optional[str]] = mapped_column(String(255),comment="图片")
    author: Mapped[Optional[str]] = mapped_column(String(50),comment="作者名称")
    category_id: Mapped[int] = mapped_column(Integer,ForeignKey("news_category.id"), comment="分类ID")
    views: Mapped[int] = mapped_column(Integer,default=0,comment="浏览次数")
    publish_time: Mapped[datetime] = mapped_column(DateTime,default=func.now(),comment="发布时间")

    def __repr__(self) -> str:
        return f"<News id={self.id}, title={self.title}, author={self.author}, category_id={self.category_id}, views={self.views}, publish_time={self.publish_time}>"
