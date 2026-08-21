"""用户知识库业务：按 owner_id 隔离的私有知识

隔离安全兜底：检索/删除必须带 owner_id，服务层强制注入过滤条件，
不信任调用方传入的过滤参数，避免越权访问他人数据。
"""

from app.services.knowledge.base_service import BaseKnowledgeService


class UserKnowledgeService(BaseKnowledgeService):
    """用户库：所有操作强制 owner_id 过滤"""

    def _build_where(self, owner_id: str | None = None) -> dict:
        # 缺 owner_id（含空串）直接报错，防止无隔离检索泄露他人数据
        if not owner_id:
            raise ValueError("用户知识库必须指定 owner_id")
        return {"owner_id": owner_id}