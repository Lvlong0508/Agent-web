"""技能加载器：扫描 skills 根目录下各技能目录的 SKILL.md，解析 frontmatter
生成技能索引（L0）与正文缓存（L1）。

设计要点（spec 2026-08-18）：
- L0 索引：name + description 清单注入 system prompt，agent 据此判断何时调 read_skill
- L1 正文：完整 markdown，agent 按需经 read_skill 工具加载
- 降级：某技能文件缺失/frontmatter 解析失败时跳过该技能，绝不阻塞其他技能与主流程
"""

from pathlib import Path

import yaml

from app.utils.filesystem import list_dir_contents


class SkillLoader:
    """技能加载器：构造时扫描一次并缓存索引，运行期只读"""

    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        self._index: list[dict] = []  # [{name, description, body}]
        self._scan()

    def _scan(self) -> None:
        """遍历技能根目录的顶层子目录，读取每个 SKILL.md 并解析进索引；
        目录不存在时索引为空（skill 机制对主流程完全透明）"""
        subdirs, _ = list_dir_contents(self.skills_dir)
        for child in subdirs:
            # 只扫顶层目录，不递归子目录（防止把 references/ 等资源目录当技能）
            md_file = child / "SKILL.md"
            if not md_file.is_file():
                continue
            try:
                # 读+解析整体保护：单个技能文件读取失败（如编码异常）只跳过该技能，
                # 不得让整个扫描崩溃（spec 降级契约：坏技能不阻塞好技能与主流程）
                skill = self._parse_skill_md(md_file.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, OSError):
                continue
            if skill:
                skill["mtime"] = md_file.stat().st_mtime
                self._index.append(skill)

    @staticmethod
    def _parse_skill_md(content: str) -> dict | None:
        """解析单个 SKILL.md：提取 frontmatter 的 name/description，正文取
        frontmatter 之后部分；解析失败返回 None（该技能被跳过）"""
        # 必须以 --- 开头才是带 frontmatter 的技能文件
        if not content.startswith("---"):
            return None
        parts = content.split("---", 2)
        if len(parts) < 3:
            return None
        try:
            meta = yaml.safe_load(parts[1])
        except yaml.YAMLError:
            return None
        # meta 必须是非空 dict，且 name/description 均为非空字符串
        if not isinstance(meta, dict):
            return None
        name = meta.get("name")
        description = meta.get("description")
        if not isinstance(name, str) or not name:
            return None
        if not isinstance(description, str) or not description:
            return None
        return {
            "name": name,
            "description": description,
            "body": parts[2].strip(),
        }

    def get_index_prompt(self) -> str:
        """L0：生成"可用技能"清单文本（对齐 Claude Code / LangChain 验证过的格式），
        无技能时返回空串（不污染 system prompt）"""
        if not self._index:
            return ""
        lines = [
            "## 可用技能",
            "",
            "当任务匹配某技能的描述时，调用 read_skill 工具加载该技能的完整说明。",
            "",
        ]
        for skill in self._index:
            lines.append(f"- **{skill['name']}**: {skill['description']}")
        return "\n".join(lines)

    def get_skill_body(self, name: str) -> str | None:
        """L1：按技能名返回完整正文；未知名返回 None"""
        for skill in self._index:
            if skill["name"] == name:
                return skill["body"]
        return None

    def skill_names(self) -> list[str]:
        """返回所有已加载技能名（测试与诊断用）"""
        return [skill["name"] for skill in self._index]

    def skills(self) -> list[dict]:
        return [dict(s) for s in self._index]

    def get_skill(self, name: str) -> dict | None:
        for skill in self._index:
            if skill["name"] == name:
                return dict(skill)
        return None