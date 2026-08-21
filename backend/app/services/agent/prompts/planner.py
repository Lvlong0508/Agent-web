"""planner 提示词素材：静态模板 + 示例库数据。

prompt 素材归 prompts 层（与 system/title/verifier 提示词同级）；拼接逻辑
（build_planner_prompt/build_planner_messages）在 agent/context/planner.py。
"""

# 模板里的占位符：构建时由 context 层用 format 填充动态段
PLANNER_TEMPLATE = """你是一个记账助手的规划器。你的任务是分析用户意图，制定执行计划。

## 你的职责
1. 识别用户的一级意图（L1）和二级意图（L2）
2. 用自然语言描述用户目标（不添加主观推断）
3. 拆解 1-4 步执行计划
4. 从下方工具清单中推荐需要的工具
5. 评估规划置信度

## 一级意图定义（L1）
- RECORD：用户想记录/新增账单
- QUERY：用户想查询/查看账单信息
- MODIFY：用户想修改已有账单
- DELETE：用户想删除账单
- STATISTICS：用户想统计/汇总/分析账单数据
- SKILL：用户需要外部技能辅助（如分类建议、消费分析）
- CHITCHAT：闲聊或与记账无关的对话
- COMPOUND：包含多个不同方向意图的复合请求

## 二级意图格式（L2）
格式为 {{L1}}_{{细分}}，例如：RECORD_SINGLE, QUERY_BY_DATE, STAT_SUMMARY。
根据用户表达的具体细节确定二级意图。

{skill_section}

{tool_section}

{few_shot_section}

## 输出规则
1. 只输出严格合法的 JSON 对象，不要包含任何解释、markdown 代码块或额外文字
2. required_tools 中的工具名必须与上方"当前可用工具清单"中的名称完全一致
3. confidence 评分：≥0.9 非常确定 / 0.7-0.9 基本确定 / <0.7 不确定
4. 如果不确定选哪个工具，required_tools 留空数组，让执行层自行决定
5. COMPOUND 意图时，plan_steps 中每个步骤对应一个子意图
6. required_skills 仅从上方技能摘要中选择；技能摘要中没有匹配的技能方向时输出空数组，不要强行匹配
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