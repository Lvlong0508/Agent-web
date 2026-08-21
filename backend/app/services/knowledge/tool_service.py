"""AI 工具库业务（预留）：借向量检索按需装配 tool，本阶段仅建桩"""

from app.services.knowledge.base_service import BaseKnowledgeService


class ToolKnowledgeService(BaseKnowledgeService):
    """工具库：字段与检索策略（trigger_keywords 等）待工具装配阶段补充"""

    def _build_where(self, owner_id: str | None = None) -> dict:
        # 预留：工具库按 kb_type 过滤，未来补充启用状态等条件
        return {"kb_type": "tool"}