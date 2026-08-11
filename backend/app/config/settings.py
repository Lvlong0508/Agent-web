from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 单用户模式：所有聊天数据的固定归属 ID
    DEFAULT_USER_ID: str = "anonymous"

    # MongoDB 连接配置
    MONGODB_URI: str
    MONGODB_DB_NAME: str

    # Ollama 本地 LLM 配置
    OLLAMA_BASE_URL: str = "http://localhost:11434"  # Ollama 服务地址
    LLM_MODEL: str = "glm-4.7-flash"                  # 本地部署的模型名

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


# 全局单例配置对象（导入即加载 .env）
settings = Settings()
