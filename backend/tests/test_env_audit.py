"""配置审计测试：.env 中未被任何配置类认领的键应触发 warning"""

import logging
from unittest.mock import patch

from app.config import audit_env


def test_audit_env_warns_unknown_key(caplog):
    """未知键（不属于 Settings/AgentSettings/DatabaseSettings）应打 warning"""
    fake_env = {"MYSQL_USER": "agentweb", "SOME_TYPO": "value"}
    with caplog.at_level(logging.WARNING), patch(
        "app.config.dotenv_values", return_value=fake_env
    ):
        audit_env()
    assert "SOME_TYPO" in caplog.text


def test_audit_env_silent_when_all_known(caplog):
    """所有键都被某配置类认领时不应告警"""
    fake_env = {"MYSQL_USER": "agentweb", "CHROMA_HOST": "localhost"}
    with caplog.at_level(logging.WARNING), patch(
        "app.config.dotenv_values", return_value=fake_env
    ):
        audit_env()
    assert "未被任何配置类认领" not in caplog.text