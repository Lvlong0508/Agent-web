"""planner 节点：LLM 意图识别 + 目标分析 + 路线规划，带三级降级。

职责（spec 2026-08-21）：
- 本文件只做**编排**：调 LLM + 降级 + 状态组装 + 输出清洗
- 提示词素材在 agent/prompts/planner.py，content 组装在 agent/context/planner.py
- 编排层经 agent.context 包级 __init__ 导入，不深层 import（import 边界）
"""

import asyncio
import json
import logging
import time

from langchain_core.messages import SystemMessage
from pydantic import ValidationError

from app.config import agent_settings
from app.services.agent.capabilities.planner.events import (
    PLANNER_COMPLETED_EVENT,
    PLANNER_FAILED_EVENT,
)
from app.services.agent.capabilities.planner.schema import PlannerOutput
from app.services.agent.context import (
    HISTORY_REFERENCE_MARKER,   # 经 context 包级导出（对齐 spec §3.5）
    build_planner_messages,     # content 组装：生成发给 planner 的消息列表
    format_plan_system_message, # content 组装：规划 → 注入 agent 的 SystemMessage 内容
)
from app.services.agent.events import emit
from app.services.agent.llm import create_llm

logger = logging.getLogger(__name__)

# 规划 SystemMessage 的 name 标记：rewrite 构建时据此过滤、落库可追溯
PLANNER_MARKER = "planner"


def _edit_distance(a: str, b: str) -> int:
    """计算两字符串的编辑距离（Levenshtein），供工具名模糊匹配。

    实现：经典动态规划。工具名长度通常 <30，O(n*m) 足够。
    """
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(
                prev[j] + 1,          # 删除
                cur[j - 1] + 1,       # 插入
                prev[j - 1] + (ca != cb),  # 替换
            ))
        prev = cur
    return prev[-1]


def resolve_tool_name(raw_name: str, valid_names: list[str]) -> str | None:
    """工具名容错解析：精确匹配 → 编辑距离 ≤2 模糊纠正 → 无法匹配返回 None。

    None 表示该工具名不可信，调用方应丢弃它并让 agent 自主选择工具。
    """
    if raw_name in valid_names:
        return raw_name
    # 编辑距离 ≤2 的最近匹配自动纠正（小模型常见拼写偏差）
    best = None
    best_dist = 3  # >2 视为不可信
    for name in valid_names:
        dist = _edit_distance(raw_name, name)
        if dist < best_dist:
            best = name
            best_dist = dist
    return best if best_dist <= 2 else None


def sanitize_required_tools(required_tools: list[str], valid_names: list[str]) -> list[str]:
    """清洗 planner 输出的工具名列表：逐名容错解析，无法匹配的丢弃。

    返回清洗后的可信工具名列表（可能短于输入，但不会引入非法名）。
    属编排层输出后处理（处理 LLM 返回的结果，不是发给 planner 的上下文）。
    """
    result = []
    for raw in required_tools:
        resolved = resolve_tool_name(raw, valid_names)
        if resolved is not None and resolved not in result:
            result.append(resolved)
    return result


def _extract_user_input(messages) -> str:
    """从消息列表提取本轮用户问题（最后一条无标记 HumanMessage）。

    planner 在 START 后最先执行，state["messages"] 是首轮上下文：
    [System, 历史参考块(HumanMessage, name=history_reference), 本轮问题(HumanMessage)]。
    历史参考块与本轮问题都是 HumanMessage，靠 name 标记区分（与 rewrite/verdict 同法）。
    """
    for m in reversed(messages):
        if hasattr(m, "name") and getattr(m, "name", None) != HISTORY_REFERENCE_MARKER:
            if m.type == "human":
                return m.content
    return ""


