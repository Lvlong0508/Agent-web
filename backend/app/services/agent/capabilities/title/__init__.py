"""title 能力：标题生成（旁路节点，与回复生成并行 fan-out）"""

from langgraph.graph import END, START, StateGraph

from app.config.settings import settings
from app.services.agent.capabilities.core_agent.llm import create_llm
from app.services.agent.capabilities.core_agent.state import AgentState
from app.services.agent.capabilities.title.node import _generate_title_if_empty
from app.services.agent.capability import AgentCapability
from app.services.agent.events import emit


class TitleCapability(AgentCapability):
    """标题生成能力：标题为空时调用 LLM 生成新标题并写回数据库"""

    @property
    def name(self) -> str:
        return "title"

    def __init__(self, conv_repo):
        self._conv_repo = conv_repo

    def state_keys(self) -> dict[str, type]:
        # 标题产物字段（预定义在 AgentState，本处声明供校验与文档化）
        return {"generated_title": str}

    def register_nodes(self, builder: StateGraph) -> list[str]:
        # 标题生成节点：标题为空则生成并写回数据库，新标题放入状态供上层推送前端
        async def generate_title_node(state: AgentState) -> dict:
            # get_by_id 带 user_id 参数：按"对话 ID + 归属用户"查询，防越权访问他人对话
            conv = await self._conv_repo.get_by_id(state["conv_id"], state["user_id"])
            title = ""
            try:
                title = await _generate_title_if_empty(
                    conv,
                    state["messages"],
                    create_llm(
                        streaming=False,
                        model=state.get("model") or settings.MODEL_OLLAMA,
                        # 标题生成关闭思考模式并限制输出长度：通义千问开启思考时
                        # 标题请求要等十几秒思考完才返回，会拖到回复之后才刷新；
                        # 关闭后秒回，保证"先刷新标题，再输出内容"
                        enable_thinking=False,
                        max_tokens=100,
                    ),
                )
                if title:
                    await self._conv_repo.update_title(state["conv_id"], title)
            except Exception:
                # 标题生成失败不能阻断主聊天流程：静默跳过，回复仍照常产出
                pass
            # 发出标题事件：chat_service 经 EventRouter 订阅后推送前端侧边栏。
            # 标题为空（未生成/已存在）也发事件，由订阅端自行判断是否推送
            emit("title.completed", "title", {"title": title or ""}, status="completed")
            # 把（可能为空的）标题写回状态：保持状态 schema 完整，供测试断言与
            # 未来能力读取（业务推送已改走上面的 title.completed 事件）
            return {"generated_title": title or ""}

        builder.add_node("generate_title", generate_title_node)
        return ["generate_title"]

    def connect(self, builder: StateGraph) -> None:
        # 标题节点与 agent 节点并行启动：标题生成与回复生成互不依赖。
        # fan-out 并行：若串行（generate_title → agent），标题 LLM 完整生成完
        # 才轮到回复流式输出，首条回复会被标题生成拖慢数秒；并行后回复立即
        # 开始流式输出，标题在后台生成
        builder.add_edge(START, "generate_title")
        # 标题节点是旁路：产出标题即结束，不参与回复链路
        builder.add_edge("generate_title", END)
