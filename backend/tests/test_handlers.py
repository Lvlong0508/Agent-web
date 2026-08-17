"""订阅侧业务 handler 单元测试：mock 输出队列与 ReplyState，验证行为与产出事件"""
import pytest

from app.services.chat.handlers import TitleCompletedHandler, VerdictHandler
from app.services.chat.reply_state import ReplyPhase, ReplyState
from app.services.chat.sse_serializer import SSEEvent


@pytest.mark.asyncio
async def test_title_handler_emits_when_nonempty():
    """标题非空：产出 title 事件（含标题文本）"""
    out = []
    handler = TitleCompletedHandler(out)
    await handler.handle({"type": "title.completed", "payload": {"title": "新标题"}})
    assert out == [SSEEvent(type="title", data={"title": "新标题"})]


@pytest.mark.asyncio
async def test_title_handler_skips_empty():
    """标题为空：不产出任何事件（避免无谓消息）"""
    out = []
    handler = TitleCompletedHandler(out)
    await handler.handle({"type": "title.completed", "payload": {"title": ""}})
    assert out == []


@pytest.mark.asyncio
async def test_verdict_retry_resets_and_emits_rewriting():
    """retry：清空待定回复进入重写轮，产出 rewriting 事件"""
    out = []
    state = ReplyState()
    state.pending_reply = "首轮残稿"
    handler = VerdictHandler(state, "fallback", out)
    await handler.handle({"type": "verifier.verdict", "payload": {"result": "retry"}})
    assert state.phase == ReplyPhase.REWRITING
    assert state.pending_reply == ""
    assert out == [SSEEvent(type="rewriting", data={"rewriting": True})]


@pytest.mark.asyncio
async def test_verdict_pass_promotes_reply():
    """pass：待定回复升格为最终版，产出 final 事件携带最终版"""
    out = []
    state = ReplyState()
    state.pending_reply = "你好"
    handler = VerdictHandler(state, "fallback", out)
    await handler.handle({"type": "verifier.verdict", "payload": {"result": "pass"}})
    assert state.full_response == "你好"
    assert out == [SSEEvent(type="final", data={"final": "你好"})]


@pytest.mark.asyncio
async def test_verdict_fail_uses_fallback():
    """fail：最终版为固定文案，产出 final 事件携带文案"""
    out = []
    state = ReplyState()
    handler = VerdictHandler(state, "小励出了点问题", out)
    await handler.handle({"type": "verifier.verdict", "payload": {"result": "fail"}})
    assert state.full_response == "小励出了点问题"
    assert out == [SSEEvent(type="final", data={"final": "小励出了点问题"})]


@pytest.mark.asyncio
async def test_verdict_unknown_result_noop():
    """未知判定：不转移状态、不产出事件（未来事件类型向后兼容）"""
    out = []
    state = ReplyState()
    handler = VerdictHandler(state, "fallback", out)
    await handler.handle({"type": "verifier.verdict", "payload": {"result": "unknown"}})
    assert state.phase == ReplyPhase.PENDING
    assert out == []


@pytest.mark.asyncio
async def test_verdict_missing_payload_noop():
    """payload 缺失：不报错、不转移状态、不产出事件（防御分支）"""
    out = []
    state = ReplyState()
    handler = VerdictHandler(state, "fallback", out)
    await handler.handle({"type": "verifier.verdict"})
    assert state.phase == ReplyPhase.PENDING
    assert out == []


@pytest.mark.asyncio
async def test_title_handler_missing_payload_skips():
    """payload 缺失：标题视为空，不产出事件（防御分支）"""
    out = []
    handler = TitleCompletedHandler(out)
    await handler.handle({"type": "title.completed"})
    assert out == []