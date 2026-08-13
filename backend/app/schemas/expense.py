"""个人账单的数据结构：创建/更新请求与分页响应"""

from __future__ import annotations  # 延迟注解求值：避免字段名 date 遮蔽 datetime.date 类型

import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.expense import ExpenseCategory


class ExpenseCreate(BaseModel):
    """新增账单请求体：类型用枚举校验，金额必须大于 0"""

    category: ExpenseCategory
    amount: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    # 字段名是 date，类型注解用模块级 datetime.date 全限定，避免 pydantic 求值
    # 时把类型名解析成同名字段
    date: datetime.date
    description: str | None = Field(default=None, max_length=255)


class ExpenseUpdate(BaseModel):
    """更新账单请求体：全部字段可选，只更新传了的字段"""

    category: ExpenseCategory | None = None
    amount: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    date: datetime.date | None = None
    description: str | None = Field(default=None, max_length=255)


class ExpenseResponse(BaseModel):
    """账单响应体：从 ORM 对象序列化而来（from_attributes 支持直接读属性）"""

    id: int
    category: str
    amount: Decimal
    date: datetime.date
    description: str | None = None
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class ExpensePage(BaseModel):
    """分页响应：当前页数据 + 总数 + 页码信息，total_pages 供前端渲染分页器"""

    items: list[ExpenseResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
