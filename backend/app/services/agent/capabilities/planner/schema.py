"""Planner 输出结构化 schema：意图识别 + 目标 + 路线规划（稳定骨架）。

设计要点（spec 2026-08-18 第 6 节）：
- schema 中不硬编码任何工具名：required_tools 恒为 List[str]，工具扩张时零改动
- intent_l1 用 Literal 枚举封闭：小模型禁止自创类别
- 计划步骤带 suggested_tools 与 depends_on，支持多步依赖表达
"""

from typing import Literal

from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    """执行步骤：一步动作 + 建议工具 + 依赖关系"""

    step_id: int = Field(description="步骤序号，从 1 开始")
    action: str = Field(description="该步骤要做什么，自然语言描述")
    suggested_tools: list[str] = Field(
        default_factory=list, description="建议工具名（从可用工具清单选择），可为空"
    )
    depends_on: list[int] = Field(
        default_factory=list, description="依赖的步骤 ID 列表，空表示无依赖"
    )


# 一级意图枚举：业务动作方向，极稳定，与具体工具解耦（spec 第 5.1 节）
L1_INTENTS = Literal[
    "RECORD",   # 记一笔（新增）
    "QUERY",    # 查账
    "MODIFY",   # 改账
    "DELETE",   # 删账
    "STATISTICS",  # 统计/分析
    "SKILL",    # 技能辅助
    "CHITCHAT",  # 闲聊/无关
    "COMPOUND",  # 复合意图
]


class PlannerOutput(BaseModel):
    """Planner 输出：意图 + 目标 + 步骤 + 工具/技能推荐 + 置信度"""

    intent_l1: L1_INTENTS = Field(description="一级意图（从枚举中选择，禁止自创）")
    intent_l2: str = Field(description="二级意图，格式 L1_XXX，如 RECORD_SINGLE")
    goal: str = Field(description="用户目标的中性描述，1-2 句，不添加主观推断")
    plan_steps: list[PlanStep] = Field(description="执行步骤列表（1-4 步）")
    required_tools: list[str] = Field(
        default_factory=list, description="需要的工具名（从可用工具清单选择）"
    )
    required_skills: list[str] = Field(
        default_factory=list, description="可能需要的技能方向（从技能摘要选择）"
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="规划置信度（≥0.9 非常确定 / 0.7-0.9 基本确定 / <0.7 不确定）"
    )