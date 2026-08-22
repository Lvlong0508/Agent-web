"""数据库连接与命名配置：MongoDB / MySQL / Chroma 三类存储的连接参数与表/集合名映射。

从原 settings.py 拆出，职责划分：
- settings.py：应用级配置（服务地址、用户归属、路径）
- agent_settings.py：大模型配置（模型注册表、LLM 厂商、向量模型、planner、skill）
- database_settings.py：数据存储接入（连接参数 + 命名映射）

三类配置共享同一个 .env，各用 extra="ignore" 只认领自己的字段。
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """数据库连接与命名配置：MongoDB / MySQL / Chroma 统一管理"""

    # ---- MongoDB ----
    MONGODB_URI: str
    MONGODB_DB_NAME: str
    # 集合名映射：key 是代码引用的逻辑名，value 是真实集合名（env 可 JSON 覆盖）
    MONGODB_COLLECTIONS: dict[str, str] = {
        "agent_runs": "agent_runs",
        "conversations": "conversations",
        "messages": "messages",
    }

    # ---- MySQL ----
    # 凭据（用户名/密码）不设默认值：必须从 .env 读取，避免敏感信息出现在代码中
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str
    MYSQL_PASSWORD: str
    MYSQL_DB_NAME: str = "agent-web"
    # 表名映射：key 是代码引用的逻辑名，value 是真实表名（env 可 JSON 覆盖）
    MYSQL_TABLES: dict[str, str] = {"expense": "expenses"}

    # ---- Chroma 向量库 ----
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8000
    # 隔离：tenant 保持默认 default_tenant，database 用项目名与其他项目分开
    # （database 隔离后，集合名无需加项目前缀）
    CHROMA_TENANT: str = "default_tenant"
    CHROMA_DATABASE: str = "agent-web"
    # 集合名映射：key 是 kb_type 逻辑名，value 是真实集合名（env 可 JSON 覆盖）
    CHROMA_COLLECTIONS: dict[str, str] = {
        "enterprise": "kb_enterprise",  # 企业公共知识库（全体用户可查）
        "user": "kb_user",              # 用户私有知识库（owner_id 隔离）
        "tool": "kb_tools",             # AI 工具库（预留：按需装配 tool）
        "skill": "kb_skills",           # skill 库（预留：按需装配 skill）
    }

    # extra="ignore"：.env 里非数据库的变量（DASHSCOPE_*、MODEL_* 等）不属本类，忽略
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# 全局单例配置对象（导入即加载 .env）
database_settings = DatabaseSettings()