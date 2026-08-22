"""配置包统一入口：导出三个配置类与单例，并提供 .env 审计。

职责划分：
- settings：应用级配置（服务地址、用户归属、路径）
- database_settings：数据库配置（MongoDB / MySQL / Chroma 连接 + 表/集合命名映射）
- agent_settings：大模型配置（模型注册表、LLM 厂商、向量模型、planner、skill）

调用方统一 `from app.config import settings, database_settings, agent_settings`，
无需关心具体模块；应用启动时调用 audit_env() 校验 .env 中的未知键。
"""

import logging

from dotenv import dotenv_values

from app.config.agent_settings import AgentSettings, agent_settings
from app.config.database_settings import DatabaseSettings, database_settings
from app.config.settings import Settings, settings

__all__ = [
    "Settings", "settings",
    "AgentSettings", "agent_settings",
    "DatabaseSettings", "database_settings",
    "audit_env",
]

_logger = logging.getLogger(__name__)


def audit_env() -> None:
    """扫描 .env，对未被任何配置类认领的键打 warning（防止静默失效的配置）。

    三个配置类都用 extra="ignore" 允许注入类外变量（不报错），但若某个键
    不属于任何配置类，通常是拼写错误或已废弃配置——配了也不生效，需提醒开发者。
    """
    env_values = dotenv_values(".env")
    if not env_values:
        return
    known = set()
    for cls in (Settings, AgentSettings, DatabaseSettings):
        known.update(cls.model_fields)
    # 统一大写比较：pydantic-settings 的 env 匹配大小写不敏感
    known_upper = {k.upper() for k in known}
    unknown = sorted(k for k in env_values if k.upper() not in known_upper)
    if unknown:
        _logger.warning(
            ".env 中存在未被任何配置类认领的键（配置了也不生效，请检查拼写）: %s",
            ", ".join(unknown),
        )