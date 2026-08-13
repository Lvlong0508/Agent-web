"""MySQL 数据库中间件：基于 SQLAlchemy 异步引擎的公共连接层。

对外暴露三样东西：
- Base：模型声明基类，后续 ORM 模型统一继承它
- SessionLocal：异步会话工厂，供业务代码创建会话
- get_db()：FastAPI 依赖，路由通过 Depends(get_db) 获取会话并自动关闭
"""

from collections.abc import AsyncIterator
from urllib.parse import quote_plus

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config.settings import settings


# SQLAlchemy 2.x 模型基类：所有 ORM 模型继承它定义表结构
class Base(DeclarativeBase):
    pass


# 异步引擎：asyncmy 驱动 + 连接池。
# 密码/库名经 quote_plus 做 URL 编码，避免密码中的 @、# 等字符被当作连接串分隔符。
# pool_pre_ping=True：取连接前先探测存活，MySQL 断开后可自动重连；
# pool_recycle=3600：连接超过 1 小时自动回收，避免被 MySQL 侧超时关闭
engine = create_async_engine(
    (
        f"mysql+asyncmy://{settings.MYSQL_USER}:{quote_plus(settings.MYSQL_PASSWORD)}"
        f"@{settings.MYSQL_HOST}:{settings.MYSQL_PORT}/{quote_plus(settings.MYSQL_DB_NAME)}"
        "?charset=utf8mb4"
    ),
    pool_pre_ping=True,
    pool_recycle=3600,
)

# 异步会话工厂：expire_on_commit=False 让提交后对象仍可继续读取属性
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：为每个请求提供一个数据库会话，结束后关闭归还连接池"""
    async with SessionLocal() as session:
        yield session
