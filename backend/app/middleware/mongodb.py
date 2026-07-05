from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config.settings import settings


class MongoDB:
    """MongoDB 连接管理器：单例模式，全局只维护一个客户端"""

    client: AsyncIOMotorClient | None = None
    db: AsyncIOMotorDatabase | None = None

    @classmethod
    async def connect(cls):
        """初始化 MongoDB 客户端并获取数据库引用"""
        cls.client = AsyncIOMotorClient(settings.MONGODB_URI)
        cls.db = cls.client[settings.MONGODB_DB_NAME]

    @classmethod
    async def close(cls):
        """关闭 MongoDB 连接（Motor 的 close() 是同步方法，无需 await）"""
        if cls.client:
            cls.client.close()
            cls.client = None
            cls.db = None


# 依赖注入：获取 MongoDB 数据库实例
async def get_db() -> AsyncIOMotorDatabase:
    """FastAPI 依赖注入函数，返回 MongoDB 数据库引用"""
    if MongoDB.db is None:
        await MongoDB.connect()
        # connect() 成功后 db 一定不为 None，告知类型检查器
        assert MongoDB.db is not None
    return MongoDB.db
