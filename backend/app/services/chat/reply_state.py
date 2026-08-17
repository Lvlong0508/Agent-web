"""回复状态机：管理 pending_reply（待定回复）/ full_response（最终版）/ phase（阶段）。

背景：chat_stream 原先用闭包 + nonlocal 维护这些状态，无法脱离外层函数单独测试。
本模块用 Enum + 转移方法建模小状态机，状态机语义集中、可穷举测试。

状态语义：
- PENDING：首轮流式 token 累积中（验证通过前一律不推前端）
- REWRITING：verifier 判定 retry 后进入重写轮，重新累积待定回复
- FINAL：验证通过（full_response = pending_reply）
- FAILED：验证超限（full_response = 固定文案）

转移规则：PENDING/REWRITING（活动态）可接收 retry/pass/fail；
FINAL/FAILED（终态）再接收任何判定即抛 ValueError（编程错误，fail fast）。
"""

from dataclasses import dataclass
from enum import Enum


class ReplyPhase(Enum):
    """回复阶段枚举：终态为 FINAL / FAILED，活动态为 PENDING / REWRITING"""
    PENDING = "pending"      # 首轮待定回复累积中
    REWRITING = "rewriting"  # 重写轮待定回复累积中
    FINAL = "final"          # 验证通过，产出最终版
    FAILED = "failed"        # 验证超限，产出固定文案


@dataclass
class ReplyState:
    """回复状态机：持有待定回复与最终版，通过语义化方法完成状态转移。

    本类零外部依赖（只依赖标准库），可独立构造与穷举测试。
    """

    phase: ReplyPhase = ReplyPhase.PENDING
    pending_reply: str = ""   # 待定回复：验证通过前累积的 token
    full_response: str = ""   # 最终版：pass 时为 pending_reply，fail 时为固定文案

    def _ensure_active(self) -> None:
        """终态守卫：FINAL/FAILED 收到任何判定都是编程错误，抛 ValueError"""
        if self.phase in (ReplyPhase.FINAL, ReplyPhase.FAILED):
            raise ValueError(f"终态 {self.phase.value} 不能再接收判定")

    def on_retry(self) -> None:
        """verifier 判定 retry：进入重写轮并清空待定回复（重写轮重新累积）"""
        self._ensure_active()
        self.phase = ReplyPhase.REWRITING
        self.pending_reply = ""

    def on_pass(self) -> None:
        """verifier 判定 pass：待定回复升格为最终版（前端一次性推送）"""
        self._ensure_active()
        self.phase = ReplyPhase.FINAL
        self.full_response = self.pending_reply

    def on_fail(self, fallback: str) -> None:
        """verifier 判定 fail：用固定文案作为最终版"""
        self._ensure_active()
        self.phase = ReplyPhase.FAILED
        self.full_response = fallback
