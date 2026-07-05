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
    MONGODB_URI: str = "mongodb://localhost:27017"  # MongoDB 连接地址
    MONGODB_DB_NAME: str = "agentweb"               # 数据库名

    # 通义千问 LLM 配置
    LLM_API_KEY: str          # DashScope API Key，必须从 .env 读取
    LLM_MODEL: str = "qwen-plus"  # 模型名，默认 qwen-plus

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
