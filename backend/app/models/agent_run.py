import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.models.trace import TraceStep


class AgentRun(BaseModel):
    """agent 运行全链路记录 ODM：对应 MongoDB agent_runs 集合

    一次运行（用户每发一条消息触发一次）存一条文档。三层结构：
    - 运行级汇总（duration_ms/total_tokens/verdict/retry_count）供管理员列表页快速概览
    - steps[]（TraceStep）按节点组织完整链路：输入上下文、产出、耗时、降级、Call 级
    其中 messages 字段保留为兼容字段（旧数据/退化路径），新记录主数据在 steps。
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), alias="_id")
    conversation_id: str   # 所属对话 ID
    user_id: str           # 归属用户 ID（与请求头 X-User-Id 一致）
    model: str             # 模型选择名，如 ollama-qwen3.5
    status: str = "ok"     # ok | error，运行失败时便于排查
    error: str | None = None  # 运行异常时的错误信息（仅 status=error 时有值）
    trace_id: str = ""     # 请求级追踪 ID（uuid4().hex），管理员据此串联错误链（规格 7.1）
    messages: list[dict] = Field(default_factory=list)  # 全链路消息序列（兼容字段）
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # === 运行级汇总（管理员列表页快速概览，无需展开 steps）===
    duration_ms: int = 0               # 总耗时（首 Step 开始 → 末 Step 结束）
    total_input_tokens: int = 0        # 全部 LLM 调用输入 token 之和
    total_output_tokens: int = 0       # 全部 LLM 调用输出 token 之和
    verdict: str | None = None         # 最终质检结果 pass / retry / fail
    retry_count: int = 0               # 重写轮次数
    steps: list[TraceStep] = Field(default_factory=list)  # 三层结构：节点级步骤数组

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}
