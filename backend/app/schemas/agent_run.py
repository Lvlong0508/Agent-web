from pydantic import BaseModel

from app.models.agent_run import AgentRun


class AgentRunPage(BaseModel):
    """运行记录分页响应：与 ExpensePage 对齐的通用分页结构（items+total+分页信息）"""
    items: list[AgentRun]   # 当前页的运行记录
    total: int              # 满足过滤条件的总条数
    page: int               # 当前页码（从 1 开始）
    page_size: int          # 每页条数
    total_pages: int        # 总页数 = ceil(total / page_size)