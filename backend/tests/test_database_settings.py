"""DatabaseSettings 测试：三类数据库（MongoDB/MySQL/Chroma）连接配置默认值 + 命名映射"""

from app.config import database_settings


def test_mongodb_config_defaults():
    """MongoDB 集合名映射：agent_runs / conversations / messages"""
    assert database_settings.MONGODB_COLLECTIONS == {
        "agent_runs": "agent_runs",
        "conversations": "conversations",
        "messages": "messages",
    }


def test_mysql_config_defaults():
    """MySQL 表名映射与库名：expense -> expenses，库名 agent-web"""
    assert database_settings.MYSQL_TABLES == {"expense": "expenses"}
    assert database_settings.MYSQL_DB_NAME == "agent-web"


def test_chroma_config_defaults():
    """Chroma 连接默认值：localhost:8000，tenant 保持默认，database 用项目名隔离"""
    assert database_settings.CHROMA_HOST == "localhost"
    assert database_settings.CHROMA_PORT == 8000
    assert database_settings.CHROMA_TENANT == "default_tenant"
    assert database_settings.CHROMA_DATABASE == "agent-web"
    # 集合名映射：kb_type -> collection 名
    assert database_settings.CHROMA_COLLECTIONS == {
        "enterprise": "kb_enterprise",
        "user": "kb_user",
        "tool": "kb_tools",
        "skill": "kb_skills",
    }