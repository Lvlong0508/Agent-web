from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 数据库连接配置（所有值从 .env 读取，不留默认值）
    DB_HOST: str
    DB_PORT: int
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str

    # JWT 鉴权配置
    JWT_SECRET_KEY: str  # 密钥，必须从 .env 文件读取
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30   # 短令牌 30 分钟过期
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7      # 刷新令牌 7 天过期

    # MongoDB 连接配置
    MONGODB_URI: str
    MONGODB_DB_NAME: str

    # Ollama 本地 LLM 配置
    OLLAMA_BASE_URL: str = "http://localhost:11434"  # Ollama 服务地址
    LLM_MODEL: str = "glm-4.7-flash"                  # 本地部署的模型名

    # 动态拼接 MySQL 连接 URL
    @property
    def database_url(self) -> str:
        return (
            f"mysql+asyncmy://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


# 全局单例配置对象（导入即加载 .env）
settings = Settings()
