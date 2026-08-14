import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class AgentRun(BaseModel):
    """agent 运行全链路记录 ODM：对应 MongoDB agent_runs 集合

    一次运行（用户每发一条消息触发一次）存一条文档，messages 里按时间
    有序保存该轮全链路消息（用户请求、agent 中间回复含工具调用参数、
    工具执行结果、最终回复），供开发者完整回放一次运行过程。
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), alias="_id")
    conversation_id: str   # 所属对话 ID
    user_id: str           # 归属用户 ID（与请求头 X-User-Id 一致）
    model: str             # 模型选择名，如 ollama-qwen3.5
    status: str = "ok"     # ok | error，运行失败时便于排查
    error: str | None = None  # 运行异常时的错误信息（仅 status=error 时有值）
    messages: list[dict] = Field(default_factory=list)  # 全链路消息序列，按时间有序
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}
