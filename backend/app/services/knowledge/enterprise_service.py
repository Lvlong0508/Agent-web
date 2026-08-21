"""企业知识库业务：全体用户可查的公共知识，无 owner 隔离"""

from app.services.knowledge.base_service import BaseKnowledgeService


class EnterpriseKnowledgeService(BaseKnowledgeService):
    """企业库：检索/删除不加过滤条件（公共知识）"""

    def _build_where(self, owner_id: str | None = None) -> dict:
        return {}