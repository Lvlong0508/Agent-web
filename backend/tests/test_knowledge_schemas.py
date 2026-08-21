"""知识库 schema 测试：文档块字段模型与请求/响应结构"""

import pytest
from pydantic import ValidationError

from app.schemas.knowledge import (
    ChunkAddRequest,
    ChunkMetadata,
    ChunkSearchRequest,
    ChunkSearchResponse,
    SearchResultItem,
)


def test_chunk_metadata_valid():
    """合法 metadata：5 字段齐备，kb_type 取 enterprise"""
    meta = ChunkMetadata(
        kb_type="enterprise",
        owner_id="global",
        source_doc_id="doc_001",
        source_file="手册v3.pdf",
        chunk_index=2,
    )
    assert meta.kb_type == "enterprise"
    assert meta.owner_id == "global"
    assert meta.chunk_index == 2


def test_chunk_metadata_invalid_kb_type():
    """非法 kb_type 抛 ValidationError"""
    with pytest.raises(ValidationError):
        ChunkMetadata(
            kb_type="invalid",
            owner_id="global",
            source_doc_id="doc_001",
            chunk_index=0,
        )


def test_chunk_metadata_defaults():
    """source_file 默认空串、chunk_index 默认 0"""
    meta = ChunkMetadata(kb_type="user", owner_id="usr_1", source_doc_id="doc_1")
    assert meta.source_file == ""
    assert meta.chunk_index == 0


def test_chunk_add_request():
    """批量写入请求：一篇文章的多个正文块"""
    req = ChunkAddRequest(
        kb_type="enterprise",
        owner_id="global",
        source_doc_id="doc_001",
        source_file="手册v3.pdf",
        chunks=["块1正文", "块2正文"],
    )
    assert len(req.chunks) == 2
    assert req.source_file == "手册v3.pdf"


def test_chunk_add_request_requires_chunks():
    """chunks 不能为空列表"""
    with pytest.raises(ValidationError):
        ChunkAddRequest(
            kb_type="enterprise",
            owner_id="global",
            source_doc_id="doc_001",
            chunks=[],
        )


def test_chunk_search_request_defaults():
    """检索请求：top_k 默认 5"""
    req = ChunkSearchRequest(kb_type="user", query="怎么报销差旅费")
    assert req.top_k == 5
    assert req.kb_type == "user"


def test_search_response_build():
    """检索响应：组装溯源信息"""
    resp = ChunkSearchResponse(
        items=[
            SearchResultItem(
                content="报销流程：先填单后审批",
                score=0.92,
                source_file="手册v3.pdf",
                chunk_index=3,
                source_doc_id="doc_001",
                kb_type="enterprise",
            )
        ]
    )
    assert resp.items[0].score == 0.92
    assert resp.items[0].source_doc_id == "doc_001"