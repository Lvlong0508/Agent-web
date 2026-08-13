"""个人账单数据访问层：封装 expenses 表的增删改查与分页查询"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import Expense


class ExpenseRepo:
    """账单数据访问：所有查询都按 user_id 过滤，保证只能操作自己的账单"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, expense: Expense) -> Expense:
        """新增一条账单并提交，刷新后返回带自增 id 的完整对象"""
        self.session.add(expense)
        await self.session.commit()
        await self.session.refresh(expense)
        return expense

    async def get_by_id(self, user_id: str, expense_id: int) -> Expense | None:
        """按 id + 归属用户查询单条账单，不存在或不属于该用户返回 None"""
        result = await self.session.execute(
            select(Expense).where(
                Expense.id == expense_id,
                Expense.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_user(
        self,
        user_id: str,
        page: int,
        page_size: int,
    ) -> tuple[list[Expense], int]:
        """分页查询该用户的账单，返回（当前页数据, 总条数）。
        按日期倒序（最新在前）排列，同一天按 id 倒序保证顺序稳定。
        索引 (user_id, date, amount) 会命中本查询的过滤与排序。
        """
        # 先统计总条数，用于计算总页数
        count_q = (
            select(func.count())
            .select_from(Expense)
            .where(Expense.user_id == user_id)
        )
        total = (await self.session.execute(count_q)).scalar_one()

        # 再按 LIMIT/OFFSET 取当前页数据
        result = await self.session.execute(
            select(Expense)
            .where(Expense.user_id == user_id)
            .order_by(Expense.date.desc(), Expense.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), total

    async def update(self, expense: Expense, data: dict) -> Expense:
        """用传入的字段字典更新账单并提交，返回刷新后的对象"""
        for field, value in data.items():
            setattr(expense, field, value)
        await self.session.commit()
        await self.session.refresh(expense)
        return expense

    async def delete(self, expense: Expense) -> None:
        """删除一条账单并提交"""
        await self.session.delete(expense)
        await self.session.commit()
