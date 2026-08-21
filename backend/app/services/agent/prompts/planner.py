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

# 工具名占位符：示例 output 用占位符，运行时由 _replace_tool_names 替换为真实工具名。
# 占位符语义 = 工具类别（创建/查询/修改/删除/计算），按工具名前缀自动匹配当前工具集，
# 新增业务工具只需遵守命名规范（create_/list_/update_/delete_ 前缀），示例库零改动。
_TOOL_PLACEHOLDERS = {
    "{create_tool}": ("create_",),      # 新增类工具：create_expense/create_stock...
    "{query_tool}": ("list_", "get_"),  # 查询类工具：list_expenses/get_expense...
    "{modify_tool}": ("update_",),      # 修改类工具：update_expense/update_stock...
    "{delete_tool}": ("delete_",),      # 删除类工具：delete_expense/delete_stock...
    "{stats_tool}": ("calculate",),     # 计算类工具：calculate...
}

# 示例库：key 为 L1，value 为示例列表（input + output）。每个 output 严格遵循
# PlanStep schema 四字段（step_id/action/suggested_tools/depends_on），
# output 保持 dict 格式（_replace_tool_names 依赖 json.dumps→replace→json.loads）。
FEW_SHOT_LIBRARY: dict[str, list[dict]] = {
    "RECORD": [
        {
            "input": "记一笔午饭35块",
            "output": {
                "intent_l1": "RECORD",
                "intent_l2": "RECORD_SINGLE",
                "goal": "记录一笔35元的午餐支出",
                "plan_steps": [
                    {"step_id": 1, "action": "创建账单", "suggested_tools": ["{create_tool}"], "depends_on": []},
                ],
                "required_tools": ["{create_tool}"],
                "required_skills": [],
                "confidence": 0.95,
            },
        },
    ],
    "QUERY": [
        {
            "input": "查上周的账单",
            "output": {
                "intent_l1": "QUERY",
                "intent_l2": "QUERY_BY_DATE",
                "goal": "查询上周的账单记录",
                "plan_steps": [
                    {"step_id": 1, "action": "按日期范围查询上周账单", "suggested_tools": ["{query_tool}"], "depends_on": []},
                ],
                "required_tools": ["{query_tool}"],
                "required_skills": [],
                "confidence": 0.9,
            },
        },
    ],
    "MODIFY": [
        {
            "input": "把昨天的午饭改成40",
            "output": {
                "intent_l1": "MODIFY",
                "intent_l2": "MODIFY_AMOUNT",
                "goal": "修改昨天午餐账单金额为40元",
                "plan_steps": [
                    {"step_id": 1, "action": "查询目标账单", "suggested_tools": ["{query_tool}"], "depends_on": []},
                    {"step_id": 2, "action": "修改金额", "suggested_tools": ["{modify_tool}"], "depends_on": [1]},
                ],
                "required_tools": ["{query_tool}", "{modify_tool}"],
                "required_skills": [],
                "confidence": 0.9,
            },
        },
    ],
    "DELETE": [
        {
            "input": "删掉昨天那笔打车",
            "output": {
                "intent_l1": "DELETE",
                "intent_l2": "DELETE_SINGLE",
                "goal": "删除昨天的打车账单",
                "plan_steps": [
                    {"step_id": 1, "action": "查询目标账单", "suggested_tools": ["{query_tool}"], "depends_on": []},
                    {"step_id": 2, "action": "删除账单", "suggested_tools": ["{delete_tool}"], "depends_on": [1]},
                ],
                "required_tools": ["{query_tool}", "{delete_tool}"],
                "required_skills": [],
                "confidence": 0.9,
            },
        },
    ],
    "STATISTICS": [
        {
            "input": "本月花了多少",
            "output": {
                "intent_l1": "STATISTICS",
                "intent_l2": "STAT_SUMMARY",
                "goal": "统计本月总支出",
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
            "input": "这笔怎么分类",
            "output": {
                "intent_l1": "SKILL",
                "intent_l2": "SKILL_CLASSIFY",
                "goal": "获取分类建议",
                "plan_steps": [
                    {"step_id": 1, "action": "读取分类技能说明", "suggested_tools": ["read_skill"], "depends_on": []},
                ],
                "required_tools": ["read_skill"],
                "required_skills": ["记账分类"],
                "confidence": 0.85,
            },
        },
    ],
    "CHITCHAT": [
        {
            "input": "你好",
            "output": {
                "intent_l1": "CHITCHAT",
                "intent_l2": "CHITCHAT_GREET",
                "goal": "打招呼",
                "plan_steps": [],
                "required_tools": [],
                "required_skills": [],
                "confidence": 0.95,
            },
        },
    ],
    "COMPOUND": [
        {
            "input": "查一下上周的餐饮支出，再帮我记一笔今天午饭35块",
            "output": {
                "intent_l1": "COMPOUND",
                "intent_l2": "COMPOUND_QUERY_RECORD",
                "goal": "查询上周餐饮支出并记录今天午饭",
                "plan_steps": [
                    {"step_id": 1, "action": "查询上周餐饮账单", "suggested_tools": ["{query_tool}"], "depends_on": []},
                    {"step_id": 2, "action": "记录今天午饭账单", "suggested_tools": ["{create_tool}"], "depends_on": []},
                ],
                "required_tools": ["{query_tool}", "{create_tool}"],
                "required_skills": [],
                "confidence": 0.85,
            },
        },
    ],
}

# 兜底示例：粗判 L1 无对应示例时使用（8 类全覆盖后实际不会触发，保留兼容）
FALLBACK_EXAMPLE = FEW_SHOT_LIBRARY["CHITCHAT"][0]

# 关键词粗判规则：L1 -> 关键词列表（越靠前优先级越高）。供 context/planner.py
# 的 quick_l1_classify 选择 few-shot 示例（遍历顺序 = 优先级顺序，RECORD 最先）。
# 保持 list[str] 格式（quick_l1_classify 用 for kw in keywords 遍历，dict 会破坏逻辑）。
# COMPOUND 放最前：并列连接词（再/还有/另外）是高区分信号，应先于具体意图命中，
# 否则含"查""记"的复合输入会被 QUERY/RECORD 劫持，COMPOUND 永远轮不到。
_QUICK_KEYWORDS: dict[str, list[str]] = {
    "COMPOUND": ["再", "还有", "另外", "同时", "并且", "以及"],
    "RECORD": ["记一笔", "记", "新增", "添加", "加一笔", "支出", "消费"],
    "MODIFY": ["改", "修改", "改成", "更新", "换成", "调整为", "更正"],
    "DELETE": ["删", "删除", "删掉", "去掉", "移除", "撤销", "不要了"],
    "QUERY": ["查", "看", "查询", "列出", "有哪些", "找", "明细", "哪笔"],
    "STATISTICS": ["统计", "汇总", "总共", "合计", "多少", "平均", "占比", "趋势", "分析"],
    "SKILL": ["怎么分类", "分类", "建议", "怎么归类", "归到哪"],
    "CHITCHAT": ["你好", "谢谢", "再见", "哈哈", "在吗"],
}