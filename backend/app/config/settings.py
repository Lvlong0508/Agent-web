from pathlib import Path
from typing import ClassVar

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 单用户模式：所有聊天数据的固定归属 ID
    DEFAULT_USER_ID: str = "anonymous"

    # backend 根目录：settings.py 在 backend/app/config/，parents[2] 即 backend/
    # （parents[0]=config, [1]=app, [2]=backend，实测验证）
    # 注意：SKILLS_DIR 已迁移到 app/config/agent_settings.py（agent 模块配置独立）。
    # 模型字段（LLM_MODEL / DASHSCOPE_MODEL / MODEL_*）将在 Task 2 删除
    BASE_DIR: ClassVar[Path] = Path(__file__).resolve().parents[2]

    # MongoDB 连接配置
    MONGODB_URI: str
    MONGODB_DB_NAME: str

    # MySQL 连接配置（SQLAlchemy async，账号仅授权 agent-web 库）
    # 凭据（用户名/密码）不设默认值：必须从 .env 读取，避免敏感信息出现在代码中
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str
    MYSQL_PASSWORD: str
    MYSQL_DB_NAME: str = "agent-web"

    # Ollama 本地 LLM 配置（模型名已迁入 AgentSettings 模型注册表）
    OLLAMA_BASE_URL: str = "http://localhost:11434"  # Ollama 服务地址

    # DashScope 通义千问配置（API Key 从 .env 读取；模型名已迁入 AgentSettings 注册表）
    DASHSCOPE_API_KEY: str = ""                     # 阿里云百炼 API Key
    DASHSCOPE_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


# 全局单例配置对象（导入即加载 .env）
settings = Settings()
