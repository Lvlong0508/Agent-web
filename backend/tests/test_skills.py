# backend/tests/test_skills.py
"""技能机制测试：SkillLoader 扫描解析、read_skill 工具、索引文本格式"""

import pytest

from app.services.agent.skills import get_skills_index_prompt
from app.services.agent.skills.loader import SkillLoader
from app.services.agent.skills.tool import build_skill_tools

# 合法 SKILL.md：frontmatter 含 name/description，正文在 --- 之后
VALID_SKILL = """---
name: accounting-expert
description: 专业记账知识：账单分类规则、消费分析、预算建议。当用户询问账单分类建议、消费习惯分析、预算规划时使用。
---

# 记账专家

## 目标
在账单查询结果基础上提供记账领域知识。
"""

# frontmatter 解析失败的 SKILL.md（YAML 语法错误）
BROKEN_SKILL = """---
name: broken
description: [未闭合
---

正文
"""

# 无 frontmatter 的文件（既不是 SKILL.md 格式）
NO_FRONTMATTER = "这只是一个普通 markdown 文件"


def _write_skill(tmp_path, dir_name, content):
    """在临时目录下创建一个技能目录并写入 SKILL.md"""
    d = tmp_path / dir_name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(content, encoding="utf-8")


def test_loader_scans_valid_skill(tmp_path):
    """正常 SKILL.md 被扫描进索引：name/description/body 正确解析"""
    _write_skill(tmp_path, "accounting-expert", VALID_SKILL)
    loader = SkillLoader(tmp_path)
    assert loader.skill_names() == ["accounting-expert"]
    body = loader.get_skill_body("accounting-expert")
    assert body is not None
    assert "# 记账专家" in body
    assert "## 目标" in body


def test_loader_skips_broken_frontmatter(tmp_path):
    """frontmatter 解析失败的技能被跳过，不阻塞其他技能与主流程"""
    _write_skill(tmp_path, "good", VALID_SKILL)
    _write_skill(tmp_path, "broken", BROKEN_SKILL)
    _write_skill(tmp_path, "nofront", NO_FRONTMATTER)
    loader = SkillLoader(tmp_path)
    # 只保留解析成功的技能（技能名取 frontmatter 的 name，与目录名无关）
    assert loader.skill_names() == ["accounting-expert"]


def test_loader_missing_dir_returns_empty(tmp_path):
    """技能目录不存在/为空 → 空索引，get_index_prompt 返回空串"""
    loader = SkillLoader(tmp_path / "not-exist")
    assert loader.skill_names() == []
    assert loader.get_index_prompt() == ""


def test_loader_requires_name_and_description(tmp_path):
    """frontmatter 缺 name 或 description 的技能被视为无效跳过"""
    _write_skill(tmp_path, "no-desc", """---
name: only-name
---

正文
""")
    loader = SkillLoader(tmp_path)
    assert loader.skill_names() == []


def test_loader_index_prompt_format(tmp_path):
    """索引文本包含"可用技能"引导句 + 每行 - **name**: description"""
    _write_skill(tmp_path, "accounting-expert", VALID_SKILL)
    loader = SkillLoader(tmp_path)
    prompt = loader.get_index_prompt()
    assert "## 可用技能" in prompt
    assert "read_skill" in prompt
    assert "**accounting-expert**" in prompt
    assert "记账知识" in prompt


def test_loader_skips_file_with_bad_encoding(tmp_path):
    """非 UTF-8 编码的 SKILL.md 只跳过该技能，不影响其他技能加载
    （降级契约：坏文件绝不阻塞整个扫描）"""
    _write_skill(tmp_path, "good", VALID_SKILL)
    bad_dir = tmp_path / "bad-encoding"
    bad_dir.mkdir(parents=True)
    # 写入 GBK 编码文件（UTF-8 解码必然失败）
    (bad_dir / "SKILL.md").write_bytes("---\nname: 乱码\n---\n正文".encode("gbk"))
    loader = SkillLoader(tmp_path)
    # 好技能正常加载，坏编码技能被跳过
    assert loader.skill_names() == ["accounting-expert"]


def test_get_skills_index_prompt_uses_singleton(monkeypatch, tmp_path):
    """get_skills_index_prompt 透传单例 loader 的索引文本（monkeypatch 换 loader）"""
    _write_skill(tmp_path, "accounting-expert", VALID_SKILL)
    test_loader = SkillLoader(tmp_path)
    # 替换包级单例：生产环境单例指向 settings.SKILLS_DIR，测试注入临时目录
    monkeypatch.setattr("app.services.agent.skills.loader", test_loader)
    prompt = get_skills_index_prompt()
    assert "**accounting-expert**" in prompt


@pytest.mark.asyncio
async def test_read_skill_returns_body(monkeypatch, tmp_path):
    """read_skill 返回 [技能 name]\n正文"""
    _write_skill(tmp_path, "accounting-expert", VALID_SKILL)
    test_loader = SkillLoader(tmp_path)
    # 替换工具闭包引用的包级 loader 单例
    monkeypatch.setattr("app.services.agent.skills.tool.loader", test_loader)
    tools = {t.name: t for t in build_skill_tools()}
    result = await tools["read_skill"].ainvoke({"name": "accounting-expert"})
    assert "[技能 accounting-expert]" in result
    assert "# 记账专家" in result


@pytest.mark.asyncio
async def test_read_skill_unknown_name_returns_friendly_error(monkeypatch, tmp_path):
    """未知名返回友好错误提示，不抛异常（降级）"""
    _write_skill(tmp_path, "accounting-expert", VALID_SKILL)
    test_loader = SkillLoader(tmp_path)
    monkeypatch.setattr("app.services.agent.skills.tool.loader", test_loader)
    tools = {t.name: t for t in build_skill_tools()}
    result = await tools["read_skill"].ainvoke({"name": "no-such-skill"})
    assert "未找到技能" in result
    assert "no-such-skill" in result


def test_build_skill_tools_returns_read_skill():
    """工具工厂只返回 read_skill 一个工具"""
    tools = build_skill_tools()
    assert [t.name for t in tools] == ["read_skill"]