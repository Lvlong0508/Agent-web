"""文本向量化：把文档块/查询文本转成向量，供 Chroma 入库与检索。

用 langchain-openai 的 OpenAIEmbeddings 走 DashScope 兼容端点
（复用 DASHSCOPE_BASE_URL/API_KEY，与 LLM 走同一通道，不新增依赖）。
text-embedding-v3 单次最多 10 条，超量自动分批；
同步 embedding 调用放进 asyncio.to_thread，避免阻塞事件循环。
"""

import asyncio

from langchain_openai import OpenAIEmbeddings

from app.config.agent_settings import agent_settings
from app.config.settings import settings


class DashScopeEmbedder:
    """把文本批量转向量；embeddings 可注入（测试传伪对象，默认构造真实客户端）"""

    def __init__(
        self,
        embeddings: OpenAIEmbeddings | None = None,
        batch_size: int = 10,
    ) -> None:
        self.batch_size = batch_size
        # 未注入时构造真实客户端：复用 DashScope 兼容端点与 key，维度固定 1024
        self.embeddings = embeddings or OpenAIEmbeddings(
            model=agent_settings.EMBEDDING_MODEL,
            base_url=settings.DASHSCOPE_BASE_URL,
            api_key=settings.DASHSCOPE_API_KEY,
            dimensions=settings.EMBEDDING_DIM,
            # 非 OpenAI 官方服务：关掉 token 长度检查，按原文发送
            # （DashScope 兼容端点不认识 OpenAI 的 token 编码）
            check_embedding_ctx_length=False,
        )

    async def batch_embed(self, texts: list[str]) -> list[list[float]]:
        """分批向量化：返回向量列表，顺序与 texts 一一对应（入库/检索对齐 ID）"""
        vectors: list[list[float]] = []
        # 按 batch_size 切批，避免超出单次调用条数上限
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            # embed_documents 是同步阻塞调用，放进线程池避免卡住事件循环
            batch_vectors = await asyncio.to_thread(self.embeddings.embed_documents, batch)
            vectors.extend(batch_vectors)
        return vectors