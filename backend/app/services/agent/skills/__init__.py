"""技能机制包出口：模块级 loader 单例与索引文本工厂。

- loader：进程内单例，构造时扫描 agent_settings.SKILLS_DIR 一次并缓存（运行期只读）
- get_skills_index_prompt()：供 chat_service 注入 system prompt 的 L0 索引文本。
  用函数而非直接暴露 loader，调用方不依赖单例内部结构，测试可 monkeypatch
  包级 loader 变量以注入临时技能目录
"""

import logging
from pathlib import Path

from app.config import agent_settings
from app.config import settings
from app.services.agent.skills.loader import SkillLoader

logger = logging.getLogger(__name__)

# 进程内单例：路径由 AgentSettings 配置（相对 BASE_DIR 或绝对），换位置只需改 .env
_skills_path = Path(agent_settings.SKILLS_DIR)
if not _skills_path.is_absolute():
    _skills_path = settings.BASE_DIR / _skills_path
# 注意：这里把单例实例绑定为 loader 变量，与子模块 loader.py 同名——
# "from ...skills import loader" 拿到的是本实例而非模块（Python 属性链语义），
# tool.py 的 read_skill 正是依赖这一行为；测试 monkeypatch 的目标也对应实例
loader = SkillLoader(_skills_path)

_skill_service = None

def get_skills_index_prompt() -> str:
    """返回技能索引清单文本（L0），无技能时返回空串；供 build_agent_messages 注入"""
    return loader.get_index_prompt()

def build_skills_index_prompt(candidates: list) -> str:
    if not candidates:
        return ""
    lines = [
        "## 可用技能",
        "",
        "当任务匹配某技能的描述时，调用 read_skill 工具加载该技能的完整说明。",
        "",
    ]
    for c in candidates:
        lines.append(f"- **{c.name}**: {c.description}")
    return "\n".join(lines)

def _get_skill_service():
    global _skill_service
    if _skill_service is None:
        from app.middleware.chroma import ChromaClient
        from app.services.knowledge.embedder import DashScopeEmbedder
        from app.services.knowledge.skill_service import SkillKnowledgeService

        _skill_service = SkillKnowledgeService(
            ChromaClient.get_collection("skill"),
            DashScopeEmbedder(),
        )
    return _skill_service

async def get_relevant_skills_prompt(query: str) -> str:
    try:
        service = _get_skill_service()
        candidates = await service.search(
            query,
            top_k=agent_settings.SKILL_RETRIEVE_TOP_K,
            threshold=agent_settings.SKILL_SIMILARITY_THRESHOLD,
        )
    except Exception as e:
        logger.warning("技能向量检索失败，回退全量注入: %s", e)
        return get_skills_index_prompt()

    names = {c.name for c in candidates}
    for name in agent_settings.SKILL_ALWAYS_INJECT:
        if name in names:
            continue
        skill = loader.get_skill(name)
        if skill is None:
            continue
        from app.schemas.knowledge import SkillCandidate

        candidates.insert(0, SkillCandidate(
            name=name,
            description=skill["description"],
            score=1.0
        ))
    return build_skills_index_prompt(candidates)

__all__ = [
    "SkillLoader",
    "get_skills_index_prompt",
    "get_relevant_skills_prompt",
    "build_skills_index_prompt",
    "loader"
]