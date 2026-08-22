"""个人账单 ORM 模型与类型枚举：对应 MySQL agent-web.expenses 表"""

from __future__ import annotations  # 延迟注解求值：避免字段名 date 遮蔽 datetime.date 类型

import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import BigInteger, Date, DateTime, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.config import database_settings
from app.config import settings
from app.middleware.mysql import Base


class ExpenseCategory(str, Enum):
    """账单类型枚举：数据库存枚举值的字符串，API 用该枚举做校验"""

    FOOD = "food"  # 餐饮
    TRANSPORT = "transport"  # 交通
    SHOPPING = "shopping"  # 购物
    HOUSING = "housing"  # 居住
    ENTERTAINMENT = "entertainment"  # 娱乐
    MEDICAL = "medical"  # 医疗
    OTHER = "other"  # 其他


class Expense(Base):
    """个人账单表：id 自增主键，所有查询都按 user_id 过滤"""

    # 表名从配置读取（env 可覆盖），与 MongoDB/Chroma 的集合名统一在配置管理
    __tablename__ = database_settings.MYSQL_TABLES["expense"]

    # 三个查询索引都从 user_id 开头（最左前缀），保证按用户过滤的查询命中索引。
    # 注意：第三个索引 (user_id, amount) 是第二个 (user_id, amount, category)
    # 的前缀子集，存在冗余，此处按需求保留以对照理解索引前缀规则。
    __table_args__ = (
        Index("idx_user_date_amount", "user_id", "date", "amount"),
        Index("idx_user_amount_category", "user_id", "amount", "category"),
        Index("idx_user_amount", "user_id", "amount"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), default=settings.DEFAULT_USER_ID)
    category: Mapped[str] = mapped_column(String(32))
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    # 字段名是 date，类型注解用模块级 datetime.date 全限定，避免与同名字段冲突
    date: Mapped[datetime.date] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # 创建时间：账单记录时间，用于排序兜底。
    # MySQL DATETIME 只存 naive 时间，取 UTC 后去掉时区信息落库
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None),
    )

    def __repr__(self) -> str:
        """调试友好输出：显示账单归属用户、类型与金额"""
        return f"<Expense id={self.id} user={self.user_id} {self.category}={self.amount}>"
