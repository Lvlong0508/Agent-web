"""llm 包测试：验证 create_llm 厂商级粗分发 + 厂商内模型级分发"""

from unittest.mock import patch

import pytest

from app.config.settings import settings
from app.services.agent.llm import create_llm


def test_ollama_model():
    """按 ollama-qwen3.5 选择名创建 Ollama 配置的 LLM"""
    with patch("app.services.agent.llm.ollama.ChatOpenAI") as mock_cls:
        create_llm(streaming=True, model=settings.MODEL_OLLAMA)
    mock_cls.assert_called_once()
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["base_url"] == settings.OLLAMA_BASE_URL + "/v1"
    assert kwargs["model"] == settings.LLM_MODEL
    assert kwargs["api_key"] == "ollama"
    assert kwargs["streaming"] is True


def test_dashscope_model():
    """按 qwen3.7-flash 选择名创建 DashScope 配置的 LLM"""
    with patch("app.services.agent.llm.dashscope.ChatOpenAI") as mock_cls:
        create_llm(streaming=False, model=settings.MODEL_DASHSCOPE_QWEN)
    mock_cls.assert_called_once()
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["base_url"] == settings.DASHSCOPE_BASE_URL
    assert kwargs["model"] == settings.DASHSCOPE_MODEL
    assert kwargs["api_key"] == settings.DASHSCOPE_API_KEY
    assert kwargs["streaming"] is False


def test_dashscope_disables_thinking_for_title():
    """标题场景：关闭思考模式并限制 max_tokens，让标题秒回不被思考拖慢"""
    with patch("app.services.agent.llm.dashscope.ChatOpenAI") as mock_cls:
        create_llm(
            streaming=False,
            model=settings.MODEL_DASHSCOPE_QWEN,
            enable_thinking=False,
            max_tokens=100,
        )
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["max_tokens"] == 100
    # DashScope 兼容模式通过 extra_body 关闭思考
    assert kwargs["extra_body"] == {"enable_thinking": False}


def test_ollama_ignores_thinking_params():
    """Ollama 分支不受思考参数影响：不传 extra_body / max_tokens"""
    with patch("app.services.agent.llm.ollama.ChatOpenAI") as mock_cls:
        create_llm(
            streaming=True,
            model=settings.MODEL_OLLAMA,
            enable_thinking=False,
            max_tokens=100,
        )
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["base_url"] == settings.OLLAMA_BASE_URL + "/v1"
    assert kwargs["model"] == settings.LLM_MODEL
    assert "extra_body" not in kwargs
    assert "max_tokens" not in kwargs


def test_unknown_model_raises():
    """非空未知选择名抛 ValueError，避免静默回退掩盖配置漂移"""
    with pytest.raises(ValueError):
        create_llm(model="qwen3.7-flsh")  # 拼错的选择名


def test_default_falls_back_to_ollama():
    """未指定 model 时回退本地 Ollama（向后兼容）"""
    with patch("app.services.agent.llm.ollama.ChatOpenAI") as mock_cls:
        create_llm(streaming=True)
    mock_cls.assert_called_once()
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["base_url"] == settings.OLLAMA_BASE_URL + "/v1"
    assert kwargs["model"] == settings.LLM_MODEL
    assert kwargs["api_key"] == "ollama"
