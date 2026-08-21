"""planner 提示词素材：静态模板 + 示例库数据。

prompt 素材归 prompts 层（与 system/title/verifier 提示词同级）；拼接逻辑
（build_planner_prompt/build_planner_messages）在 agent/context/planner.py。
"""

# 模板里的占位符：构建时由 context 层用 format 填充动态段
PLANNER_TEMPLATE = """记账助手规划器。分析用户意图，制定执行计划。

## 判定规则
1. 优先级（同时符合多类时取最高）：RECORD > MODIFY > DELETE > QUERY > STATISTICS > SKILL > CHITCHAT
2. 关键词参考：记/花/支出→RECORD | 改/更新→MODIFY | 删→DELETE | 查/看→QUERY | 统计/汇总→STATISTICS | 分类/建议→SKILL
3. 无法明确判定时，confidence < 0.7，intent_l1 填 CHITCHAT，禁止强行分类
4. COMPOUND 严控：仅当两个独立并列核心动作（"再""还有""另外"）才判；同一目标先后步骤（"查完再统计"）不算
5. intent_l1 仅限 8 值：RECORD/QUERY/MODIFY/DELETE/STATISTICS/SKILL/CHITCHAT/COMPOUND

## 意图定义（L1→L2 示例）
- RECORD：新增账单 →RECORD_SINGLE
- QUERY：查询账单 →QUERY_BY_DATE
- MODIFY：修改已有账单 →MODIFY_AMOUNT
- DELETE：删除账单 →DELETE_SINGLE
- STATISTICS：统计/汇总/分析 →STAT_SUMMARY
- SKILL：需外部技能辅助 →SKILL_CLASSIFY
- CHITCHAT：闲聊或与记账无关 →CHITCHAT_GREET
- COMPOUND：多个独立并列核心动作 →COMPOUND_QUERY_RECORD

{skill_section}

{tool_section}

{few_shot_section}

## 输出规则
1. 只输出合法 JSON 对象，不含 markdown 代码块或额外文字
2. required_tools 必须与工具清单名称完全一致；不确定时留空数组
3. required_skills 仅从技能摘要选；无匹配则留空数组
4. confidence：≥0.9 非常确定 / 0.7-0.9 基本确定 / <0.7 不确定（归 CHITCHAT）
5. COMPOUND 时 plan_steps 每步对应一个子意图
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

# 关键词粗判规则：L1 -> 关键词列表（越靠前优先级越高）。供 context/planner.py
# 的 quick_l1_classify 选择 few-shot 示例（见 spec §3.2）
_QUICK_KEYWORDS: dict[str, list[str]] = {
    "RECORD": ["记一笔", "记", "新增", "加一笔", "添加"],
    "MODIFY": ["改", "修改", "更新", "变成"],
    "DELETE": ["删", "删除", "去掉"],
    "QUERY": ["查", "看", "查一下", "列出", "有哪些"],
    "STATISTICS": ["多少", "总共", "合计", "统计", "平均", "占比", "汇总"],
    "SKILL": ["怎么分类", "分类", "建议", "技能", "怎么记"],
}