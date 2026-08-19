"""planner 节点：LLM 意图识别 + 目标分析 + 路线规划，带三级降级。

设计要点（spec 第 8/11 节）：
- 用注册表 planner 条目（agent_settings.PLANNER_MODEL_ALIAS）非流式调用，开启思考模式
- 输出必须解析为 PlannerOutput；任何失败（JSON/schema/超时）降级为跳过，
  对主流程完全透明（planner_result=None，不注入规划消息）
- 低置信度：仍注入规划但状态 skipped（agent 自主执行）
- 规划 SystemMessage 带 name=planner 标记：rewrite 据此过滤、落库可追溯
"""

import asyncio
import json
import logging
import time

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from app.config.agent_settings import agent_settings
from app.services.agent.capabilities.planner.events import (
    PLANNER_COMPLETED_EVENT,
    PLANNER_FAILED_EVENT,
)
from app.services.agent.capabilities.planner.prompts import build_planner_prompt
from app.services.agent.capabilities.planner.schema import PlannerOutput
from app.services.agent.capabilities.planner.tool_listing import sanitize_required_tools
from app.services.agent.context.agent import HISTORY_REFERENCE_MARKER
from app.services.agent.events import emit
from app.services.agent.llm import create_llm
from app.services.agent.skills import get_skills_index_prompt

logger = logging.getLogger(__name__)

# 规划 SystemMessage 的 name 标记：rewrite 构建时据此过滤、落库可追溯
PLANNER_MARKER = "planner"


def _format_plan_system_message(plan: PlannerOutput) -> str:
    """把规划格式化为注入 agent 上下文的 SystemMessage 内容"""
    steps_desc = "\n".join(
        f"  {s.step_id}. {s.action}"
        + (f"（建议工具：{', '.join(s.suggested_tools)}）" if s.suggested_tools else "")
        for s in plan.plan_steps
    )
    return (
        "【执行规划参考】\n"
        f"意图：{plan.intent_l1}/{plan.intent_l2}\n"
        f"目标：{plan.goal}\n"
        f"步骤：\n{steps_desc}\n"
        f"推荐工具：{', '.join(plan.required_tools) or '无（自主决定）'}\n"
        f"推荐技能：{', '.join(plan.required_skills) or '无'}\n"
        f"置信度：{plan.confidence}\n"
        "注意：以上为参考规划，你可根据实际情况调整，但不得偏离用户核心目标。"
    )


def _extract_user_input(messages) -> str:
    """从消息列表提取本轮用户问题（最后一条无标记 HumanMessage）。

    planner 在 START 后最先执行，state["messages"] 是首轮上下文：
    [System, 历史参考块(HumanMessage, name=history_reference), 本轮问题(HumanMessage)]。
    历史参考块与本轮问题都是 HumanMessage，靠 name 标记区分（与 rewrite/verdict 同法）。
    """
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            if getattr(m, "name", None) != HISTORY_REFERENCE_MARKER:
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
        # 用独立规划模型（查注册表 planner 条目：非流式 + 思考开），不占用 agent 主模型。
        # 模型/厂商由注册表决定，PLANNER_THINKING 仍保留为运行时覆盖开关
        if llm is None:
            llm = create_llm(
                alias=agent_settings.PLANNER_MODEL_ALIAS,
                streaming=False,
                enable_thinking=agent_settings.PLANNER_THINKING,
            )
        user_input = _extract_user_input(state.get("messages", []))
        tools_list = tools or []
        prompt = build_planner_prompt(
            user_input,
            tools_list,
            get_skills_index_prompt(),
        )
        valid_names = [t.name for t in tools_list]

        try:
            # 超时由 asyncio.wait_for 保障：模型卡住也能打断（spec 4.3）
            response = await asyncio.wait_for(
                llm.ainvoke([SystemMessage(content=prompt)]),
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
            logger.warning("planner 超时（%.1fs），降级跳过", agent_settings.PLANNER_TIMEOUT)
            emit(PLANNER_FAILED_EVENT, "planner", {"reason": "timeout"}, status="failed")
            return {
                "planner_result": None,
                "planner_status": "failed",
                "planner_reason": "timeout",
                "messages": [],
            }
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("planner 输出解析失败，降级跳过：%s", e)
            emit(PLANNER_FAILED_EVENT, "planner", {"reason": "json_parse_error"}, status="failed")
            return {
                "planner_result": None,
                "planner_status": "failed",
                "planner_reason": "json_parse_error",
                "messages": [],
            }
        except ValidationError as e:
            logger.warning("planner 输出 schema 校验失败，降级跳过：%s", e)
            emit(PLANNER_FAILED_EVENT, "planner", {"reason": "schema_invalid"}, status="failed")
            return {
                "planner_result": None,
                "planner_status": "failed",
                "planner_reason": "schema_invalid",
                "messages": [],
            }

        # 清洗工具名：planner 可能输出近似名，容错解析后丢弃非法名（spec 7.2）
        cleaned_tools = sanitize_required_tools(plan.required_tools, valid_names)
        # 清洗后的工具名回写 plan（plan 是 pydantic 对象，用 model_copy 更新）
        plan = plan.model_copy(update={"required_tools": cleaned_tools})
        result = plan.model_dump()

        # 低置信度：仍注入规划但标注 skipped（agent 自主执行）
        if plan.confidence < agent_settings.PLANNER_CONFIDENCE_THRESHOLD:
            emit(PLANNER_COMPLETED_EVENT, "planner",
                 {"status": "skipped", "intent_l1": plan.intent_l1,
                  "confidence": plan.confidence, "cost_time_ms": int((time.monotonic() - start) * 1000)},
                 status="progress")
            return {
                "planner_result": result,
                "planner_status": "skipped",
                "planner_reason": "low_confidence",
                "messages": [SystemMessage(
                    content=_format_plan_system_message(plan) + "\n（置信度较低，仅供参考）",
                    name=PLANNER_MARKER,
                )],
            }

        # 正常路径：注入规划 SystemMessage（name=planner 标记）
        emit(PLANNER_COMPLETED_EVENT, "planner",
             {"status": "planned", "intent_l1": plan.intent_l1,
              "confidence": plan.confidence, "cost_time_ms": int((time.monotonic() - start) * 1000)},
             status="completed")
        return {
            "planner_result": result,
            "planner_status": "planned",
            "planner_reason": "",
            "messages": [SystemMessage(
                content=_format_plan_system_message(plan),
                name=PLANNER_MARKER,
            )],
        }

    return planner_node