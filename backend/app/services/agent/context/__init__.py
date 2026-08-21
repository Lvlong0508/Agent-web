"""agent 上下文组装包：把提示词 + 动态信息组装成发给 LLM 的消息列表。

- agent.py：build_agent_messages（agent 首轮上下文）+ HISTORY_REFERENCE_MARKER
- planner.py：build_planner_messages（planner 上下文）+ format_plan_system_message
编排层只能经本包 __init__ 导入，禁止深层 import（spec §3.5 import 边界）
"""

from app.services.agent.context.agent import (
    HISTORY_REFERENCE_MARKER,
    build_agent_messages,
)
from app.services.agent.context.planner import (
    build_planner_messages,
    format_plan_system_message,
)

__all__ = [
    "HISTORY_REFERENCE_MARKER",
    "build_agent_messages",
    "build_planner_messages",
    "format_plan_system_message",
]
