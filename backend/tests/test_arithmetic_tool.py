"""算术工具 calculate 测试：表达式求值、优先级、异常（纯函数，不依赖数据库）"""

import pytest

from app.tools.arithmetic_tool import build_arithmetic_tools


@pytest.mark.asyncio
async def test_calculate_mixed_expression_with_brackets():
    """带括号的混合运算按优先级求值：(1+2)*3 = 9"""
    tools = {t.name: t for t in build_arithmetic_tools()}
    result = await tools["calculate"].ainvoke({"expression": "(1+2)*3"})
    assert result["expression"] == "(1+2)*3"
    assert result["result"] == 9.0


@pytest.mark.asyncio
async def test_calculate_priority_multiplication_before_addition():
    """先乘除后加减：1+2*3 = 7"""
    tools = {t.name: t for t in build_arithmetic_tools()}
    result = await tools["calculate"].ainvoke({"expression": "1+2*3"})
    assert result["result"] == 7.0


@pytest.mark.asyncio
async def test_calculate_division_returns_float():
    """除法返回浮点数：10/4 = 2.5"""
    tools = {t.name: t for t in build_arithmetic_tools()}
    result = await tools["calculate"].ainvoke({"expression": "10/4"})
    assert result["result"] == 2.5


@pytest.mark.asyncio
async def test_calculate_left_associative_chain_division():
    """连续除法左结合：100/4/5 = 5.0"""
    tools = {t.name: t for t in build_arithmetic_tools()}
    result = await tools["calculate"].ainvoke({"expression": "100/4/5"})
    assert result["result"] == 5.0


@pytest.mark.asyncio
async def test_calculate_division_by_zero_raises_value_error():
    """除零报错：langchain 会把 ValueError 转成错误反馈给 LLM 重试"""
    tools = {t.name: t for t in build_arithmetic_tools()}
    with pytest.raises(ValueError):
        await tools["calculate"].ainvoke({"expression": "1/0"})


@pytest.mark.asyncio
async def test_calculate_invalid_expression_raises_value_error():
    """非法表达式报错（names={} 禁用变量，'abc' 视为非法）"""
    tools = {t.name: t for t in build_arithmetic_tools()}
    with pytest.raises(ValueError):
        await tools["calculate"].ainvoke({"expression": "abc"})