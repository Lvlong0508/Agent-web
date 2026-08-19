"""Ollama 厂商子包：本地 LLM 的构造工厂。

模型名校验由上层注册表承担（未知 alias 抛 ValueError），本函数不再做白名单。
"""

from langchain_openai import ChatOpenAI

from app.config.settings import settings


def create_ollama_llm(
    model: str,                        # 真实 API 模型名（来自注册表条目）
    streaming: bool = True,
) -> ChatOpenAI:
    """构造 Ollama 本地 LLM。max_tokens 不传给 ChatOpenAI（保持重构前行为）。"""
    return ChatOpenAI(
        model=model,
        base_url=settings.OLLAMA_BASE_URL + "/v1",
        api_key="ollama",  # Ollama 不校验 API Key，但 ChatOpenAI 需要此参数
        streaming=streaming,
    )