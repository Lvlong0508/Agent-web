from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config.settings import settings
from app.models.user import Base

# 异步数据库引擎（连接池）
engine = create_async_engine(settings.database_url, echo=False)
# 异步会话工厂（每个请求一个独立会话）
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# 启动时自动创建所有表的 DDL
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# FastAPI 依赖注入：为每个请求提供独立数据库会话，请求结束自动提交/回滚
async def get_db() -> AsyncSession:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
