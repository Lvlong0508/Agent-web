"""ChromaClient 测试：mock chromadb.HttpClient 与 httpx 请求，不连真实服务"""

import pytest
from unittest.mock import MagicMock, patch

from app.config.settings import settings
from app.middleware.chroma import ChromaClient


def _patch_httpx(status=200):
    """mock connect() 里的 httpx 探测/创建 database：
    status=200 视为 database 已存在（只探测），status=404 才会触发 POST 创建。
    返回 (fake_get, fake_post, ctx_get, ctx_post)，前两个供断言，后两个作为 context manager"""
    fake_get = MagicMock(return_value=MagicMock(status_code=status))
    fake_post = MagicMock(return_value=MagicMock(status_code=200))
    return (
        fake_get,
        fake_post,
        patch("app.middleware.chroma.httpx.get", fake_get),
        patch("app.middleware.chroma.httpx.post", fake_post),
    )


def _fake_collection(name, **kwargs):
    """构造一个假的 collection 对象（只验证被 get_or_create 到）"""
    col = MagicMock()
    col.name = name
    return col


def test_connect_creates_four_collections():
    """connect 建 4 个 collection，每个指定 cosine 距离度量，
    且 HttpClient 携带配置的 tenant/database（database 隔离来自 env）"""
    fake_client = MagicMock()
    fake_client.get_or_create_collection.side_effect = _fake_collection

    _, _, ctx_get, ctx_post = _patch_httpx()
    with ctx_get, ctx_post, patch(
        "app.middleware.chroma.chromadb.HttpClient", return_value=fake_client
    ) as mock_http:
        ChromaClient.connect()

    assert fake_client.get_or_create_collection.call_count == 4
    names = [c.kwargs["name"] for c in fake_client.get_or_create_collection.call_args_list]
    assert sorted(names) == ["kb_enterprise", "kb_skills", "kb_tools", "kb_user"]
    # 每个 collection 都带 cosine 距离度量（与 DashScope 归一化向量匹配）
    for call in fake_client.get_or_create_collection.call_args_list:
        assert call.kwargs["metadata"] == {"hnsw:space": "cosine"}
    # HttpClient 必须用配置的 tenant/database
    assert mock_http.call_args.kwargs["tenant"] == settings.CHROMA_TENANT
    assert mock_http.call_args.kwargs["database"] == settings.CHROMA_DATABASE


def test_connect_creates_database_if_missing():
    """database 不存在（GET 返回 404）时 connect 主动 POST 创建，保证隔离库存在"""
    fake_client = MagicMock()
    fake_client.get_or_create_collection.side_effect = _fake_collection

    _, fake_post, ctx_get, ctx_post = _patch_httpx(status=404)
    with ctx_get, ctx_post, patch(
        "app.middleware.chroma.chromadb.HttpClient", return_value=fake_client
    ):
        ChromaClient.connect()

    assert fake_post.called  # 探测 404 后必须发起创建


def test_connect_skips_create_when_database_exists():
    """database 已存在（GET 返回 200）时不应重复创建"""
    fake_client = MagicMock()
    fake_client.get_or_create_collection.side_effect = _fake_collection

    _, fake_post, ctx_get, ctx_post = _patch_httpx()
    with ctx_get, ctx_post, patch(
        "app.middleware.chroma.chromadb.HttpClient", return_value=fake_client
    ):
        ChromaClient.connect()

    assert not fake_post.called


def test_get_collection_routes_by_kb_type():
    """get_collection 按 kb_type 路由到对应 collection"""
    fake_client = MagicMock()
    fake_client.get_or_create_collection.side_effect = _fake_collection
    _, _, ctx_get, ctx_post = _patch_httpx()
    with ctx_get, ctx_post, patch(
        "app.middleware.chroma.chromadb.HttpClient", return_value=fake_client
    ):
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
    _, _, ctx_get, ctx_post = _patch_httpx()
    with ctx_get, ctx_post, patch(
        "app.middleware.chroma.chromadb.HttpClient", return_value=fake_client
    ):
        ChromaClient.connect()
    with pytest.raises(ValueError):
        ChromaClient.get_collection("invalid")