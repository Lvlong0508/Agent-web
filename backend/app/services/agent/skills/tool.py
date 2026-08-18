"""技能读取工具：agent 按需经 read_skill 加载技能完整正文（L1 展开）。

设计要点（spec 2026-08-18）：
- 纯函数工具，无会话依赖（与 time_tool 一致）
- 统一用 async 定义：同步工具在 LangGraph 中会被放进线程池执行，而本项目用
  contextvar 传递用户身份，跨线程会丢失上下文；async 工具与 agent 在同一个
  事件循环内执行，规避该问题
- 未知名技能返回友好提示而非抛异常：技能加载失败不阻塞 agent 主流程
"""

from langchain_core.tools import tool

from app.services.agent.skills import loader


@tool
async def read_skill(name: str) -> str:
    """加载技能完整说明。当任务匹配某技能的描述时调用。"""
    body = loader.get_skill_body(name)
    if body is None:
        return f"未找到技能: {name!r}。可用技能见系统提示词列表。"
    return f"[技能 {name}]\n{body}"


def build_skill_tools() -> list:
    """构造技能相关工具列表；新增技能类工具时在此追加并更新返回列表"""
    return [read_skill]
