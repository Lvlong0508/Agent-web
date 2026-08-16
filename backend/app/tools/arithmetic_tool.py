"""算术工具：把数学表达式计算能力封装成 agent 可调用的 langchain 工具。

设计对齐 time_tool：用 build_arithmetic_tools() 工厂返回工具列表，新增算术类
工具只需在该函数里追加一个 @tool 函数，无需改动调用方。

算术工具是纯函数，不依赖数据库/会话。统一用 async 定义：同步工具在
LangGraph 中会被放进线程池执行，而本项目用 contextvar 传递用户身份，
跨线程会丢失上下文；async 工具与 agent 在同一个事件循环内执行，规避该问题。

求值用 simpleeval 库：支持 + - * / 与括号，按标准优先级（先乘除后加减、
括号优先）计算混合运算；names={} 禁用一切变量名、不启用任何函数，表达式里
只允许数字和运算符，保证安全。
"""

import simpleeval
from langchain_core.tools import tool
from pydantic import BaseModel, Field


class CalculateArgs(BaseModel):
    """计算表达式的参数"""

    expression: str = Field(
        description="数学表达式，支持数字、+ - * / 四则运算与括号，按标准优先级求值"
        "（先乘除后加减、括号优先），如 (1+2)*3"
    )


def build_arithmetic_tools() -> list:
    """构造算术工具列表；新增算术类工具时在此追加并更新返回列表"""

    @tool(args_schema=CalculateArgs)
    async def calculate(expression: str) -> dict:
        """计算一个数学表达式，返回表达式原文与计算结果；支持混合运算（括号 + 优先级）。"""
        try:
            # names={}：禁用变量名，表达式只能含数字与运算符；simpleeval 默认
            # 除法返回 float，天然支持先乘除后加减与括号优先级
            result = simpleeval.simple_eval(expression, names={})
        except (ZeroDivisionError, simpleeval.InvalidExpression, SyntaxError) as e:
            # 除零/非法表达式/语法错误统一转 ValueError，langchain 自动把
            # 异常转成错误提示反馈给 LLM，让其修正表达式后重试
            raise ValueError(f"表达式无法计算：{e}") from e
        return {"expression": expression, "result": float(result)}

    return [calculate]