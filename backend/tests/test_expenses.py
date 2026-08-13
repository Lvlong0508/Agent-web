"""个人账单模块测试：真实 MySQL 上验证 CRUD、分页与索引（无服务时自动跳过）"""

import pytest
import pytest_asyncio
from sqlalchemy import delete, text
from sqlalchemy.exc import OperationalError

from app.config.settings import settings
from app.exceptions import NotFoundError
from app.middleware.mysql import Base, SessionLocal, engine
from app.models.expense import Expense, ExpenseCategory
from app.schemas.expense import ExpenseCreate, ExpenseUpdate
from app.services.expense_service import ExpenseService


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """每个测试前确保表已创建，结束后清空测试数据"""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except OperationalError:
        pytest.skip("本地 MySQL 不可用，跳过账单测试")
    yield
    async with engine.begin() as conn:
        await conn.execute(delete(Expense))


@pytest_asyncio.fixture
async def service():
    """为每个测试提供一个独立的业务层实例（内含独立会话）"""
    async with SessionLocal() as session:
        yield ExpenseService(session)


async def _make(data: ExpenseCreate, svc: ExpenseService) -> dict:
    """快捷方式：创建账单并返回响应字典"""
    resp = await svc.create(data)
    return resp.model_dump()


@pytest.mark.asyncio
async def test_create_expense(service):
    """测试新增账单：类型枚举转字符串、金额与日期正确落库"""
    resp = await service.create(
        ExpenseCreate(category=ExpenseCategory.FOOD, amount="25.50", date="2026-08-01", description="午饭")
    )
    assert resp.id is not None
    assert resp.category == "food"
    assert str(resp.amount) == "25.50"
    assert str(resp.date) == "2026-08-01"
    assert resp.description == "午饭"


@pytest.mark.asyncio
async def test_get_expense(service):
    """测试按 id 查询账单"""
    data = await _make(
        ExpenseCreate(category=ExpenseCategory.TRANSPORT, amount="3.00", date="2026-08-02"),
        service,
    )
    got = await service.get(data["id"])
    assert got.id == data["id"]
    assert got.category == "transport"


@pytest.mark.asyncio
async def test_get_expense_not_found(service):
    """测试查询不存在的账单抛 404"""
    with pytest.raises(NotFoundError):
        await service.get(999999)


@pytest.mark.asyncio
async def test_list_pagination(service):
    """测试分页查询：总数、总页数、页码与当前页条数正确"""
    for i in range(5):
        await _make(
            ExpenseCreate(category=ExpenseCategory.SHOPPING, amount=f"{i + 1}.00", date="2026-08-03"),
            service,
        )

    page = await service.list(page=1, page_size=2)
    assert page.total == 5
    assert page.total_pages == 3
    assert page.page == 1
    assert page.page_size == 2
    assert len(page.items) == 2

    # 翻到最后一页只剩 1 条
    last = await service.list(page=3, page_size=2)
    assert len(last.items) == 1


@pytest.mark.asyncio
async def test_list_clamps_pagination(service):
    """测试分页参数兜底：页码最小 1，每页条数上限 100"""
    page = await service.list(page=0, page_size=500)
    assert page.page == 1
    assert page.page_size == 100


@pytest.mark.asyncio
async def test_update_expense(service):
    """测试更新账单：只更新传入字段，其余保持不变"""
    data = await _make(
        ExpenseCreate(category=ExpenseCategory.FOOD, amount="10.00", date="2026-08-01"),
        service,
    )
    updated = await service.update(data["id"], ExpenseUpdate(amount="99.00"))
    assert str(updated.amount) == "99.00"
    # 未传的 category 保持原值
    assert updated.category == "food"


@pytest.mark.asyncio
async def test_delete_expense(service):
    """测试删除账单：删除后查询应抛 404"""
    data = await _make(
        ExpenseCreate(category=ExpenseCategory.OTHER, amount="1.00", date="2026-08-01"),
        service,
    )
    await service.delete(data["id"])
    with pytest.raises(NotFoundError):
        await service.get(data["id"])


@pytest.mark.asyncio
async def test_indexes_created(service):
    """测试三个查询索引已真实创建（information_schema.statistics 可查）"""
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT DISTINCT index_name FROM information_schema.statistics "
                "WHERE table_schema = :db AND table_name = 'expenses'"
            ),
            {"db": settings.MYSQL_DB_NAME},
        )
        indexes = {row[0] for row in result}

    expected = {"idx_user_date_amount", "idx_user_amount_category", "idx_user_amount"}
    assert expected <= indexes
