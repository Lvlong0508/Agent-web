"""预定义完整 AgentState：所有能力的字段集中在此声明（规格 v3 第 6.2 节）。

设计决策：不动态合成 TypedDict（评审指出 reducer 在动态类型上不可靠），
而是预定义全部已知字段，新能力需要新字段时在此追加（属于能力自带的迁移操作）。
"""

from langgraph.graph import MessagesState


class AgentState(MessagesState):
    # ---- 公共字段（core_agent 声明）----
    conv_id: str
    user_id: str
    model: str
    thinking: bool
    history_reference: list
    trace_id: str            # 请求级追踪 ID：chat_stream 注入 config 后节点写入，供落库
    error_info: str          # 节点异常时写入的摘要，由 updates 流带出（管理员可查）

    # ---- title 能力贡献 ----
    generated_title: str

    # ---- verifier 能力贡献 ----
    rewrite_count: int
    verification_feedback: str
    verification_result: str
    verdict: dict
    verdict_input: list
