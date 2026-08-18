"""时间工具包：把"获取时间"类能力封装成 agent 可调用的 langchain 工具。

设计对齐 expense_tool：用 build_time_tools() 工厂返回工具列表，新增时间类
工具（如取日期、取星期）时，只需在该函数里追加一个 @tool 函数，无需改动
调用方（services/agent/tools/__init__.py 的 get_tools 直接展开该列表）。

时间工具是纯函数，不依赖数据库/会话。统一用 async 定义：同步工具在
LangGraph 中会被放进线程池执行，而本项目用 contextvar 传递用户身份，
跨线程会丢失上下文；async 工具与 agent 在同一个事件循环内执行，规避该问题。
"""

import time

from langchain_core.tools import tool


def build_time_tools() -> list:
    """构造时间工具列表；新增时间类工具时在此追加并更新返回列表"""

    @tool
    async def get_now_time() -> str:
        """获取当前实际时间，返回格式 YYYY-MM-DD HH:MM:SS。"""
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    return [get_now_time]
