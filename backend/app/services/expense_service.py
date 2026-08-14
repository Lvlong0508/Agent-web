"""个人账单业务层：串联数据访问、类型校验与分页组装"""

from app.auth import get_current_user_id_or_raise
from app.exceptions import NotFoundError
from app.models.expense import Expense
from app.repositories.expense_repo import ExpenseRepo
from app.schemas.expense import (
    ExpenseCreate,
    ExpensePage,
    ExpenseResponse,
    ExpenseUpdate,
)


class ExpenseService:
    """账单业务逻辑：对外暴露增删改查与分页查询，屏蔽底层 ORM 细节"""

    def __init__(self, session):
        # 注入异步会话，数据访问全部走 ExpenseRepo
        self.repo = ExpenseRepo(session)

    async def create(self, data: ExpenseCreate) -> ExpenseResponse:
        """新增账单：类型枚举转字符串存库，归属当前请求用户"""
        # 从请求上下文取当前用户 ID（FastAPI 依赖已注入），落库归属该用户
        user_id = get_current_user_id_or_raise()
        expense = Expense(
            user_id=user_id,
            category=data.category.value,
            amount=data.amount,
            date=data.date,
            description=data.description,
        )
        created = await self.repo.create(expense)
        return ExpenseResponse.model_validate(created)

    async def list(self, page: int = 1, page_size: int = 20) -> ExpensePage:
        """分页查询账单：页码下限 1，每页条数限制在 1~100 之间，防止恶意大值"""
        user_id = get_current_user_id_or_raise()
        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)
        items, total = await self.repo.list_by_user(user_id, page, page_size)
        return ExpensePage(
            items=[ExpenseResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size,
        )

    async def get(self, expense_id: int) -> ExpenseResponse:
        """按 id 查询单条账单，不存在则抛 404"""
        user_id = get_current_user_id_or_raise()
        expense = await self.repo.get_by_id(user_id, expense_id)
        if expense is None:
            raise NotFoundError(entity="Expense")
        return ExpenseResponse.model_validate(expense)

    async def update(self, expense_id: int, data: ExpenseUpdate) -> ExpenseResponse:
        """更新账单：只更新请求里传了的字段（排除值为 None 的字段）"""
        user_id = get_current_user_id_or_raise()
        expense = await self.repo.get_by_id(user_id, expense_id)
        if expense is None:
            raise NotFoundError(entity="Expense")
        update_data = data.model_dump(exclude_unset=True)
        # 类型枚举转字符串后再落库
        if "category" in update_data and update_data["category"] is not None:
            update_data["category"] = update_data["category"].value
        updated = await self.repo.update(expense, update_data)
        return ExpenseResponse.model_validate(updated)

    async def delete(self, expense_id: int) -> None:
        """删除账单：不存在则抛 404"""
        user_id = get_current_user_id_or_raise()
        expense = await self.repo.get_by_id(user_id, expense_id)
        if expense is None:
            raise NotFoundError(entity="Expense")
        await self.repo.delete(expense)
