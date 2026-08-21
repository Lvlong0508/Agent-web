"""SkillKnowledgeService 测试：增量入库对账 + 检索，mock collection 与 embedder"""

import pytest

from app.services.knowledge.skill_service import SkillKnowledgeService
from app.schemas.knowledge import SkillCandidate


class FakeCollection:
    """伪 Chroma collection：内存记录，供对账与检索断言"""

    def __init__(self):
        self.records: dict[str, dict] = {}  # id -> {document, metadata}
        self.query_result = {
            "ids": [["skill:system:accounting-expert:0"]],
            "documents": [["accounting-expert\n记账知识"]],
            "metadatas": [[{
                "kb_type": "skill", "owner_id": "system",
                "source_doc_id": "accounting-expert",
                "name": "accounting-expert",
                "description": "记账知识", "mtime": 111.0,
            }]],
            "distances": [[0.08]],
        }

    def add(self, **kwargs):
        ids = kwargs["ids"]
        for i, doc_id in enumerate(ids):
            self.records[doc_id] = {
                "document": kwargs["documents"][i],
                "metadata": kwargs["metadatas"][i],
            }

    def delete(self, ids=None, where=None):
        if where:
            sid = where.get("source_doc_id")
            self.records = {k: v for k, v in self.records.items()
                            if v["metadata"]["source_doc_id"] != sid}

    def get(self, where=None, include=None, limit=None, offset=None):
        if include == []:
            return {"ids": [k for k in self.records]}
        return {
            "ids": [k for k in self.records],
            "documents": [r["document"] for r in self.records.values()],
            "metadatas": [r["metadata"] for r in self.records.values()],
        }

    def query(self, **kwargs):
        return self.query_result


class FakeEmbedder:
    """伪 embedding：固定 3 维向量"""

    async def batch_embed(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]


def _skill(name, mtime, description="描述"):
    return {
        "name": name, "description": description, "body": "正文",
        "mtime": mtime,
    }


class _FakeLoader:
    """伪 loader：只暴露 skills()，供 sync_from_disk 消费"""

    def __init__(self, skills):
        self._skills = skills

    def skills(self):
        return self._skills


@pytest.mark.asyncio
async def test_sync_from_disk_adds_new_skill():
    """库为空时，磁盘技能全部入库：documents=name+desc，metadata 含 name/desc/mtime"""
    col = FakeCollection()
    service = SkillKnowledgeService(col, FakeEmbedder())
    loader = _FakeLoader([_skill("accounting-expert", 111.0)])

    await service.sync_from_disk(loader)

    assert "skill:system:accounting-expert:0" in col.records
    rec = col.records["skill:system:accounting-expert:0"]
    assert rec["document"] == "accounting-expert\n描述"
    assert rec["metadata"]["name"] == "accounting-expert"
    assert rec["metadata"]["description"] == "描述"
    assert rec["metadata"]["mtime"] == 111.0
    assert rec["metadata"]["source_doc_id"] == "accounting-expert"
    # 溯源冗余字段已去掉：不存 source_file / chunk_index
    assert "source_file" not in rec["metadata"]
    assert "chunk_index" not in rec["metadata"]


@pytest.mark.asyncio
async def test_sync_from_disk_skips_unchanged():
    """库中已有且 mtime 相同的技能跳过（不重复 embedding）"""
    col = FakeCollection()
    service = SkillKnowledgeService(col, FakeEmbedder())
    # 预置库内记录，mtime 与磁盘一致
    col.records["skill:system:accounting-expert:0"] = {
        "document": "accounting-expert\n描述",
        "metadata": {
            "kb_type": "skill", "owner_id": "system",
            "source_doc_id": "accounting-expert",
            "name": "accounting-expert",
            "description": "描述", "mtime": 111.0,
        },
    }
    loader = _FakeLoader([_skill("accounting-expert", 111.0)])

    await service.sync_from_disk(loader)

    # 未发生增删：记录数不变（跳过 = 不重复写入）
    assert len(col.records) == 1


