# backend/tests/test_settings.py
"""settings 配置测试：BASE_DIR 定位 backend 根目录、SKILLS_DIR 默认值"""

from pathlib import Path

from app.config.settings import settings


def test_base_dir_points_to_backend_root():
    """BASE_DIR 必须指向 backend/ 根目录：skill 相对路径在此基础上解析。
    settings.py 位于 backend/app/config/，向上 3 级即 backend/"""
    assert settings.BASE_DIR == Path(__file__).resolve().parents[1]
    # parents[0]=tests, [1]=backend, [2]=agent-web；BASE_DIR 应为 backend（测试文件比 settings.py 多一层 tests/，故取 parents[1]）
    assert settings.BASE_DIR.name == "backend"


def test_skills_dir_default_is_relative():
    """SKILLS_DIR 默认相对路径 "skills"，可经 .env 调整为其他位置"""
    assert settings.SKILLS_DIR == "skills"
