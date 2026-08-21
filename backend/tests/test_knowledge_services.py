"""知识库业务 service 测试：mock collection 与 embedder，验证过滤策略与 ID 生成"""

import pytest

from app.services.knowledge.enterprise_service import EnterpriseKnowledgeService
from app.services.knowledge.user_service import UserKnowledgeService
from app.schemas.knowledge import ChunkAddRequest


class FakeCollection:
    """伪 Chroma collection：记录 add/query/delete/get/count 调用供断言"""

    def __init__(self):
        self.added = []
        self.queries = []
        self.deleted_where = []
        self.deleted_ids = []
        self.get_calls = []

    def add(self, **kwargs):
        self.added.append(kwargs)

    def query(self, **kwargs):
        self.queries.append(kwargs)
        # 固定返回 1 条命中；这里只验证调用参数，不关心真实检索
        return {
            "ids": [["enterprise:global:doc_001:0"]],
            "documents": [["报销流程：先填单后审批"]],
            "metadatas": [[{
                "kb_type": "enterprise",
                "owner_id": "global",
                "source_doc_id": "doc_001",
                "source_file": "手册v3.pdf",
                "chunk_index": 0,
            }]],
            "distances": [[0.08]],
        }

    def delete(self, ids=None, where=None):
        if ids:
            self.deleted_ids.append(ids)
        if where:
            self.deleted_where.append(where)

    def get(self, where=None, include=None, limit=None, offset=None):
        self.get_calls.append({"where": where, "include": include})
        # count() 用 include=[] 只取 id；其余默认带 documents/metadatas
        if include == []:
            return {"ids": ["enterprise:global:doc_001:0"]}
        return {
            "ids": ["enterprise:global:doc_001:0"],
            "documents": ["报销流程：先填单后审批"],
            "metadatas": [{
                "kb_type": "enterprise",
                "owner_id": "global",
                "source_doc_id": "doc_001",
                "source_file": "手册v3.pdf",
                "chunk_index": 0,
            }],
        }

    def count(self):
        return 1


class FakeEmbedder:
    """伪 embedding：固定 3 维向量，便于断言批次"""

    async def batch_embed(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]


@pytest.fixture
def fake_collection():
    return FakeCollection()


@pytest.fixture
def enterprise_service(fake_collection):
    return EnterpriseKnowledgeService(fake_collection, FakeEmbedder())


@pytest.fixture
def user_service(fake_collection):
    return UserKnowledgeService(fake_collection, FakeEmbedder())


@pytest.mark.asyncio
async def test_enterprise_add_chunks_generates_ids_and_metadata(enterprise_service, fake_collection):
    """企业库 add：ID 规范 + metadata 5 字段 + embeddings 与正文一一对应"""
    req = ChunkAddRequest(
        kb_type="enterprise",
        owner_id="global",
        source_doc_id="doc_001",
        source_file="手册v3.pdf",
        chunks=["块1", "块2"],
    )
    await enterprise_service.add_chunks(req)

    assert len(fake_collection.added) == 1
    call = fake_collection.added[0]
    assert call["ids"] == [
        "enterprise:global:doc_001:0",
        "enterprise:global:doc_001:1",
    ]
    assert call["documents"] == ["块1", "块2"]
    assert call["embeddings"] == [[0.1, 0.2, 0.3], [0.1, 0.2, 0.3]]
    assert call["metadatas"][0] == {
        "kb_type": "enterprise",
        "owner_id": "global",
        "source_doc_id": "doc_001",
        "source_file": "手册v3.pdf",
        "chunk_index": 0,
    }
    assert call["metadatas"][1]["chunk_index"] == 1


@pytest.mark.asyncio
async def test_enterprise_search_no_filter(enterprise_service, fake_collection):
    """企业库检索：无过滤（公共知识），返回溯源信息"""
    resp = await enterprise_service.search("报销流程", top_k=5)

    query_call = fake_collection.queries[0]
    assert "where" not in query_call or query_call["where"] is None
    assert query_call["n_results"] == 5
    assert query_call["query_embeddings"] == [[0.1, 0.2, 0.3]]
    assert len(resp.items) == 1
    assert resp.items[0].source_doc_id == "doc_001"
    assert resp.items[0].score == 0.92  # 1 - distance


@pytest.mark.asyncio
async def test_user_search_forces_owner_filter(user_service, fake_collection):
    """用户库检索：强制注入 owner_id 过滤，不信任调用方传入的过滤条件"""
    resp = await user_service.search("我的记账规则", owner_id="usr_1", top_k=5)

    query_call = fake_collection.queries[0]
    assert query_call["where"] == {"owner_id": "usr_1"}
    assert len(resp.items) == 1


@pytest.mark.asyncio
async def test_user_search_requires_owner_id(user_service):
    """用户库检索缺 owner_id 必须报错（隔离安全兜底）"""
    with pytest.raises(ValueError):
        await user_service.search("我的记账规则")


@pytest.mark.asyncio
async def test_user_search_rejects_empty_owner_id(user_service):
    """用户库检索 owner_id 为空串同样报错（空值守卫）"""
    with pytest.raises(ValueError):
        await user_service.search("我的记账规则", owner_id="")


@pytest.mark.asyncio
async def test_delete_by_source(enterprise_service, fake_collection):
    """按来源删除：走 collection.delete(where=...)，合并 source_doc_id 条件"""
    await enterprise_service.delete_by_source("doc_001")
    assert fake_collection.deleted_where == [{"source_doc_id": "doc_001"}]


@pytest.mark.asyncio
async def test_user_delete_by_source_forces_owner(user_service, fake_collection):
    """用户库按来源删除：where 必须同时带 owner_id 与 source_doc_id"""
    await user_service.delete_by_source("doc_001", owner_id="usr_1")
    assert fake_collection.deleted_where == [
        {"owner_id": "usr_1", "source_doc_id": "doc_001"}
    ]


@pytest.mark.asyncio
async def test_count_returns_total(enterprise_service, fake_collection):
    """count 返回 collection 记录数"""
    assert await enterprise_service.count() == 1


@pytest.mark.asyncio
async def test_user_count_requires_owner_id(user_service):
    """用户库 count 缺 owner_id 必须报错（隔离安全兜底，与 search 一致）"""
    with pytest.raises(ValueError):
        await user_service.count()


@pytest.mark.asyncio
async def test_user_count_filters_by_owner(user_service, fake_collection):
    """用户库 count 走 get 过滤统计个人数据，不返回全量"""
    result = await user_service.count(owner_id="usr_1")
    assert result == 1
    # get 必须带 owner_id 过滤，且只取 id（include=[]）
    assert fake_collection.get_calls[-1]["where"] == {"owner_id": "usr_1"}
    assert fake_collection.get_calls[-1]["include"] == []


@pytest.mark.asyncio
async def test_list_documents_groups_by_source(enterprise_service, fake_collection):
    """list_documents 返回按 source_doc_id 分组的溯源列表"""
    docs = await enterprise_service.list_documents()
    assert len(docs) == 1
    assert docs[0]["source_doc_id"] == "doc_001"
    assert docs[0]["chunks"] == 1