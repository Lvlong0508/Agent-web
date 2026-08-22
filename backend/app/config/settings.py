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
    # 注意：SKILLS_DIR 已迁移到 app/config/agent_settings.py（agent 模块配置独立）。
    # 模型字段（LLM_MODEL / DASHSCOPE_MODEL / MODEL_*）将在 Task 2 删除
    BASE_DIR: ClassVar[Path] = Path(__file__).resolve().parents[2]

    # MongoDB 连接配置
    MONGODB_URI: str
    MONGODB_DB_NAME: str

    # MongoDB 集合名映射：key 是代码引用的逻辑名，value 是真实集合名。
    # env 可 JSON 覆盖（统一管理，避免集合名散落硬编码在各 repository 里）
    MONGODB_COLLECTIONS: dict[str, str] = {
        "agent_runs": "agent_runs",
        "conversations": "conversations",
        "messages": "messages",
    }

    # MySQL 连接配置（SQLAlchemy async，账号仅授权 agent-web 库）
    # 凭据（用户名/密码）不设默认值：必须从 .env 读取，避免敏感信息出现在代码中
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str
    MYSQL_PASSWORD: str
    MYSQL_DB_NAME: str = "agent-web"

    # 数据命名映射：key 是代码引用的逻辑名，value 是真实表名。
    # env 可 JSON 覆盖（统一管理，避免表名散落硬编码在模型/服务里）
    MYSQL_TABLES: dict[str, str] = {"expense": "expenses"}

    # Ollama 本地 LLM 配置（模型名已迁入 AgentSettings 模型注册表）
    OLLAMA_BASE_URL: str = "http://localhost:11434"  # Ollama 服务地址

    # DashScope 通义千问配置（API Key 从 .env 读取；模型名已迁入 AgentSettings 注册表）
    DASHSCOPE_API_KEY: str = ""                     # 阿里云百炼 API Key
    DASHSCOPE_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8000
    # Chroma 隔离：tenant 保持默认，database 用项目名与其他项目分开
    # （database 隔离后，集合名无需加项目前缀，避免跨项目集合命名冲突）
    CHROMA_TENANT: str = "default_tenant"
    CHROMA_DATABASE: str = "agent-web"

    EMBEDDING_DIM: int = 1024

    # extra="ignore"：.env 里 agent 模块的变量（如 CHROMA_COLLECTIONS、MODEL_*）不属本类，
    # 忽略它们，与 AgentSettings 各认领自己的字段互不干扰
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


# 全局单例配置对象（导入即加载 .env）
settings = Settings()
