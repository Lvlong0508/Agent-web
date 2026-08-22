# backend/tests/test_settings.py
"""settings 配置测试：BASE_DIR 定位 backend 根目录、应用级配置默认值。

数据库配置在 test_database_settings.py，大模型配置在 test_agent_settings.py。
"""

from pathlib import Path

from app.config import settings


def test_base_dir_points_to_backend_root():
    """BASE_DIR 必须指向 backend/ 根目录：skill 相对路径在此基础上解析。
    settings.py 位于 backend/app/config/，向上 3 级即 backend/"""
    assert settings.BASE_DIR == Path(__file__).resolve().parents[1]
    # parents[0]=tests, [1]=backend, [2]=agent-web；BASE_DIR 应为 backend（测试文件比 settings.py 多一层 tests/，故取 parents[1]）
    assert settings.BASE_DIR.name == "backend"


def test_skills_dir_migrated_to_agent_settings():
    """SKILLS_DIR 已迁移到 AgentSettings：agent 模块配置独立于应用级配置"""
    from app.config import agent_settings

    assert agent_settings.SKILLS_DIR == "skills"


def test_app_level_config_defaults():
    """应用级配置默认值：服务地址与单用户归属 ID"""
    assert settings.backend_host == "localhost"
    assert settings.backend_port == 8088
    assert settings.DEFAULT_USER_ID == "anonymous"