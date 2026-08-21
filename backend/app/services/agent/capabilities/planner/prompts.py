"""planner 系统提示词构建：模板稳定，动态段（工具清单/技能摘要/few-shot）注入。

设计要点（spec 第 7.4 节）：
- 模板骨架稳定：L1 定义、输出规则、JSON 约束不随工具变化
- 动态段：工具清单、技能摘要、few-shot 每次构建时注入（新增工具零改动模板）
"""

from app.services.agent.capabilities.planner.few_shots import build_few_shot_section
from app.services.agent.capabilities.planner.tool_listing import build_tool_section

# 模板里的占位符：构建时用 format 填充动态段
_PLANNER_TEMPLATE = """你是一个记账助手的规划器。你的任务是分析用户意图，制定执行计划。

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


def _build_skill_section(skills_index: str) -> str:
    """技能摘要段：注入现有 L0 技能索引文本；为空时不注入。

    skills_index 来自 skills 包的 get_skills_index_prompt()（与 system prompt 一致）。
    """
    if not skills_index.strip():
        return ""
    return skills_index


def build_planner_prompt(
    user_input: str,
    tools: list,
    skills_index: str = "",
) -> str:
    """构建 planner 系统提示词：模板骨架 + 动态工具清单 + 技能摘要 + few-shot。

    user_input：本轮用户问题（用于 few-shot 粗判 L1）
    tools：langchain BaseTool 列表（生成动态工具清单）
    skills_index：技能索引文本（L0），空串表示无技能
    """
    skill_section = _build_skill_section(skills_index)
    tool_section = build_tool_section(tools)
    tool_names = [t.name for t in tools]
    few_shot_section = build_few_shot_section(user_input, tool_names)
    return _PLANNER_TEMPLATE.format(
        skill_section=skill_section,
        tool_section=tool_section,
        few_shot_section=few_shot_section,
    )