"""DashScopeEmbedder 测试：mock OpenAIEmbeddings，不调用真实 API"""

import pytest
from unittest.mock import MagicMock, patch

from app.services.knowledge.embedder import DashScopeEmbedder


@pytest.fixture
def fake_embeddings():
    """伪 embedding 客户端：embed_documents 返回与输入条数相同的固定向量"""
    emb = MagicMock()
    emb.embed_documents.side_effect = lambda texts: [
        [0.1, 0.2, 0.3] for _ in texts
    ]
    return emb


@pytest.mark.asyncio
async def test_batch_embed_splits_over_batch_size(fake_embeddings):
    """超过 batch_size 时自动分批调用，向量顺序与输入一一对应"""
    embedder = DashScopeEmbedder(embeddings=fake_embeddings, batch_size=3)
    texts = ["a", "b", "c", "d", "e"]  # 5 条 -> 分 3+2 两批

    vectors = await embedder.batch_embed(texts)

    assert len(vectors) == 5
    # embed_documents 被调 2 次（3 条 + 2 条）
    calls = [c.args[0] for c in fake_embeddings.embed_documents.call_args_list]
    assert len(calls) == 2
    assert calls[0] == ["a", "b", "c"]
    assert calls[1] == ["d", "e"]


@pytest.mark.asyncio
async def test_batch_embed_single_batch_within_limit(fake_embeddings):
    """条数不超过 batch_size 时只调一次"""
    embedder = DashScopeEmbedder(embeddings=fake_embeddings, batch_size=10)
    vectors = await embedder.batch_embed(["only"])

    assert len(vectors) == 1
    assert fake_embeddings.embed_documents.call_count == 1


@pytest.mark.asyncio
async def test_batch_embed_empty_input():
    """空列表直接返回空，不调 API"""
    emb = MagicMock()
    embedder = DashScopeEmbedder(embeddings=emb, batch_size=10)
    vectors = await embedder.batch_embed([])

    assert vectors == []
    emb.embed_documents.assert_not_called()


@pytest.mark.asyncio
async def test_batch_embed_uses_to_thread():
    """同步 embedding 调用应在线程池执行，避免阻塞事件循环"""
    emb = MagicMock()
    emb.embed_documents.return_value = [[1.0, 2.0]]
    embedder = DashScopeEmbedder(embeddings=emb, batch_size=10)

    with patch("app.services.knowledge.embedder.asyncio.to_thread") as mock_thread:
        mock_thread.return_value = [[1.0, 2.0]]
        await embedder.batch_embed(["x"])
        mock_thread.assert_called_once()