def make_planner_node(tools: list | None = None):
    """构造 planner 节点：意图识别 + 目标分析 + 路线规划。

    tools：可用工具列表（生成动态工具清单，供 planner 选择）。
    """

    async def planner_node(state: dict, llm=None) -> dict:
        """planner 节点主体：调用 LLM 产出规划 JSON，失败降级为跳过。

        llm：可注入的 LLM 实例（测试用）；缺省用 agent_settings 配置创建。
        """
        start = time.monotonic()
        # 用独立规划模型（查注册表 planner 条目：非流式 + 思考开），不占用 agent 主模型
        if llm is None:
            llm = create_llm(
                alias=agent_settings.PLANNER_MODEL_ALIAS,
                streaming=False,
                enable_thinking=agent_settings.PLANNER_THINKING,
            )
        user_input = _extract_user_input(state.get("messages", []))
        tools_list = tools or []
        # 技能索引从 state 读取（chat_stream 已检索 top-K 注入），不再自调全量；
        # 缺省空串（无技能/降级时 skill 机制透明）
        skills_index = state.get("skills_index", "")
        # content 组装委托 context 层：生成 [SystemMessage(提示词), HumanMessage(用户本轮)]
        messages = build_planner_messages(user_input, tools_list, skills_index)
        valid_names = [t.name for t in tools_list]

        try:
            # 超时由 asyncio.wait_for 保障：模型卡住也能打断（spec 4.3）
            response = await asyncio.wait_for(
                llm.ainvoke(messages),
                timeout=agent_settings.PLANNER_TIMEOUT,
            )
            content = getattr(response, "content", "")
            if isinstance(content, str) and content:
                data = json.loads(content)
            else:
                data = None
            if not isinstance(data, dict):
                raise json.JSONDecodeError("非 dict", content, 0)
            plan = PlannerOutput(**data)
        except asyncio.TimeoutError:
            cost_time_ms = int((time.monotonic() - start) * 1000)
            logger.warning("planner 超时（%.1fs），降级跳过", agent_settings.PLANNER_TIMEOUT)
            emit(PLANNER_FAILED_EVENT, "planner", {"reason": "timeout", "cost_time_ms": cost_time_ms}, status="failed")
            return {
                "planner_result": None,
                "planner_status": "failed",
                "planner_reason": "timeout",
                "messages": [],
                "planner_cost_ms": cost_time_ms,
            }
        except (json.JSONDecodeError, TypeError) as e:
            cost_time_ms = int((time.monotonic() - start) * 1000)
            logger.warning("planner 输出解析失败，降级跳过：%s", e)
            emit(PLANNER_FAILED_EVENT, "planner", {"reason": "json_parse_error", "cost_time_ms": cost_time_ms}, status="failed")
            return {
                "planner_result": None,
                "planner_status": "failed",
                "planner_reason": "json_parse_error",
                "messages": [],
                "planner_cost_ms": cost_time_ms,
            }
        except ValidationError as e:
            cost_time_ms = int((time.monotonic() - start) * 1000)
            logger.warning("planner 输出 schema 校验失败，降级跳过：%s", e)
            emit(PLANNER_FAILED_EVENT, "planner", {"reason": "schema_invalid", "cost_time_ms": cost_time_ms}, status="failed")
            return {
                "planner_result": None,
                "planner_status": "failed",
                "planner_reason": "schema_invalid",
                "messages": [],
                "planner_cost_ms": cost_time_ms,
            }
        except Exception as e:
            # LLM 调用本身抛出的异常（网络错误 / openai 403 无权限 / 配额等）：
            # planner 必须对主流程透明（实测：planner 模型无权限时 openai 抛
            # PermissionDeniedError，不捕获会直接把 500 抛给整条请求）
            cost_time_ms = int((time.monotonic() - start) * 1000)
            logger.warning("planner LLM 调用失败，降级跳过：%s", e)
            emit(PLANNER_FAILED_EVENT, "planner", {"reason": "llm_error", "cost_time_ms": cost_time_ms}, status="failed")
            return {
                "planner_result": None,
                "planner_status": "failed",
                "planner_reason": "llm_error",
                "messages": [],
                "planner_cost_ms": cost_time_ms,
            }

        # 清洗工具名：planner 可能输出近似名，容错解析后丢弃非法名（spec 7.2）
        cleaned_tools = sanitize_required_tools(plan.required_tools, valid_names)
        plan = plan.model_copy(update={"required_tools": cleaned_tools})
        result = plan.model_dump()

        # 低置信度：仍注入规划但标注 skipped（agent 自主执行）
        if plan.confidence < agent_settings.PLANNER_CONFIDENCE_THRESHOLD:
            cost_time_ms = int((time.monotonic() - start) * 1000)
            emit(PLANNER_COMPLETED_EVENT, "planner",
                 {"status": "skipped", "intent_l1": plan.intent_l1,
                  "confidence": plan.confidence, "cost_time_ms": cost_time_ms},
                 status="progress")
            return {
                "planner_result": result,
                "planner_status": "skipped",
                "planner_reason": "low_confidence",
                "messages": [SystemMessage(
                    content=format_plan_system_message(plan) + "\n（置信度较低，仅供参考）",
                    name=PLANNER_MARKER,
                )],
                "planner_cost_ms": cost_time_ms,
            }

        # 正常路径：注入规划 SystemMessage（name=planner 标记）
        cost_time_ms = int((time.monotonic() - start) * 1000)
        emit(PLANNER_COMPLETED_EVENT, "planner",
             {"status": "planned", "intent_l1": plan.intent_l1,
              "confidence": plan.confidence, "cost_time_ms": cost_time_ms},
             status="completed")
        return {
            "planner_result": result,
            "planner_status": "planned",
            "planner_reason": "",
            "messages": [SystemMessage(
                content=format_plan_system_message(plan),
                name=PLANNER_MARKER,
            )],
            "planner_cost_ms": cost_time_ms,
        }

    return planner_node
