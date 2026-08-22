"""Chroma 向量库连接管理器：单例模式，全局只维护一个 HttpClient 与四类 collection。

对齐 MongoDB 连接管理器（app/middleware/mongodb.py）的模式：
- connect() 幂等初始化，get_or_create 保证 collection 存在且复用
- close() 关闭客户端
- get_collection() 按 kb_type 路由到对应 collection
"""

import chromadb
import httpx

from app.config.agent_settings import agent_settings
from app.config.settings import settings


class ChromaClient:
    """Chroma 连接与 collection 管理（类属性单例）"""

    client: chromadb.ClientAPI | None = None
    _collections: dict[str, object] = {}

    @classmethod
    def connect(cls) -> None:
        """初始化 HttpClient 并建立 4 个 collection（幂等：已存在则复用）"""
        # 先确保目标 database 存在：server 不会自动创建，缺库时后续 get_or_create 会 404
        cls._ensure_database(
            settings.CHROMA_HOST,
            settings.CHROMA_PORT,
            settings.CHROMA_TENANT,
            settings.CHROMA_DATABASE,
        )
        cls.client = chromadb.HttpClient(
            host=settings.CHROMA_HOST,
            port=settings.CHROMA_PORT,
            tenant=settings.CHROMA_TENANT,      # 项目共用 default_tenant
            database=settings.CHROMA_DATABASE,  # database 按项目名隔离，与其他项目分开
        )
        # 按配置映射逐个 get_or_create；cosine 与 DashScope 归一化向量匹配
        for kb_type, name in agent_settings.CHROMA_COLLECTIONS.items():
            cls._collections[kb_type] = cls.client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"},
            )

    @staticmethod
    def _ensure_database(host: str, port: int, tenant: str, database: str) -> None:
        """确保 database 存在：GET 探测 404 则 POST 创建（幂等，供测试 mock）"""
        base = f"http://{host}:{port}/api/v2/tenants/{tenant}/databases"
        resp = httpx.get(f"{base}/{database}", timeout=5)
        if resp.status_code == 404:
            resp = httpx.post(base, json={"name": database}, timeout=5)
            resp.raise_for_status()

    @classmethod
    def close(cls) -> None:
        cls.client = None
        cls._collections = {}

    @classmethod
    def get_collection(cls, kb_type: str) -> object:
        if cls.client is None:
            raise RuntimeError("ChromaClient 未初始化，请先调用 connect()")
        if kb_type not in cls._collections:
            raise ValueError(f"未知库类型: {kb_type}")
        return cls._collections[kb_type]