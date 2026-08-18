"""Ollama 厂商子包：本地 LLM 的构造工厂（厂商内模型级分发）"""

from langchain_openai import ChatOpenAI

from app.config.settings import settings


def create_ollama_llm(
    streaming: bool = True,
    model: str = "",
    max_tokens: int | None = None,
) -> ChatOpenAI:
    """构造 Ollama 本地 LLM：缺省选择名或 ollama-qwen3.5 都落到本地默认模型。

    model：模型选择名（仅用于厂商内模型分发校验）。
    max_tokens：当前 Ollama 分支不传给 ChatOpenAI（保持重构前行为），
        参数保留仅用于签名对称，未来本地模型需要时可透传。
    """
    # 厂商内模型分发：当前只认领缺省与 ollama-qwen3.5 两个选择名，
    # 其余（含拼错/未注册的 ollama 前缀名）显式报错，避免静默用错模型
    if model not in ("", settings.MODEL_OLLAMA):
        raise ValueError(f"未知的 Ollama 模型选择名: {model!r}")
    return ChatOpenAI(
        model=settings.LLM_MODEL,
        base_url=settings.OLLAMA_BASE_URL + "/v1",
        api_key="ollama",  # Ollama 不校验 API Key，但 ChatOpenAI 需要此参数
        streaming=streaming,
    )
