"""planner 上下文组装：把提示词、工具清单、技能索引、few-shot、用户本轮问题
组装成真正发给 planner LLM 的消息列表（对齐 context/agent.py 的 build_agent_messages）。

职责划分（spec 2026-08-21）：
- 静态素材（模板/示例库/关键词表）在 agent/prompts/planner.py
- 本文件只做"组装"：素材 + 动态信息 → 消息列表
- 输出清洗（sanitize_required_tools）在编排层 node.py，不在此处
"""

from langchain_core.messages import HumanMessage, SystemMessage

from app.services.agent.prompts import PLANNER_TEMPLATE  # 经包级 init 导出
from app.services.agent.prompts.planner import (
    FALLBACK_EXAMPLE,
    FEW_SHOT_LIBRARY,
    _QUICK_KEYWORDS,
    _TOOL_PLACEHOLDERS,
)


def quick_l1_classify(user_input: str) -> str:
    """用关键词规则粗判用户输入的 L1 意图（无需 LLM，供 few-shot 选择）。

    按优先级顺序匹配关键词；均未命中返回 CHITCHAT（兜底，不代表分类正确，
    仅决定注入哪个示例）。粗判只影响示例选择，不影响最终规划质量。
    """
    for l1, keywords in _QUICK_KEYWORDS.items():
        for kw in keywords:
            if kw in user_input:
                return l1
    return "CHITCHAT"


def _replace_tool_names(output: dict, current_tools: list[str]) -> dict:
    """把示例 output 里的工具名占位符替换为当前真实工具名。

    current_tools：当前可用工具名列表。占位符按"语义前缀"匹配——例如
    {create_tool} 匹配以 create_ 开头的工具，匹配到第一个即替换，匹配不到
    替换为空（工具不可用时不留假名）。新增业务工具只要遵守命名规范
    （create_/list_/update_/delete_ 前缀），示例库与占位符表零改动。
    """
    import json

    text = json.dumps(output, ensure_ascii=False)
    for placeholder, prefixes in _TOOL_PLACEHOLDERS.items():
        if placeholder in text:
            # 从当前工具集找第一个名字以任一前缀开头的工具
            replacement = next(
                (name for name in current_tools if name.startswith(prefixes)), ""
            )
            text = text.replace(placeholder, replacement)
    return json.loads(text)


def build_few_shot_section(user_input: str, current_tools: list[str]) -> str:
    """按用户输入粗判 L1，返回该 L1 的 1-2 个示例（工具名已动态替换）。

    current_tools：当前可用工具名列表（用于动态替换示例里的占位工具名）。
    """
    l1 = quick_l1_classify(user_input)
    examples = FEW_SHOT_LIBRARY.get(l1) or [FALLBACK_EXAMPLE]
    # 只取前 2 个示例控制 token（每 L1 当前只有 1 个，未来扩展时天然截断）
    selected = examples[:2]
    lines = ["## 输出示例", "以下是类似输入的参考输出格式：", ""]
    for ex in selected:
        output = _replace_tool_names(ex["output"], current_tools)
        lines.append(f"输入：{ex['input']}")
        lines.append(f"输出：{output}")
        lines.append("")
    return "\n".join(lines)


def build_tool_section(tools: list) -> str:
    """从工具列表生成"可用工具清单"prompt 片段；无工具时返回空串。

    tools：langchain BaseTool 列表（含 .name 与 .description 属性）。
    当前 ≤15 个工具扁平展示；未来工具多时在此改为按 category 分组。
    """
    if not tools:
        return ""
    lines = [
        "## 当前可用工具清单",
        "请从以下工具中选择需要的工具（使用工具名称，名称必须完全一致）：",
        "",
    ]
    for t in tools:
        lines.append(f"- **{t.name}**：{t.description}")
    return "\n".join(lines)


def build_planner_prompt(
    user_input: str,
    tools: list,
    skills_index: str = "",
) -> str:
    """拼完整 planner 提示词：模板骨架 + 动态工具清单 + 技能摘要 + few-shot。

    user_input：本轮用户问题（用于 few-shot 粗判 L1）；
    tools：langchain BaseTool 列表（生成动态工具清单）；
    skills_index：技能索引文本（L0），空串表示无技能。
    """
    skill_section = skills_index if skills_index.strip() else ""
    tool_section = build_tool_section(tools)
    few_shot_section = build_few_shot_section(user_input, [t.name for t in tools])
    return PLANNER_TEMPLATE.format(
        skill_section=skill_section,
        tool_section=tool_section,
        few_shot_section=few_shot_section,
    )


def build_planner_messages(
    user_input: str,
    tools: list,
    skills_index: str = "",
) -> list:
    """组装发给 planner LLM 的消息列表：[SystemMessage(完整提示词), HumanMessage(用户本轮)]。

    对齐 build_agent_messages 模式：消息列表是发给 LLM 的完整上下文。
    为未来把历史会话组装进 context 留出位置（本期历史会话仍不入 planner 上下文）。
    """
    prompt = build_planner_prompt(user_input, tools, skills_index)
    return [
        SystemMessage(content=prompt),
        HumanMessage(content=user_input),
    ]


def format_plan_system_message(plan) -> str:
    """把规划格式化为注入 agent 上下文的 SystemMessage 内容（输出逐字不变）。

    plan：PlannerOutput 实例。编排层（node.py）用它生成带 PLANNER_MARKER 的
    SystemMessage，注入 agent 消息流作为执行规划参考。
    """
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