@pytest.mark.asyncio
async def test_sync_from_disk_updates_changed_mtime():
    """库中已有但 mtime 变新 → 删除旧记录后重新入库"""
    col = FakeCollection()
    service = SkillKnowledgeService(col, FakeEmbedder())
    col.records["skill:system:accounting-expert:0"] = {
        "document": "accounting-expert\n旧描述",
        "metadata": {
            "kb_type": "skill", "owner_id": "system",
            "source_doc_id": "accounting-expert",
            "name": "accounting-expert",
            "description": "旧描述", "mtime": 100.0,
        },
    }
    loader = _FakeLoader([_skill("accounting-expert", 200.0, description="新描述")])

    await service.sync_from_disk(loader)

    assert len(col.records) == 1  # 删旧加新后仍一条
    rec = col.records["skill:system:accounting-expert:0"]
    assert rec["metadata"]["description"] == "新描述"
    assert rec["metadata"]["mtime"] == 200.0


@pytest.mark.asyncio
async def test_sync_from_disk_deletes_removed_skill():
    """磁盘已删技能，库中残留 → 清理删除"""
    col = FakeCollection()
    service = SkillKnowledgeService(col, FakeEmbedder())
    col.records["skill:system:gone:0"] = {
        "document": "gone\n描述",
        "metadata": {
            "kb_type": "skill", "owner_id": "system",
            "source_doc_id": "gone",
            "name": "gone", "description": "描述", "mtime": 100.0,
        },
    }
    loader = _FakeLoader([])  # 磁盘无任何技能

    await service.sync_from_disk(loader)

    assert len(col.records) == 0


@pytest.mark.asyncio
async def test_sync_from_disk_empty_loader_noop():
    """磁盘无技能且库也为空：幂等，不报错"""
    col = FakeCollection()
    service = SkillKnowledgeService(col, FakeEmbedder())

    await service.sync_from_disk(_FakeLoader([]))

    assert len(col.records) == 0


@pytest.mark.asyncio
async def test_search_returns_candidates_filtered_by_threshold():
    """search：命中过滤阈值，返回 SkillCandidate（含 name/description/score）"""
    col = FakeCollection()
    # 构造两条命中：一条高于阈值，一条低于
    col.query_result = {
        "ids": [["skill:system:accounting-expert:0", "skill:system:low:0"]],
        "documents": [["accounting-expert\n记账知识", "low\n低相关"]],
        "metadatas": [[
            {"kb_type": "skill", "owner_id": "system", "source_doc_id": "accounting-expert",
             "name": "accounting-expert",
             "description": "记账知识", "mtime": 1.0},
            {"kb_type": "skill", "owner_id": "system", "source_doc_id": "low",
             "name": "low",
             "description": "低相关", "mtime": 1.0},
        ]],
        "distances": [[0.05, 0.9]],
    }
    service = SkillKnowledgeService(col, FakeEmbedder())

    # 阈值 0.5：0.95 命中保留，0.1 丢弃
    candidates = await service.search("记账", top_k=5, threshold=0.5)

    assert len(candidates) == 1
    assert candidates[0].name == "accounting-expert"
    assert candidates[0].score == 0.95
    assert isinstance(candidates[0], SkillCandidate)
    # SkillCandidate 不暴露 source_doc_id（与 name 恒等，冗余）
    assert not hasattr(candidates[0], "source_doc_id")


@pytest.mark.asyncio
async def test_search_dedupes_by_name():
    """search：同一技能多 chunk 只取首个（去重）"""
    col = FakeCollection()
    col.query_result = {
        "ids": [["skill:system:accounting-expert:0", "skill:system:accounting-expert:1"]],
        "documents": [["accounting-expert\n记账知识", "accounting-expert\n第二节"]],
        "metadatas": [[
            {"kb_type": "skill", "owner_id": "system", "source_doc_id": "accounting-expert",
             "name": "accounting-expert", "description": "记账知识", "mtime": 1.0},
            {"kb_type": "skill", "owner_id": "system", "source_doc_id": "accounting-expert",
             "name": "accounting-expert", "description": "记账知识", "mtime": 1.0},
        ]],
        "distances": [[0.05, 0.06]],
    }
    service = SkillKnowledgeService(col, FakeEmbedder())

    candidates = await service.search("记账", top_k=5, threshold=0.5)

    assert len(candidates) == 1