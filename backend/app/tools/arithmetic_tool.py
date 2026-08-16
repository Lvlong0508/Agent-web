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

import math

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
            # names={}：禁用变量名；functions={}：不启用任何内置函数（simpleeval
            # 默认会开放 rand/randint/int/float/str，一并关掉才保证表达式里只允许
            # 数字与运算符；simpleeval 默认除法返回 float，天然支持先乘除后加减与括号优先级
            result = simpleeval.simple_eval(expression, names={}, functions={})
            # float 转换必须放在 try 内：simple_eval 对超大整数（如 2**1030）会正常返回
            # int，真正的 OverflowError 在这里抛出；放 try 外会漏出原始英文 traceback
            result = float(result)
        except (
            TypeError,
            OverflowError,
            ZeroDivisionError,
            simpleeval.InvalidExpression,
            SyntaxError,
        ) as e:
            # 除零/非法表达式/类型错误（如 1+"a"）/数值溢出（如 2**1030）/语法错误
            # 统一转 ValueError，langchain 自动把异常转成错误提示反馈给 LLM，
            # 让其修正表达式后重试
            raise ValueError(f"表达式无法计算：{e}") from e
        # round 前先判断有限性：simpleeval 返回的浮点数可能为 inf/nan（如 1e400），
        # langchain 序列化时会产生非严格 JSON 的 Infinity，质检员小模型无法可靠判定，
        # 统一转 ValueError 让 LLM 换一种表达
        if not math.isfinite(result):
            raise ValueError("表达式计算结果超出可表示范围（inf/nan），请换一种表达方式")
        # 浮点结果四舍五入到10位，避免 0.30000000000000004 这类尾数噪音干扰质检
        return {"expression": expression, "result": round(result, 10)}

    return [calculate]
