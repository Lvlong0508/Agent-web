"""create_llm：按模型选择名创建对应 LLM（本地 Ollama 或通义千问 DashScope）"""

import logging

from langchain_openai import ChatOpenAI

from app.config.settings import settings

# 模块级日志器：供节点异常降级等场景记录可诊断信息，便于线上排查
logger = logging.getLogger(__name__)


def create_llm(
    streaming: bool = True,
    model: str = "",
    enable_thinking: bool = True,
    max_tokens: int | None = None,
) -> ChatOpenAI:
    """
    按模型选择名创建对应 LLM：本地 Ollama 或通义千问（DashScope）

    enable_thinking：仅对通义千问生效。qwen3 系列默认开启思考模式，
        请求会先输出大段思考 token 再回答，非流式请求要等全部思考完成才返回
        （实测标题生成耗时十几秒）。关闭后响应立即返回，用于"标题要先刷新"
        这类对速度敏感、不需要深度推理的场景。
    max_tokens：限制输出 token 数，防止思考/回答超长拖慢响应。
    """
    # 通义千问：显式匹配选择名
    if model == settings.MODEL_DASHSCOPE_QWEN:
        kwargs = {"streaming": streaming}
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        # 关闭思考时通过 DashScope 兼容模式的请求体参数控制
        if not enable_thinking:
            kwargs["extra_body"] = {"enable_thinking": False}
        return ChatOpenAI(
            model=settings.DASHSCOPE_MODEL,
            base_url=settings.DASHSCOPE_BASE_URL,
            api_key=settings.DASHSCOPE_API_KEY,
            **kwargs,
        )
    # 缺省（未指定）或 Ollama 选择名：回退本地 Ollama，保证向后兼容
    if model == "" or model == settings.MODEL_OLLAMA:
        return ChatOpenAI(
            model=settings.LLM_MODEL,
            base_url=settings.OLLAMA_BASE_URL + "/v1",
            api_key="ollama",  # Ollama 不校验 API Key，但 ChatOpenAI 需要此参数
            streaming=streaming,
        )
    # 非空未知选择名：显式报错，避免前后端常量漂移时静默用错模型
    raise ValueError(f"未知的模型选择名: {model!r}")
