"""agent 模块公共出口：外部调用方只从这里导入公共 API。

设计要点（spec 2026-08-17-agent-import-optimization-design）：
- 对外单一入口：chat_service / 测试统一从本包导入，不再深入内部子包路径
- __all__ 即包的文档化 API 清单：新增能力若需对外暴露，在此追加一行
- 只重导出公共符号，不暴露 make_agent_node / make_verifier_node / _validate_* 等内部实现
- 两个下划线函数（_decide_verification / _generate_title_if_empty）因测试仍
  从本出口依赖它们而保留，非出口泄漏内部实现
"""

from app.services.agent.llm import create_llm
from app.services.agent.tools import get_tools
from app.services.agent.capabilities.core_agent.node import should_continue
from app.services.agent.capabilities.core_agent.state import AgentState
from app.services.agent.capabilities.title.events import TITLE_COMPLETED_EVENT
from app.services.agent.capabilities.title.node import _generate_title_if_empty
from app.services.agent.capabilities.verifier.context.verdict import Verdict
from app.services.agent.capabilities.verifier.events import VERIFIER_VERDICT_EVENT
from app.services.agent.capabilities.verifier.node import (
    MAX_VERIFY_RETRIES,
    _decide_verification,
    route_after_verify,
)
from app.services.agent.capabilities.planner.events import (
    PLANNER_COMPLETED_EVENT,
    PLANNER_FAILED_EVENT,
)
from app.services.agent.context.agent import build_agent_messages
from app.services.agent.events import CapabilityEvent, EventRouter, serialize_message
from app.services.agent.prompts import REPLY_ON_VERIFY_FAILED
from app.services.agent.registry import build_agent_graph
from app.services.agent.skills import get_skills_index_prompt

__all__ = [
    "AgentState",
    "CapabilityEvent",
    "EventRouter",
    "MAX_VERIFY_RETRIES",
    "REPLY_ON_VERIFY_FAILED",
    "TITLE_COMPLETED_EVENT",
    "VERIFIER_VERDICT_EVENT",
    "Verdict",
    "PLANNER_COMPLETED_EVENT",
    "PLANNER_FAILED_EVENT",
    "_decide_verification",
    "_generate_title_if_empty",
    "build_agent_graph",
    "build_agent_messages",
    "create_llm",
    "get_skills_index_prompt",  # 技能索引工厂：chat_service 经包出口注入
    "get_tools",
    "route_after_verify",
    "serialize_message",
    "should_continue",
]
