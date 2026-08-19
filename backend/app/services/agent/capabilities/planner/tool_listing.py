"""planner 动态工具清单：从工具列表生成 prompt 片段 + 工具名容错。

设计要点（spec 第 7 节）：
- 工具清单不硬编码：从 get_tools() 结果动态生成，新增工具零改动
- 工具描述直接用 langchain 从 docstring 生成的 t.description（实测已有中文描述）
- 工具名容错：planner 可能输出近似名，三层递进（精确→编辑距离→丢弃）
"""


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
    """
    result = []
    for raw in required_tools:
        resolved = resolve_tool_name(raw, valid_names)
        if resolved is not None and resolved not in result:
            result.append(resolved)
    return result