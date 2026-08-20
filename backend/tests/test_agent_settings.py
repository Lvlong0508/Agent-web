"""AgentSettings 测试：planner 配置默认值 + 模型注册表 + SKILLS_DIR 迁移"""

from pathlib import Path

from app.config.agent_settings import AgentSettings, agent_settings


def test_planner_defaults():
    """planner 配置默认值：模型别名 planner / 思考开 / 超时60s / 阈值0.7"""
    assert agent_settings.PLANNER_MODEL_ALIAS == "planner"
    assert agent_settings.PLANNER_THINKING is True
    assert agent_settings.PLANNER_TIMEOUT == 60.0
    assert agent_settings.PLANNER_CONFIDENCE_THRESHOLD == 0.7


def test_model_registry_has_builtin_entries():
    """内置注册表含前端两模型 + planner，缺 models.yaml 也能跑"""
    registry = agent_settings.MODEL_REGISTRY
    assert "planner" in registry
    assert registry["planner"].provider == "dashscope"
    assert registry["planner"].model == "qwen3.7-flash-2026-07-15"
    assert registry["planner"].enable_thinking is True
    assert registry["planner"].streaming is False
    assert "ollama-qwen3.5" in registry
    assert "qwen3.7-flash" in registry


def test_model_select_constants_are_registry_keys():
    """前端选择名常量 = 注册表 key，二者必须一致（前端下拉值即注册表别名）"""
    assert agent_settings.MODEL_OLLAMA in agent_settings.MODEL_REGISTRY
    assert agent_settings.MODEL_DASHSCOPE_QWEN in agent_settings.MODEL_REGISTRY


def test_model_registry_loads_from_yaml(tmp_path):
    """显式传入 models.yaml 时以其为准（覆盖内置默认）"""
    yaml_file = tmp_path / "models.yaml"
    yaml_file.write_text(
        "model_registry:\n  custom:\n    provider: ollama\n    model: llama3\n",
        encoding="utf-8",
    )
    loaded = AgentSettings.load(yaml_path=yaml_file)
    assert "custom" in loaded.MODEL_REGISTRY
    assert loaded.MODEL_REGISTRY["custom"].model == "llama3"
    assert "planner" not in loaded.MODEL_REGISTRY  # 文件为准，内置被覆盖


def test_skills_dir_migrated_to_agent_settings():
    """SKILLS_DIR 已从原 settings 迁入 AgentSettings（agent 模块唯一配置源）"""
    assert agent_settings.SKILLS_DIR == "skills"


def test_base_dir_points_to_backend_root():
    """agent_settings 的 BASE_DIR 同样指向 backend/ 根目录"""
    assert agent_settings.BASE_DIR == Path(__file__).resolve().parents[1]
    assert agent_settings.BASE_DIR.name == "backend"