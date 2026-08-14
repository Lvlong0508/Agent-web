"""agent 工具包：统一从这里注册所有可调用的工具。

get_tools(session_factory) 汇总全部工具，供 agent 图构建时绑定。
"""

from collections.abc import Callable

from app.tools.expense_tool import build_expense_tools
from app.tools.time_tool import build_time_tools


def get_tools(session_factory: Callable) -> list:
    """汇总所有 agent 工具：传入会话工厂，工具在被调用时自行开一个新会话。

    账单工具需要会话工厂（每次调用开新会话访问 MySQL）；时间工具是纯函数
    不依赖会话，但其工厂签名与账单不同（无需参数），这里直接展开它的列表。
    """
    return build_expense_tools(session_factory) + build_time_tools()