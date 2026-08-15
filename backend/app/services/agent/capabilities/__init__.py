"""能力汇总：按注册顺序列出全部能力（core_agent 必须第一位，它是锚点宿主）。

新增能力：在此列表追加一行即可，核心代码零改动（规格 6.1）。
"""

from app.services.agent.capabilities.core_agent import CoreAgentCapability
from app.services.agent.capabilities.title import TitleCapability
from app.services.agent.capabilities.verifier import VerifierCapability


def get_capabilities(conv_repo, tools: list) -> list:
    """按注册顺序构建能力列表（core_agent 第一位）。

    conv_repo：对话仓库（title 能力需要写回标题）
    tools：组合根先汇总工具，再注入各能力（当前 core_agent/verifier 需要）
    """
    return [
        CoreAgentCapability(conv_repo, tools),
        TitleCapability(conv_repo),
        VerifierCapability(tools),
    ]
