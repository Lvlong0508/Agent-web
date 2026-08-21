"""提示词集中管理模块：所有发给 LLM 的提示词统一在此维护。

本包按节点分文件组织，__init__.py 只做聚合导出——外部代码统一从包级导入，
不深入子模块（import 边界，见 agent/README.md 四节）：
- core_agent.py：系统提示词（小励角色定位 + build_system_prompt）
- title.py：对话标题生成
- verifier.py：回复校验 + 重写指令
- planner.py：planner 规划模板 + 示例库

以下提示词都经过了‘第一性原理’、‘对抗性审查’的多轮次审查得到的健壮提示词。
"""

from app.services.agent.prompts.core_agent import SYSTEM_PROMPT, build_system_prompt
from app.services.agent.prompts.title import TITLE_GENERATION_TEMPLATE, build_title_prompt
from app.services.agent.prompts.verifier import (
    REPLY_ON_VERIFY_FAILED,
    REWRITE_DATA_RULE_CALL_TOOLS,
    REWRITE_DATA_RULE_USE_RESULT,
    REWRITE_PROMPT_TEMPLATE,
    VERIFY_PROMPT,
    build_rewrite_prompt,
)
from app.services.agent.prompts.planner import PLANNER_TEMPLATE  # 供 context 层经包级 init 引用

__all__ = [
    "SYSTEM_PROMPT",
    "build_system_prompt",
    "TITLE_GENERATION_TEMPLATE",
    "build_title_prompt",
    "VERIFY_PROMPT",
    "REWRITE_PROMPT_TEMPLATE",
    "REWRITE_DATA_RULE_CALL_TOOLS",
    "REWRITE_DATA_RULE_USE_RESULT",
    "build_rewrite_prompt",
    "REPLY_ON_VERIFY_FAILED",
    "PLANNER_TEMPLATE",
]