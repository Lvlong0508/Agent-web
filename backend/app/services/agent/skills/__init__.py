"""技能机制包出口：模块级 loader 单例与索引文本工厂。

- loader：进程内单例，构造时扫描 settings.SKILLS_DIR 一次并缓存（运行期只读）
- get_skills_index_prompt()：供 chat_service 注入 system prompt 的 L0 索引文本。
  用函数而非直接暴露 loader，调用方不依赖单例内部结构，测试可 monkeypatch
  包级 loader 变量以注入临时技能目录
"""

from pathlib import Path

from app.config.settings import settings
from app.services.agent.skills.loader import SkillLoader

# 进程内单例：路径由 settings 配置（相对 BASE_DIR 或绝对），换位置只需改 .env
_skills_path = Path(settings.SKILLS_DIR)
if not _skills_path.is_absolute():
    _skills_path = settings.BASE_DIR / _skills_path
loader = SkillLoader(_skills_path)


def get_skills_index_prompt() -> str:
    """返回技能索引清单文本（L0），无技能时返回空串；供 build_agent_messages 注入"""
    return loader.get_index_prompt()


__all__ = ["SkillLoader", "get_skills_index_prompt", "loader"]