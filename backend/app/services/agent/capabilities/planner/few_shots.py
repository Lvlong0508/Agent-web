"""planner 动态 few-shot：按 L1 组织示例库 + 关键词粗判 + 工具名动态替换。

设计要点（spec 第 7.3 节）：
- 示例库按 L1 组织，每 L1 1-2 个；新增工具时在此维护（不改 prompt 模板）
- 运行时用关键词粗判 L1（无需 LLM），只注入该 L1 的示例，省 token 且聚焦
- 示例 output 里的工具名是占位符，每次构建时动态替换为当前真实工具名，
  工具扩张后示例不失效
"""

# 工具名占位符：示例输出里用 {tool_xxx} 占位，运行时替换为真实工具名。
# 占位名语义即"该示例需要什么类型的工具"，不绑定具体实现
_TOOL_PLACEHOLDERS = {
    "{create_tool}": "create_expense",   # 新增账单
    "{query_tool}": "list_expenses_by_date",  # 按日期查账单
    "{stats_tool}": "calculate",         # 计算
}

# 示例库：key 为 L1，value 为示例列表（input + output 占位符形式）
FEW_SHOT_LIBRARY: dict[str, list[dict]] = {
    "RECORD": [
        {
            "input": "帮我记一笔，今天午饭花了35块",
            "output": {
                "intent_l1": "RECORD",
                "intent_l2": "RECORD_SINGLE",
                "goal": "新增一笔餐饮支出记录",
                "plan_steps": [
                    {"step_id": 1, "action": "新增餐饮账单", "suggested_tools": ["{create_tool}"], "depends_on": []},
                ],
                "required_tools": ["{create_tool}"],
                "required_skills": [],
                "confidence": 0.95,
            },
        },
    ],
    "QUERY": [
        {
            "input": "帮我查一下上周的账单",
            "output": {
                "intent_l1": "QUERY",
                "intent_l2": "QUERY_BY_DATE",
                "goal": "查询上周的账单记录",
                "plan_steps": [
                    {"step_id": 1, "action": "按日期范围查询上周账单", "suggested_tools": ["{query_tool}"], "depends_on": []},
                ],
                "required_tools": ["{query_tool}"],
                "required_skills": [],
                "confidence": 0.92,
            },
        },
    ],
    "STATISTICS": [
        {
            "input": "这个月总共花了多少钱",
            "output": {
                "intent_l1": "STATISTICS",
                "intent_l2": "STAT_SUMMARY",
                "goal": "统计本月支出总额",
                "plan_steps": [
                    {"step_id": 1, "action": "查询本月账单", "suggested_tools": ["{query_tool}"], "depends_on": []},
                    {"step_id": 2, "action": "汇总金额", "suggested_tools": ["{stats_tool}"], "depends_on": [1]},
                ],
                "required_tools": ["{query_tool}", "{stats_tool}"],
                "required_skills": [],
                "confidence": 0.9,
            },
        },
    ],
    "SKILL": [
        {
            "input": "这笔开销该怎么分类",
            "output": {
                "intent_l1": "SKILL",
                "intent_l2": "SKILL_GENERAL",
                "goal": "参考记账技能的分类规则给出建议",
                "plan_steps": [
                    {"step_id": 1, "action": "读取记账技能说明", "suggested_tools": ["read_skill"], "depends_on": []},
                ],
                "required_tools": ["read_skill"],
                "required_skills": ["记账分类"],
                "confidence": 0.88,
            },
        },
    ],
}

# 兜底示例：粗判 L1 无对应示例时使用（如 CHITCHAT / COMPOUND / MODIFY / DELETE）
FALLBACK_EXAMPLE = {
    "input": "你好",
    "output": {
        "intent_l1": "CHITCHAT",
        "intent_l2": "CHITCHAT_GENERAL",
        "goal": "与用户进行日常对话",
        "plan_steps": [],
        "required_tools": [],
        "required_skills": [],
        "confidence": 0.9,
    },
}

# 关键词粗判规则：L1 -> 关键词列表（越靠前优先级越高）
_QUICK_KEYWORDS: dict[str, list[str]] = {
    "RECORD": ["记一笔", "记", "新增", "加一笔", "添加"],
    "MODIFY": ["改", "修改", "更新", "变成"],
    "DELETE": ["删", "删除", "去掉"],
    "QUERY": ["查", "看", "查一下", "列出", "有哪些"],
    "STATISTICS": ["多少", "总共", "合计", "统计", "平均", "占比", "汇总"],
    "SKILL": ["怎么分类", "分类", "建议", "技能", "怎么记"],
}


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

    current_tools：当前可用工具名列表。占位符替换逻辑：
    - 占位符对应的默认工具名在当前工具集中 → 用默认名
    - 不在当前工具集（工具被移除/改名）→ 用占位符后的首个别名或留空
    """
    import json

    text = json.dumps(output, ensure_ascii=False)
    for placeholder, default_name in _TOOL_PLACEHOLDERS.items():
        if placeholder in text:
            # 默认名在当前工具集则替换为默认名，否则替换为空（工具不可用时不留假名）
            replacement = default_name if default_name in current_tools else ""
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