from pathlib import Path
from typing import ClassVar

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    backend_host: str = "localhost"   # 提供默认值
    backend_port: int = 8088

    # 单用户模式：所有聊天数据的固定归属 ID
    DEFAULT_USER_ID: str = "anonymous"

    # backend 根目录：settings.py 在 backend/app/config/，parents[2] 即 backend/
    # （parents[0]=config, [1]=app, [2]=backend，实测验证）
    BASE_DIR: ClassVar[Path] = Path(__file__).resolve().parents[2]

    # extra="ignore"：数据库配置在 database_settings.py、大模型配置在 agent_settings.py，
    # .env 中这两类变量不属本类，忽略即可（完全未知的键由 env_audit 提醒）
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


# 全局单例配置对象（导入即加载 .env）
settings = Settings()