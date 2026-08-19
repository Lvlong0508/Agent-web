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
