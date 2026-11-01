import os

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

SQL_PASSWORD = os.getenv("DATABASE_PASSWORD")
DATABASE_URL = f"mysql+aiomysql://root:{SQL_PASSWORD}@localhost:3306/news_app?charset=utf8mb4"

async_engine = create_async_engine(
    DATABASE_URL,
    echo=True,
    pool_size = 10,
    max_overflow = 20
)

AsyncSessionLocal = async_sessionmaker(
    async_engine,
    expire_on_commit=False,
    class_=AsyncSession
)

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except:
            await session.rollback()
            raise
        finally:
            await session.close()