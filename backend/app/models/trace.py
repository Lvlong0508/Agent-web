"""三层全链路记录模型：Step（一次节点执行）+ Call（一次 LLM/工具调用）。

Step 来自 LangGraph debug 流的 task/task_result 事件，Call 来自
TraceCallbackHandler 的 LLM/工具调用记录，两者由组装器合并为 AgentRun.steps。
"""

from datetime import datetime

from pydantic import BaseModel, Field


class TraceCall(BaseModel):
    """Call 级：一次 LLM 或工具调用"""
    call_id: str                     # 递增编号
    call_type: str                   # llm | tool
    model: str | None = None         # llm：模型名
    input_tokens: int = 0            # llm：输入 token
    output_tokens: int = 0           # llm：输出 token
    finish_reason: str | None = None # llm：stop / tool_calls
    tool_name: str | None = None     # tool：工具名
    tool_call_id: str | None = None  # tool：工具调用 ID（与 AIMessage.tool_calls 对应）
    tool_arguments: dict | None = None  # tool：工具参数
    tool_result: str | None = None   # tool：工具结果
    start_time: datetime | None = None
    duration_ms: int = 0


class TraceStep(BaseModel):
    """Step 级：一次图节点执行"""
    step_id: str                     # "step_001" 按执行序递增
    node_name: str                   # agent / tools / planner / verifier / generate_title
    step_type: str                   # entry/planner/agent/tool/verifier/title
    status: str = "success"          # success / error（节点抛异常）/ degraded（内部降级）
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_ms: int = 0             # task/task_result timestamp 差值
    input: dict | None = None        # 节点输入上下文（经输入存储策略处理）
    output: dict | None = None       # 节点产出（state 增量）
    metrics: dict | None = None      # token/模型（callback 归并）
    error_info: dict | None = None   # 异常/降级详情
    calls: list[TraceCall] = Field(default_factory=list)  # Call 级数组