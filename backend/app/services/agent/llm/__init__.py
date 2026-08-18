"""llm 包：按厂商（URL）分类的模型工厂集合。

create_llm 是统一分发入口：按"模型选择名"做厂商级粗分发，
把构造委托给各厂商子包；厂商内部再做模型级分发。
"""

from langchain_openai import ChatOpenAI

from app.services.agent.llm.dashscope import create_dashscope_llm
from app.services.agent.llm.ollama import create_ollama_llm


def create_llm(
    streaming: bool = True,
    model: str = "",
    enable_thinking: bool = True,
    max_tokens: int | None = None,
) -> ChatOpenAI:
    """按模型选择名做厂商粗分发，委托对应厂商子包构造 LLM。

    分发规则：
    - 缺省（""）或 ollama 前缀选择名 → 本地 Ollama 厂商
    - 其余选择名 → DashScope 厂商（未知选择名由厂商内部模型分发抛 ValueError）
    """
    if model == "" or model.startswith("ollama"):
        return create_ollama_llm(streaming=streaming, model=model, max_tokens=max_tokens)
    return create_dashscope_llm(
        streaming=streaming,
        model=model,
        enable_thinking=enable_thinking,
        max_tokens=max_tokens,
    )
