"""ChromaClient 测试：mock chromadb.HttpClient，不连真实服务"""

import pytest
from unittest.mock import MagicMock, patch

from app.middleware.chroma import ChromaClient


def _fake_collection(name, **kwargs):
    """构造一个假的 collection 对象（只验证被 get_or_create 到）"""
    col = MagicMock()
    col.name = name
    return col


def test_connect_creates_four_collections():
    """connect 建 4 个 collection，每个指定 cosine 距离度量"""
    fake_client = MagicMock()
    fake_client.get_or_create_collection.side_effect = _fake_collection

    with patch("app.middleware.chroma.chromadb.HttpClient", return_value=fake_client):
        ChromaClient.connect()

    assert fake_client.get_or_create_collection.call_count == 4
    names = [c.kwargs["name"] for c in fake_client.get_or_create_collection.call_args_list]
    assert sorted(names) == ["kb_enterprise", "kb_skills", "kb_tools", "kb_user"]
    # 每个 collection 都带 cosine 距离度量（与 DashScope 归一化向量匹配）
    for call in fake_client.get_or_create_collection.call_args_list:
        assert call.kwargs["metadata"] == {"hnsw:space": "cosine"}


def test_get_collection_routes_by_kb_type():
    """get_collection 按 kb_type 路由到对应 collection"""
    fake_client = MagicMock()
    fake_client.get_or_create_collection.side_effect = _fake_collection
    with patch("app.middleware.chroma.chromadb.HttpClient", return_value=fake_client):
        ChromaClient.connect()

    col = ChromaClient.get_collection("user")
    assert col.name == "kb_user"


def test_get_collection_before_connect_raises():
    """未 connect 就 get_collection 应报错（提示先初始化）"""
    # 确保初始状态干净
    ChromaClient.close()
    with pytest.raises(RuntimeError):
        ChromaClient.get_collection("user")


def test_get_collection_unknown_type_raises():
    """未知 kb_type 应报 ValueError"""
    fake_client = MagicMock()
    fake_client.get_or_create_collection.side_effect = _fake_collection
    with patch("app.middleware.chroma.chromadb.HttpClient", return_value=fake_client):
        ChromaClient.connect()
    with pytest.raises(ValueError):
        ChromaClient.get_collection("invalid")