"""agent 工具包：统一从这里注册所有可调用的工具。

get_tools(session_factory) 汇总全部工具，供 agent 图构建时绑定。
"""

from collections.abc import Callable

from app.tools.expense_tool import build_expense_tools


def get_tools(session_factory: Callable) -> list:
    """汇总所有 agent 工具：传入会话工厂，工具在被调用时自行开一个新会话"""
    return build_expense_tools(session_factory)