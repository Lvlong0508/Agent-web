"""llm 包测试：验证 create_llm 按 alias 查模型注册表分发"""

from unittest.mock import patch

import pytest

from app.config import agent_settings
from app.services.agent.llm import create_llm


def test_create_llm_dashscope_alias():
    """按注册表 dashscope 条目构造（主模型 qwen3.7-flash，思考默认开）"""
    with patch("app.services.agent.llm.dashscope.ChatOpenAI") as mock_cls:
        create_llm(alias="qwen3.7-flash")
    mock_cls.assert_called_once()
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["model"] == "qwen3.7-flash"
    assert kwargs["base_url"] == agent_settings.DASHSCOPE_BASE_URL
    assert kwargs["api_key"] == agent_settings.DASHSCOPE_API_KEY
    assert "extra_body" not in kwargs  # 思考开启时不传


def test_create_llm_ollama_alias():
    """按注册表 ollama 条目构造（本地模型）"""
    with patch("app.services.agent.llm.ollama.ChatOpenAI") as mock_cls:
        create_llm(alias="ollama-qwen3.5")
    mock_cls.assert_called_once()
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["base_url"] == agent_settings.OLLAMA_BASE_URL + "/v1"
    assert kwargs["model"] == "qwen3.5:9b"
    assert kwargs["api_key"] == "ollama"


def test_create_llm_planner_alias():
    """planner 条目：dashscope + 独立模型 + 思考开 + 非流式默认（来自注册表）"""
    with patch("app.services.agent.llm.dashscope.ChatOpenAI") as mock_cls:
        create_llm(alias="planner")
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["model"] == "qwen3.7-flash-2026-07-15"
    assert kwargs["streaming"] is False


def test_create_llm_runtime_override():
    """运行时覆盖 streaming/enable_thinking/max_tokens（节点业务决策优先于注册表）"""
    with patch("app.services.agent.llm.dashscope.ChatOpenAI") as mock_cls:
        create_llm(alias="qwen3.7-flash", streaming=False, enable_thinking=False, max_tokens=100)
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["streaming"] is False
    assert kwargs["max_tokens"] == 100
    assert kwargs["extra_body"] == {"enable_thinking": False}


def test_create_llm_unknown_alias_raises():
    """未知 alias 抛 ValueError（防拼错静默用错模型，白名单由注册表承担）"""
    with pytest.raises(ValueError):
        create_llm(alias="qwen3.7-flsh")


def test_create_llm_default_falls_back_to_local():
    """alias 缺省回退本地 ollama（向后兼容）"""
    with patch("app.services.agent.llm.ollama.ChatOpenAI") as mock_cls:
        create_llm()
    mock_cls.assert_called_once()
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["base_url"] == agent_settings.OLLAMA_BASE_URL + "/v1"