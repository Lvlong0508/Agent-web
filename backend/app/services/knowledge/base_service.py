"""知识库业务基类：承载增删查统计的共性实现。

子类差异只在过滤策略（_build_where），由各库类型定制：
- enterprise：无过滤（公共知识）
- user：强制 owner_id 隔离
- tool/skill：kb_type 过滤（预留）
"""

import asyncio

from app.schemas.knowledge import (
    ChunkAddRequest,
    ChunkMetadata,
    ChunkSearchResponse,
    SearchResultItem,
)


class BaseKnowledgeService:
    """向量知识库业务基类：注入 collection 与 embedder，提供 CRUD/检索/统计"""

    def __init__(self, collection, embedder) -> None:
        self.collection = collection  # chromadb Collection（测试注入伪对象）
        self.embedder = embedder      # DashScopeEmbedder（测试注入伪对象）

    # ---- 子类覆盖点：各库类型的过滤策略 ----
    def _build_where(self, owner_id: str | None = None) -> dict:
        """返回检索/删除时的 metadata 过滤条件；子类按库类型定制"""
        return {}

    def _build_ids(self, req: ChunkAddRequest) -> list[str]:
        """按 ID 规范生成块 ID：{kb_type}:{owner_id}:{source_doc_id}:{chunk_index}"""
        return [
            f"{req.kb_type}:{req.owner_id}:{req.source_doc_id}:{i}"
            for i in range(len(req.chunks))
        ]

    def _build_metadatas(self, req: ChunkAddRequest) -> list[dict]:
        """为每块生成 metadata（5 字段），chunk_index 随序号递增（0 起）"""
        return [
            ChunkMetadata(
                kb_type=req.kb_type,
                owner_id=req.owner_id,
                source_doc_id=req.source_doc_id,
                source_file=req.source_file,
                chunk_index=i,
            ).model_dump()
            for i in range(len(req.chunks))
        ]

    async def add_chunks(self, req: ChunkAddRequest) -> None:
        """批量写入：向量化 -> 组装 ids/metadatas -> collection.add"""
        embeddings = await self.embedder.batch_embed(req.chunks)
        # chromadb 的 add 是同步 HTTP 调用，放进线程池避免阻塞事件循环
        await asyncio.to_thread(
            self.collection.add,
            ids=self._build_ids(req),
            documents=req.chunks,
            embeddings=embeddings,
            metadatas=self._build_metadatas(req),
        )

    async def search(
        self,
        query: str,
        top_k: int = 5,
        owner_id: str | None = None,
    ) -> ChunkSearchResponse:
        """语义检索：查询向量化 -> collection.query(带 where) -> 组装溯源结果"""
        where = self._build_where(owner_id)
        query_vectors = await self.embedder.batch_embed([query])
        # chromadb 的 query 是同步 HTTP 调用，放进线程池避免阻塞事件循环
        result = await asyncio.to_thread(
            self.collection.query,
            query_embeddings=query_vectors,
            n_results=top_k,
            where=where or None,
            include=["documents", "metadatas", "distances"],
        )
        # columnar 结果：result["documents"][q][k] 与 metadatas/distances 同索引对齐
        items = []
        # kb_type 兜底取服务自身类型，避免缺 kb_type 的记录触发 pydantic 校验崩溃
        default_kb_type = where.get("kb_type", "")
        for i in range(len(result["ids"][0])):
            meta = result["metadatas"][0][i]
            items.append(
                SearchResultItem(
                    content=result["documents"][0][i],
                    score=1 - result["distances"][0][i],  # cosine distance -> 相似度
                    source_file=meta.get("source_file", ""),
                    chunk_index=meta.get("chunk_index", 0),
                    source_doc_id=meta.get("source_doc_id", ""),
                    kb_type=meta.get("kb_type") or default_kb_type,
                )
            )
        return ChunkSearchResponse(items=items)

    async def delete_by_source(self, source_doc_id: str, owner_id: str | None = None) -> None:
        """按原始文档删除整篇的所有块（合并库类型过滤条件）"""
        where = self._build_where(owner_id)
        where = {**where, "source_doc_id": source_doc_id}
        # 同步删除调用放进线程池，避免阻塞事件循环
        await asyncio.to_thread(self.collection.delete, where=where)

    async def count(self, owner_id: str | None = None) -> int:
        """返回过滤条件下的记录数；user 库必须传 owner_id（隔离安全兜底）"""
        where = self._build_where(owner_id)
        # 用 get(include=[]) 只取 id 列表统计，保持与 search/delete 相同的过滤边界
        result = await asyncio.to_thread(
            self.collection.get, where=where or None, include=[]
        )
        return len(result["ids"])

    async def list_documents(self, owner_id: str | None = None) -> list[dict]:
        """列出全部文档（按 source_doc_id 分组）：溯源概览"""
        where = self._build_where(owner_id)
        result = await asyncio.to_thread(
            self.collection.get, where=where or None, include=["metadatas"]
        )
        # 按 source_doc_id 聚合：文档 id + 文件名 + 块数
        docs: dict[str, dict] = {}
        for meta in result["metadatas"]:
            sid = meta.get("source_doc_id", "")
            if sid not in docs:
                docs[sid] = {
                    "source_doc_id": sid,
                    "source_file": meta.get("source_file", ""),
                    "kb_type": meta.get("kb_type", ""),
                    "chunks": 0,
                }
            docs[sid]["chunks"] += 1
        return list(docs.values())