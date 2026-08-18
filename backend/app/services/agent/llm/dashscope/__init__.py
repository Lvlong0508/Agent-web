"""DashScope 厂商子包：通义千问 LLM 的构造工厂（厂商内模型级分发）"""

from langchain_openai import ChatOpenAI

from app.config.settings import settings


def create_dashscope_llm(
    streaming: bool = True,
    model: str = "",
    enable_thinking: bool = True,
    max_tokens: int | None = None,
) -> ChatOpenAI:
    """构造 DashScope 通义千问 LLM，支持思考模式开关与输出长度限制。

    enable_thinking：qwen3 系列默认开启思考模式，请求会先输出大段思考
        token 再回答，非流式请求要等全部思考完成才返回（实测标题生成
        耗时十几秒）。关闭后响应立即返回，用于"标题要先刷新"这类对
        速度敏感、不需要深度推理的场景。
    max_tokens：限制输出 token 数，防止思考/回答超长拖慢响应。
    """
    # 厂商内模型分发：当前只认领 qwen3.7-flash 一个选择名
    if model != settings.MODEL_DASHSCOPE_QWEN:
        raise ValueError(f"未知的 DashScope 模型选择名: {model!r}")
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
