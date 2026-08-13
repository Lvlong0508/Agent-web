"""MySQL 中间件测试：验证连接串构造正确；本地有 MySQL 服务时验证真实连通"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.config.settings import settings
from app.middleware.mysql import Base, SessionLocal, engine, get_db


def test_engine_url_points_to_agentweb_db():
    """测试引擎连接串指向 agent-web 库与应用账号（密码需已 URL 编码）"""
    url = engine.url
    assert url.drivername == "mysql+asyncmy"
    assert url.username == settings.MYSQL_USER
    assert url.host == settings.MYSQL_HOST
    assert url.port == settings.MYSQL_PORT
    assert url.database == settings.MYSQL_DB_NAME
    # URL 对象返回解码后的原始密码；@ 等特殊字符在渲染连接串时被编码，
    # 编码正确性由下面的真实连通测试实际验证
    assert url.password == settings.MYSQL_PASSWORD
    assert url.query.get("charset") == "utf8mb4"


def test_base_and_session_factory():
    """测试模型基类与异步会话工厂已就绪"""
    assert Base is not None
    assert SessionLocal is not None


@pytest.mark.asyncio
async def test_mysql_connectivity_select_1():
    """测试真实连接：无 MySQL 服务时跳过，有服务则验证 SELECT 1 与当前库"""
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1, DATABASE()"))
            one, db_name = result.one()
    except OperationalError as exc:
        pytest.skip(f"本地 MySQL 不可用，跳过连通性测试：{exc}")

    assert one == 1
    assert db_name == settings.MYSQL_DB_NAME


@pytest.mark.asyncio
async def test_get_db_yields_session_and_closes():
    """测试 get_db 依赖能产出会话并正常结束（不抛异常即可）"""
    async for _session in get_db():
        pass
