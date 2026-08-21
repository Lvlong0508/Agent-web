"""Skill 库业务（预留）：按需检索匹配 skill，本阶段仅建桩"""

from app.services.knowledge.base_service import BaseKnowledgeService


class SkillKnowledgeService(BaseKnowledgeService):
    """skill 库：检索匹配 skill 描述，触发词等字段待 skill 装配阶段补充"""

    def _build_where(self, owner_id: str | None = None) -> dict:
        return {"kb_type": "skill"}