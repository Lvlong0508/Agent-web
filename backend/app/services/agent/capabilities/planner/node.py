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
        # 技能索引从 state 读取（chat_stream 已检索 top-K 注入），不再自调全量；
        # 缺省空串（无技能/降级时 skill 机制透明）
        skills_index = state.get("skills_index", "")
        prompt = build_planner_prompt(
            user_input,
            tools_list,
            skills_index,
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
            # 失败分支也要上报耗时：与完成事件一致，便于全链路记录排查"慢规划/超时"
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
            # 与 verifier 的 except Exception 降级同理，planner 必须对主流程透明。
            # 实测：planner 模型无 API 权限时 openai 抛 PermissionDeniedError，
            # 若不捕获会直接把 500 抛给整条请求，违背"规划失败不影响回复"的设计
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
        # 清洗后的工具名回写 plan（plan 是 pydantic 对象，用 model_copy 更新）
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
                    content=_format_plan_system_message(plan) + "\n（置信度较低，仅供参考）",
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
                content=_format_plan_system_message(plan),
                name=PLANNER_MARKER,
            )],
            "planner_cost_ms": cost_time_ms,
        }

    return planner_node