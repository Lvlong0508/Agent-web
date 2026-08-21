"""Skill 库业务：按用户输入检索匹配 skill（向量知识库装配）。

入库 + 检索都收敛在本类，不新增文件：SkillLoader（agent/skills/loader.py）管
磁盘扫描与 frontmatter 解析，本类管向量库对账写入与语义检索，职责不重叠。
"""

import asyncio
import logging

from app.schemas.knowledge import SkillCandidate
from app.services.knowledge.base_service import BaseKnowledgeService

logger = logging.getLogger(__name__)


class SkillKnowledgeService(BaseKnowledgeService):
    """skill 库：增量入库（sync_from_disk）+ 语义检索（search）。

    数据布局：documents = name+description（仅描述参与 embedding 与相似度），
    metadata 精简 5 字段（kb_type/owner_id/source_doc_id=name/name/description/mtime）；
    正文不存库，read_skill 工具经 loader 从磁盘读。
    """

    def _build_where(self, owner_id: str | None = None) -> dict:
        return {"kb_type": "skill"}

    async def sync_from_disk(self, loader) -> None:
        """扫描磁盘技能 → 与库内对账 → 增量入库（幂等）。

        对账三分支：磁盘有库无→新增；都有但 mtime 变→删后重加；
        库有磁盘无→清理残留。mtime 未变则跳过，不重复 embedding。
        """
        disk = {s["name"]: s for s in loader.skills()}
        db_mtimes = await self._get_db_skill_mtimes()

        # 1. 删除：库中存在但磁盘已无该技能（磁盘删除后清理向量库残留）
        for name in set(db_mtimes) - set(disk):
            logger.info("skill 向量库清理残留技能: %s", name)
            await self.delete_by_source(name)

        # 2. 新增/更新：磁盘有、库无 或 mtime 变化
        for name, skill in disk.items():
            if name not in db_mtimes or db_mtimes[name] != skill["mtime"]:
                if name in db_mtimes:
                    logger.info("skill 已变更，重新入库: %s", name)
                    await self.delete_by_source(name)
                else:
                    logger.info("skill 新增入库: %s", name)
                await self._add_skill(skill)

    async def _get_db_skill_mtimes(self) -> dict[str, float]:
        """返回库内全部技能 {source_doc_id: mtime}，供增量对账"""
        result = await asyncio.to_thread(
            self.collection.get,
            where=self._build_where(),
            include=["metadatas"],
        )
        # 把每条记录的 metadata 转成 {技能名: mtime} 字典，供对账对比
        mtimes: dict[str, float] = {}
        for meta in result["metadatas"]:
            mtimes[meta["source_doc_id"]] = meta.get("mtime", 0)
        return mtimes

    async def _add_skill(self, skill: dict) -> None:
        """单个技能入库：documents=name+description，metadata 存来源+name/description/mtime"""
        text = f"{skill['name']}\n{skill['description']}"
        vectors = await self.embedder.batch_embed([text])
        # 同步 Chroma add 调用放进线程池，避免阻塞事件循环
        await asyncio.to_thread(
            self.collection.add,
            ids=[f"skill:system:{skill['name']}:0"],
            documents=[text],
            embeddings=vectors,
            metadatas=[{
                "kb_type": "skill",
                "owner_id": "system",
                "source_doc_id": skill["name"],  # 过滤键=技能名（对账/删除/检索路由）
                "name": skill["name"],
                "description": skill["description"],
                "mtime": skill["mtime"],
            }],
        )

    async def search(
        self,
        query: str,
        top_k: int = 5,
        threshold: float = 0.5,
    ) -> list[SkillCandidate]:
        """语义检索命中技能列表，阈值过滤 + 按技能去重。

        top_k：候选上限（注入提示词的数量，配置可调）；
        threshold：余弦相似度阈值，低于则丢弃（防无关技能进上下文）。
        """
        query_vectors = await self.embedder.batch_embed([query])
        # 同步 Chroma query 调用放进线程池，避免阻塞事件循环
        result = await asyncio.to_thread(
            self.collection.query,
            query_embeddings=query_vectors,
            n_results=top_k,
            where=self._build_where(),
            include=["documents", "metadatas", "distances"],
        )
        candidates: list[SkillCandidate] = []
        seen: set[str] = set()
        for i in range(len(result["ids"][0])):
            meta = result["metadatas"][0][i]
            name = meta.get("name", "")
            score = 1 - result["distances"][0][i]  # cosine distance -> 相似度
            # 先过阈值再去重：避免某技能首个 chunk 低于阈值时，把后续达标的
            # 同技能 chunk 也误杀（当前单 chunk 无影响，为多 chunk 预留正确顺序）
            if score < threshold:
                continue
            if name in seen:
                continue
            seen.add(name)
            candidates.append(SkillCandidate(
                name=name,
                description=meta.get("description", ""),
                score=score,
            ))
        return candidates