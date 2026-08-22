# backend/tests/test_settings.py
"""settings 配置测试：BASE_DIR 定位 backend 根目录、SKILLS_DIR 迁移归属"""

from pathlib import Path

from app.config.settings import settings


def test_base_dir_points_to_backend_root():
    """BASE_DIR 必须指向 backend/ 根目录：skill 相对路径在此基础上解析。
    settings.py 位于 backend/app/config/，向上 3 级即 backend/"""
    assert settings.BASE_DIR == Path(__file__).resolve().parents[1]
    # parents[0]=tests, [1]=backend, [2]=agent-web；BASE_DIR 应为 backend（测试文件比 settings.py 多一层 tests/，故取 parents[1]）
    assert settings.BASE_DIR.name == "backend"


def test_skills_dir_migrated_to_agent_settings():
    """SKILLS_DIR 已迁移到 AgentSettings：agent 模块配置独立于基础设施配置"""
    from app.config.agent_settings import agent_settings

    assert agent_settings.SKILLS_DIR == "skills"


def test_chroma_config_defaults():
    """Chroma 基础设施配置默认值：localhost:8000，embedding 维度 1024，
    tenant 保持 default_tenant，database 用项目名与其他项目隔离"""
    assert settings.CHROMA_HOST == "localhost"
    assert settings.CHROMA_PORT == 8000
    assert settings.EMBEDDING_DIM == 1024
    assert settings.CHROMA_TENANT == "default_tenant"
    assert settings.CHROMA_DATABASE == "agent-web"


def test_data_name_mappings_defaults():
    """数据表/集合名统一从配置读取（env 可 JSON 覆盖），不再散落硬编码"""
    # MySQL 表名映射：逻辑名 expense -> 真实表 expenses
    assert settings.MYSQL_TABLES == {"expense": "expenses"}
    # MongoDB 集合名映射：逻辑名与真实集合名一致，env 可改 value
    assert settings.MONGODB_COLLECTIONS == {
        "agent_runs": "agent_runs",
        "conversations": "conversations",
        "messages": "messages",
    }
