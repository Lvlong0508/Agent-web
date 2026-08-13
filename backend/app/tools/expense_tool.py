"""个人账单工具：把 ExpenseService 的业务方法封装成 agent 可调用的工具。

工具函数通过闭包捕获 session_factory（返回 AsyncSession 的可调用对象），
每次调用时自行开会话构造 ExpenseService，不持有全局会话、不写业务逻辑。

每个工具用 pydantic 模型声明参数（args_schema）：字段的 Field(description=...)
会写进发送给 LLM 的 JSON Schema 的 properties.*.description，让 LLM 精确理解
每个参数含义，从而正确传参。
"""

from collections.abc import Callable

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.models.expense import ExpenseCategory
from app.schemas.expense import ExpenseCreate, ExpenseUpdate
from app.services.expense_service import ExpenseService


# ---------- 各工具的参数 schema（LLM 通过它们理解每个参数） ----------

class CreateExpenseArgs(BaseModel):
    """新增账单的参数"""

    category: ExpenseCategory = Field(
        description="账单类型：food(餐饮)/transport(交通)/shopping(购物)/housing(居住)/entertainment(娱乐)/medical(医疗)/other(其他)"
    )
    amount: float = Field(description="金额（单位：元），必须大于 0")
    date: str = Field(description="消费日期，格式 YYYY-MM-DD")
    description: str | None = Field(
        default=None, description="账单描述（可选），如'午饭'、'地铁票'"
    )


class GetExpenseArgs(BaseModel):
    """按 id 查询账单的参数"""

    expense_id: int = Field(description="账单的自增 id")


class ListExpensesArgs(BaseModel):
    """分页查询账单的参数"""

    page: int = Field(default=1, description="页码，从 1 开始")
    page_size: int = Field(default=20, description="每页条数，限制在 1~100 之间")


class UpdateExpenseArgs(BaseModel):
    """更新账单的参数（只更新传入字段）"""

    expense_id: int = Field(description="要更新的账单 id")
    category: ExpenseCategory | None = Field(
        default=None, description="新的账单类型（可选），取值同新增"
    )
    amount: float | None = Field(
        default=None, description="新的金额（可选），单位元，必须大于 0"
    )
    date: str | None = Field(
        default=None, description="新的消费日期（可选），格式 YYYY-MM-DD"
    )
    description: str | None = Field(default=None, description="新的账单描述（可选）")


class DeleteExpenseArgs(BaseModel):
    """删除账单的参数"""

    expense_id: int = Field(description="要删除的账单 id")


def build_expense_tools(session_factory: Callable) -> list:
    """构造账单相关工具列表；session_factory 在工具每次被调用时创建一个新会话"""

    @tool(args_schema=CreateExpenseArgs)
    async def create_expense(
        category: ExpenseCategory,
        amount: float,
        date: str,
        description: str | None = None,
    ) -> dict:
        """新增一条个人账单并返回账单详情。"""
        async with session_factory() as session:
            resp = await ExpenseService(session).create(
                ExpenseCreate(
                    category=category,
                    amount=str(amount),
                    date=date,
                    description=description,
                )
            )
        return resp.model_dump(mode="json")

    @tool(args_schema=GetExpenseArgs)
    async def get_expense(expense_id: int) -> dict:
        """按 id 查询一条个人账单，返回账单详情；不存在时抛出错误。"""
        async with session_factory() as session:
            resp = await ExpenseService(session).get(expense_id)
        return resp.model_dump(mode="json")

    @tool(args_schema=ListExpensesArgs)
    async def list_expenses(page: int = 1, page_size: int = 20) -> dict:
        """分页查询个人账单列表，返回当前页数据与总数/总页数，按日期倒序。"""
        async with session_factory() as session:
            resp = await ExpenseService(session).list(page=page, page_size=page_size)
        return resp.model_dump(mode="json")

    @tool(args_schema=UpdateExpenseArgs)
    async def update_expense(
        expense_id: int,
        category: ExpenseCategory | None = None,
        amount: float | None = None,
        date: str | None = None,
        description: str | None = None,
    ) -> dict:
        """更新一条个人账单，只更新传入的字段，未传字段保持原值；返回更新后的账单。"""
        # 只保留非空字段，避免把未提供的字段写成空值
        payload = {
            k: v
            for k, v in {
                "category": category,
                "amount": str(amount) if amount is not None else None,
                "date": date,
                "description": description,
            }.items()
            if v is not None
        }
        if not payload:
            raise ValueError("没有提供任何需要更新的字段")
        async with session_factory() as session:
            resp = await ExpenseService(session).update(expense_id, ExpenseUpdate(**payload))
        return resp.model_dump(mode="json")

    @tool(args_schema=DeleteExpenseArgs)
    async def delete_expense(expense_id: int) -> dict:
        """删除一条个人账单，删除成功后返回确认信息。"""
        async with session_factory() as session:
            await ExpenseService(session).delete(expense_id)
        return {"deleted": True, "id": expense_id}

    return [create_expense, get_expense, list_expenses, update_expense, delete_expense]