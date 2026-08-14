"""测试共享工具：避免测试污染真实数据库。

背景：test_expenses.py / test_tools.py 曾在每个测试结束后执行
`delete(Expense)` 清空整张 expenses 表，而它们连的是真实 MySQL
（agent-web 库），导致用户通过 AI 工具创建的账单被误删。
这里提供两个函数，把清理逻辑改为"只清理本次测试新增的数据"：
测试前记录最大 id，测试后只删除 id 大于该值的行，绝不触碰已有用户数据。
"""

from sqlalchemy import delete, text

from app.middleware.mysql import engine
from app.models.expense import Expense


async def get_max_expense_id() -> int:
    """查询 expenses 表当前最大 id；表不存在或 MySQL 不可用时抛 OperationalError"""
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT COALESCE(MAX(id), 0) FROM expenses"))
        return result.scalar()


async def delete_expenses_after(max_id: int) -> None:
    """只删除 id 大于 max_id 的行（本次测试新插入的数据），保留已有用户数据"""
    async with engine.begin() as conn:
        await conn.execute(delete(Expense).where(Expense.id > max_id))
