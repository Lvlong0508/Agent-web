"""llm 包：按厂商（URL）分类的模型工厂集合。

create_llm 是统一分发入口：按 alias 从模型注册表（AgentSettings.MODEL_REGISTRY）
取模型定义，委托对应厂商子包构造。新增模型 = 改 models.yaml（或内置默认），
本函数零改动。厂商内部不再有选择名白名单——"防拼错静默用错模型"由注册表承担。
"""

from langchain_openai import ChatOpenAI

from app.config.agent_settings import agent_settings
from app.services.agent.llm.dashscope import create_dashscope_llm
from app.services.agent.llm.ollama import create_ollama_llm


def create_llm(
    alias: str | None = None,          # 注册表 key；None → 默认本地模型（MODEL_OLLAMA）
    streaming: bool | None = None,     # None → 用注册表条目默认
    enable_thinking: bool | None = None,
    max_tokens: int | None = None,
) -> ChatOpenAI:
    """查表工厂：按 alias 从模型注册表取模型定义，委托厂商子包构造。

    厂商 / 真实模型名完全由配置决定，代码里不再出现任何模型名。
    streaming / enable_thinking / max_tokens 是节点运行时业务决策，可覆盖注册表默认
    （如标题生成关思考、verifier 关思考限长）；缺省 None 时用注册表条目默认。
    未知 alias 抛 ValueError：宁可显式报错，也不静默用错模型。
    """
    alias = alias or agent_settings.MODEL_OLLAMA
    config = agent_settings.MODEL_REGISTRY.get(alias)
    if config is None:
        raise ValueError(f"未知的模型别名: {alias!r}（请检查 models.yaml / AgentSettings 内置注册表）")
    if config.provider == "ollama":
        return create_ollama_llm(
            model=config.model,
            streaming=streaming if streaming is not None else config.streaming,
        )
    return create_dashscope_llm(
        model=config.model,
        streaming=streaming if streaming is not None else config.streaming,
        enable_thinking=enable_thinking if enable_thinking is not None else config.enable_thinking,
        max_tokens=max_tokens,
    )