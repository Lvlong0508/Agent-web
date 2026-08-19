"""verifier 能力节点：质检判定候选回复是否准确，决定结束/重写/报错"""

import logging
from typing import Literal

from langgraph.graph import END

from app.config.agent_settings import agent_settings
from app.services.agent.llm import create_llm
from app.services.agent.capabilities.verifier.context.verdict import (
    Verdict,
    build_verdict_input,
    run_verdict,
)
from app.services.agent.capabilities.verifier.events import VERIFIER_VERDICT_EVENT
from app.services.agent.events import emit

logger = logging.getLogger(__name__)

# 回复不准确时的最大重写次数：验证->重写->再验证循环的上限，防止无限循环拖慢响应
MAX_VERIFY_RETRIES = 2


def route_after_verify(state) -> Literal["agent", END]:
    """条件边：验证反馈非空（需重写）回 agent，否则（通过或超限）结束"""
    if state.get("verification_feedback"):
        return "agent"
    return END


def _decide_verification(verdict: Verdict, state: dict) -> dict:
    """根据验证结论与当前重写次数决定后续状态（纯函数，便于单测）"""
    rewrite_count = state.get("rewrite_count", 0)
    # 准确：清空反馈字段，result=pass，走 END
    if verdict.is_accurate:
        return {
            "verification_feedback": "",
            "verification_result": "pass",
            "rewrite_count": rewrite_count,
        }
    # 不准确但未超限：反馈写入状态、计数+1，result=retry，回 agent 重写
    if rewrite_count < MAX_VERIFY_RETRIES:
        return {
            "verification_feedback": verdict.issues,
            "verification_result": "retry",
            "rewrite_count": rewrite_count + 1,
        }
    # 已达上限：清空反馈、result=fail，走 END（chat_service 检测到 fail 返回固定文案）
    return {
        "verification_feedback": "",
        "verification_result": "fail",
        "rewrite_count": rewrite_count,
    }


def make_verifier_node(tools: list | None = None):
    """构造质检节点：判定 agent 候选回复是否准确，决定结束/重写/报错。

    tools：可用工具列表（质检员据此判断"没有可用工具"的说法真伪）
    """

    # verifier 节点：判定 agent 候选回复是否准确，决定结束/重写/报错
    async def verifier_node(state) -> dict:
        llm = create_llm(
            alias=state.get("model") or agent_settings.MODEL_OLLAMA,
            streaming=False,
            # 验证不需要深度思考：关闭思考模式让判定快速返回，避免十几秒思考拖慢
            enable_thinking=False,
            # 限制输出长度：质检判定只需短结论（is_accurate + issues），
            # 防止模型在 issues 里写大段自我推敲导致输出过长/截断、判定不稳定
            max_tokens=600,
        )
        try:
            # 构造发给质检员的输入（同时拿到序列化版本，供全链路记录）。
            # 传入精纯历史参考：质检员理解基于历史记忆的回复（如称呼用户名），
            # 又不受工具轮/重写轮噪音干扰。
            # 传入可用工具名列表：质检员据此判断"没有可用工具"的说法真伪，
            # 杜绝助手谎称无工具逃避（工具列表来自图构建时绑定的 tools 闭包）
            available_tools = [t.name for t in tools] if tools else []
            _, verdict_input = build_verdict_input(
                state["messages"], state.get("history_reference"), available_tools,
                planner_result=state.get("planner_result"),
            )
            verdict = await run_verdict(
                llm, state["messages"], state.get("history_reference"), available_tools,
                planner_result=state.get("planner_result"),
            )
            # 质检判定一行结果：短小，供实时确认"过没过"；细节（候选内容/工具
            # 结果）已全量落库到 agent_runs（verdict_input/verdict），终端不重复。
            # DEBUG 级别：默认不刷屏，排障（临时开 DEBUG）时可看
            logger.debug("verifier 判定: is_accurate=%s issues=%r", verdict.is_accurate, verdict.issues)
        except Exception as e:
            # 验证器调用失败（网络异常/模型不支持结构化输出等）不能拖垮主流程：
            # 与标题节点"失败静默跳过"同理，降级为通过（接受候选回复），
            # 保证用户仍能拿到 agent 已产出的合格回复
            logger.warning("验证节点调用失败，降级为通过：%s", e)
            # 降级也发出事件，保证 chat_service 能正常走 pass 推送最终版
            emit(VERIFIER_VERDICT_EVENT, "verifier", {"result": "pass"}, status="failed")
            return {
                "verification_feedback": "",
                "verification_result": "pass",
                "rewrite_count": state.get("rewrite_count", 0),
                # 降级时无真实判定，用占位 verdict 保持链路记录字段一致
                "verdict": {"is_accurate": True, "issues": f"验证器调用失败，降级通过：{e}"},
                "verdict_input": [],
            }
        decision = _decide_verification(verdict, state)
        # 把质检员的结构化判定与其输入一并写入状态，供上层全链路记录
        decision["verdict"] = verdict.model_dump()
        decision["verdict_input"] = verdict_input
        # 发出质检结果事件：chat_service 经 EventRouter 订阅后决定 pass/retry/fail
        emit(VERIFIER_VERDICT_EVENT, "verifier", {"result": decision["verification_result"]}, status="completed")
        return decision

    return verifier_node
