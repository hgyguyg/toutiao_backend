from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

#本地开发用的数据库密码占位符，请改成你自己的密码后运行。
#注意：真实密码切勿提交到公开仓库。
SQL_PASSWORD = "xxx"
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