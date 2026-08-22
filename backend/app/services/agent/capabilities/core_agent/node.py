"""core_agent 主循环节点：agent 推理节点 + 工具条件路由。

注意：generate_title_node 属于 title 能力，在 capabilities/title/node.py 中。
"""

from typing import Literal

from app.config import agent_settings
from app.services.agent.llm import create_llm
from app.services.agent.capabilities.core_agent.state import AgentState
# 重写轮上下文助手属于 verifier 能力（重写指令由质检反馈驱动），故依赖
# capabilities/verifier/context/rewrite 而非旧的 services/agent/context 目录
from app.services.agent.capabilities.verifier.context.rewrite import build_rewrite_messages


def should_continue(state: AgentState) -> Literal["tools", "verifier"]:
    """条件边：最后一条消息含工具调用则进 tools 节点，否则进 verifier 验证"""
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return "verifier"


def make_agent_node(tools):
    """构造 agent 推理节点：把消息流（已含系统提示词）交给 LLM 生成回复。

    tools：绑定给 LLM 的工具列表
    """

    # agent 节点：把消息流（已含系统提示词）交给 LLM 生成回复
    # （stream_mode 会自动流式输出 token）
    async def agent_node(state) -> dict:
        # 重写轮判断：verifier 未通过时 verification_feedback 非空。
        # 重写轮用非流式 LLM：首轮流式 token 已推给前端，重写轮的 token 若再
        # 逐字推送会造成内容闪烁，故静默生成、验证通过后由 chat_service 推送最终版
        feedback = state.get("verification_feedback", "")
        is_rewrite = bool(feedback)
        llm = create_llm(
            alias=state.get("model") or agent_settings.MODEL_OLLAMA,
            streaming=not is_rewrite,
            enable_thinking=state.get("thinking", False),
        )
        # 只在绑定了工具时才 bind_tools：空列表绑定对不支持工具的消息模型会报错
        if tools:
            # bind_tools 把工具 schema 暴露给 LLM，它才能在回复中发起工具调用；
            # 随后条件边 should_continue 检测到 tool_calls 就走 tools 节点执行
            llm = llm.bind_tools(tools)
        messages = state["messages"]
        if is_rewrite:
            # 把验证反馈注入重写指令，agent 据此重新组织语言直接作答。
            # 指令刻意不写"你上一条未通过校验"这类过程性说明：写了会让 agent
            # 在回复里道歉解释（实测出现"非常抱歉，刚才的回复确实出现了严重的
            # 错误"），而重写结果是要展示给用户的最终版，话术必须自然衔接。
            # 重写轮消息必须剔除被否决的旧候选回复（只留 系统提示词 + 本轮用户
            # 问题 + 重写指令）：否则模型看到旧答案会延续文本而不重新调用工具
            # （实测 bug：质检纠正后助手依然不肯调工具，连续输出同样的错误结论）
            messages = build_rewrite_messages(messages, feedback)
        response = await llm.ainvoke(messages)
        return {"messages": [response]}

    return agent_node
