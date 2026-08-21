"""知识库数据结构：文档块元数据 + 批量写入/检索请求 + 检索响应。

字段模型（spec 2026-08-20 精简版）：5 个通用字段全放 Chroma metadata，
正文放 document，二者组成一条 chunk 记录。
"""

from typing import Literal

from pydantic import BaseModel, Field

# 库类型枚举：Literal 精确限定可选值，防止拼错库名
KBType = Literal["enterprise", "user", "tool", "skill"]


class ChunkMetadata(BaseModel):
    """文档块元数据：Chroma 中一条 chunk 记录的 metadata 部分（5 个字段）。

    溯源/定位：kb_type 路由到 collection，owner_id 隔离归属，
    source_doc_id + chunk_index 定位到原文具体块，source_file 供前端展示。
    """

    kb_type: KBType = Field(description="库类型：enterprise/user/tool/skill")
    owner_id: str = Field(description="归属者：企业库=global，用户库=user_id，工具/skill 库=system")
    source_doc_id: str = Field(description="原始文档 ID（溯源 + 按来源删除）")
    source_file: str = Field(default="", description="原始文件名（溯源展示）")
    chunk_index: int = Field(default=0, description="块在原文中的序号（0 起）")


class ChunkAddRequest(BaseModel):
    """批量写入请求：一篇文章切分后的多个正文块。

    chunks 是已切割好的文本列表；chunk_index 由 0 起自动编号，
    调用方只需保证 chunks 顺序即原文顺序。
    """

    kb_type: KBType
    owner_id: str
    source_doc_id: str
    source_file: str = Field(default="")
    chunks: list[str] = Field(min_length=1, description="已切割好的文档块正文列表")


class ChunkSearchRequest(BaseModel):
    """语义检索请求：指定库类型与查询文本，top_k 默认 5"""

    kb_type: KBType
    query: str = Field(min_length=1, description="自然语言查询文本")
    top_k: int = Field(default=5, ge=1, le=50, description="返回条数（1~50）")


class SearchResultItem(BaseModel):
    """单条检索结果：正文 + 相似度 + 溯源信息（供前端点击跳转原文）"""

    content: str = Field(description="命中的文档块正文")
    score: float = Field(description="相似度分数（cosine distance 转相似度，越高越相关）")
    source_file: str = Field(default="", description="原始文件名（溯源展示）")
    chunk_index: int = Field(default=0, description="块在原文中的序号（0 起）")
    source_doc_id: str = Field(description="原始文档 ID，前端凭它回查原文")
    kb_type: KBType

class SkillCandidate(BaseModel):
    name: str = Field(description="技能名（= source_doc_id）")
    description: str = Field(description="技能描述（frontmatter description）")
    score: float = Field(description="相似度分数（越高越相关）")

class ChunkSearchResponse(BaseModel):
    """检索响应：按相关度排序的命中文档块列表"""

    items: list[SearchResultItem]