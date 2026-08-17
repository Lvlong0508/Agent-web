"""ReplyState 状态机单元测试：穷举合法转移与非法转移"""
import pytest

from app.services.chat.reply_state import ReplyPhase, ReplyState


def test_initial_state():
    """初始状态：PENDING 阶段，待定回复与最终版均为空"""
    state = ReplyState()
    assert state.phase == ReplyPhase.PENDING
    assert state.pending_reply == ""
    assert state.full_response == ""


def test_on_retry_from_pending():
    """PENDING 收到 retry：进入 REWRITING 并清空待定回复"""
    state = ReplyState()
    state.pending_reply = "首轮残稿"
    state.on_retry()
    assert state.phase == ReplyPhase.REWRITING
    assert state.pending_reply == ""


def test_on_retry_from_rewriting():
    """REWRITING 再次 retry：仍可重写（verifier 允许多轮）"""
    state = ReplyState(phase=ReplyPhase.REWRITING, pending_reply="重写残稿")
    state.on_retry()
    assert state.phase == ReplyPhase.REWRITING
    assert state.pending_reply == ""


def test_on_pass_from_pending():
    """PENDING 验证通过：待定回复升格为最终版，进入 FINAL"""
    state = ReplyState()
    state.pending_reply = "你好"
    state.on_pass()
    assert state.phase == ReplyPhase.FINAL
    assert state.full_response == "你好"


def test_on_pass_from_rewriting():
    """REWRITING 验证通过：重写后的待定回复升格为最终版"""
    state = ReplyState(phase=ReplyPhase.REWRITING, pending_reply="最终版回复")
    state.on_pass()
    assert state.phase == ReplyPhase.FINAL
    assert state.full_response == "最终版回复"


def test_on_fail_sets_fallback():
    """fail：使用固定文案作为最终版，进入 FAILED"""
    state = ReplyState()
    state.on_fail("小励出了点问题")
    assert state.phase == ReplyPhase.FAILED
    assert state.full_response == "小励出了点问题"


@pytest.mark.parametrize("phase", [ReplyPhase.FINAL, ReplyPhase.FAILED])
@pytest.mark.parametrize("method", ["on_retry", "on_pass", "on_fail"])
def test_terminal_states_reject_transition(phase, method):
    """终态（FINAL/FAILED）再收到任何判定必须抛 ValueError（fail fast）"""
    state = ReplyState(phase=phase, pending_reply="x", full_response="y")
    with pytest.raises(ValueError):
        if method == "on_fail":
            state.on_fail("fallback")
        else:
            getattr(state, method)()


def test_retry_clears_pending_but_keeps_full_response():
    """retry 只清待定回复，不影响已产生的最终版（pass 前 full_response 为空）"""
    state = ReplyState()
    state.pending_reply = "残稿"
    state.on_retry()
    assert state.full_response == ""
