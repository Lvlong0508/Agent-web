"""预定义完整 AgentState：所有能力的字段集中在此声明（规格 v3 第 6.2 节）。

设计决策：不动态合成 TypedDict（评审指出 reducer 在动态类型上不可靠），
而是预定义全部已知字段，新能力需要新字段时在此追加（属于能力自带的迁移操作）。
"""

from langgraph.graph import MessagesState


class AgentState(MessagesState):
    """agent 图的共享状态：消息列表（继承）+ 当前对话 ID + 模型选择名 + 新生成的标题 + 思考开关 + 验证状态"""

    # ---- 公共字段（core_agent 声明）----
    conv_id: str
    # 注意：TypedDict 状态不应用类属性默认值，缺省回退逻辑在节点内用 state.get 实现
    user_id: str  # 当前请求用户 ID：由 chat_service 注入，图节点查询/写入按用户隔离
    model: str
    # 深度思考开关：仅通义千问生效，开启时回复先生成思考过程再回答（更慢但更深入）
    thinking: bool
    # 精纯历史参考（含本轮 user）：与传给 agent 的记忆一致，来自 chat_service
    # 从 MongoDB 拉取的 user/assistant 消息（无工具轮/重写轮噪音）。
    # 供质检员理解上下文，避免只看本轮而误判基于记忆的回复
    history_reference: list
    trace_id: str            # 请求级追踪 ID：chat_stream 注入 config 后节点写入，供落库
    error_info: str          # 节点异常时写入的摘要，由 updates 流带出（管理员可查）

    # ---- skill 检索装配（chat_service 注入）----
    # 技能 L0 索引文本：chat_stream 检索 top-K 后注入，planner 节点从 state 读取
    # （全图只用一份检索结果，避免 planner 重复检索/全量膨胀）。
    # 可选字段：缺省/降级时节点用 state.get 回退空串，与 planner_result 惯例一致
    skills_index: str | None

    # ---- title 能力贡献 ----
    # 标题节点产出的新标题：必须声明在状态 schema 中，stream_mode="updates"
    # 才会把这个字段随节点输出一起推给调用方（未声明的键会被 LangGraph 过滤）
    generated_title: str

    # ---- verifier 能力贡献 ----
    # 验证重写计数：verifier 判不准确时累加，超限后返回固定文案（防止无限循环）
    rewrite_count: int
    # 验证反馈：verifier 写给 agent 的修正意见；非空表示候选回复未通过，需重写
    verification_feedback: str
    # 验证结论：verifier 产出的 pass（准确）/ retry（需重写）/ fail（超限）。
    # 必须声明在状态 schema 中，stream_mode="updates" 才会把这个字段推给 chat_service
    # 检测结果（未声明的键会被 LangGraph 静默丢弃）
    verification_result: str
    # 质检员结构化判定（Verdict 的字典）：必须声明才能经 updates 流推给 chat_service，
    # 用于全链路记录追加 role=verdict 条目（未声明的键会被 LangGraph 静默丢弃）
    verdict: dict
    # 发给质检员的完整输入（序列化消息列表）：必须声明才能经 updates 流推给
    # chat_service，用于全链路记录追加 role=input_verdict 条目（评估质检效果）
    verdict_input: list

    # ---- planner 能力贡献 ----
    # 规划结果（planner 输出的完整 JSON）；None=降级/未执行。必须声明才能经
    # updates 流推给 chat_service / verifier（未声明的键会被 LangGraph 静默丢弃）
    planner_result: dict | None
    # 规划状态：planned（成功）/ skipped（低置信度仍注入）/ failed（失败降级）。
    # 必须声明才能经 updates 流供上层落库与监控
    planner_status: str
    # 降级原因（json_parse_error / timeout / schema_invalid / low_confidence）；
    # 空串表示无降级。供落库追溯规划失败原因
    planner_reason: str
    # 规划耗时（毫秒）：planner 节点每次执行都记录，供全链路记录展示与排查慢规划。
    # 必须声明才能经 updates 流推给 chat_service（未声明的键会被 LangGraph 静默丢弃）
    planner_cost_ms: int
