from pathlib import Path
from typing import ClassVar

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 单用户模式：所有聊天数据的固定归属 ID
    DEFAULT_USER_ID: str = "anonymous"

    # backend 根目录：settings.py 在 backend/app/config/，parents[2] 即 backend/
    # （parents[0]=config, [1]=app, [2]=backend，实测验证）
    BASE_DIR: ClassVar[Path] = Path(__file__).resolve().parents[2]

    # Skill 根目录配置：相对 BASE_DIR 的路径，可经 .env 调整
    SKILLS_DIR: str = "skills"

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

    # Ollama 本地 LLM 配置
    OLLAMA_BASE_URL: str = "http://localhost:11434"  # Ollama 服务地址
    LLM_MODEL: str = "qwen3.5:9b"                  # 本地部署的模型名

    # DashScope 通义千问配置（API Key 从 .env 读取）
    DASHSCOPE_API_KEY: str = ""                     # 阿里云百炼 API Key
    DASHSCOPE_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    DASHSCOPE_MODEL: str = "qwen3.7-flash"          # 通义千问模型名

    # 模型选择名（前端下拉值与 API model 字段共用，前后端需保持一致）
    # ClassVar 声明为类常量而非 pydantic 字段，因此不需要 default 也不读 env
    MODEL_OLLAMA: ClassVar[str] = "ollama-qwen3.5"          # 对应本地 Ollama
    MODEL_DASHSCOPE_QWEN: ClassVar[str] = "qwen3.7-flash"   # 对应通义千问

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


# 全局单例配置对象（导入即加载 .env）
settings = Settings()
