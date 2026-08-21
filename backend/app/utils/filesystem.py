"""文件系统工具：纯文件操作，无业务语义，供各服务跨模块复用。

设计约定（README 分层手册"顶层包职责"）：
- 本模块只做"文件系统"这一件事，不关心读取内容是技能还是知识库文档
- 目录不存在一律返回空列表（降级行为），绝不抛异常——调用方据此可放心
  在"可选目录"上调用，与 skill loader / 未来企业知识库的降级契约一致
- 返回 Path 对象而非名字符串：保留完整路径，调用方可自行取 name 或继续拼接
"""

from pathlib import Path


def list_dir_contents(path: Path) -> tuple[list[Path], list[Path]]:
    """列出目录下第一层内容，不递归深入子目录。

    Args:
        path: 要扫描的目录（Path 对象）

    Returns:
        (子目录列表, 文件列表)。目录不存在或为空时返回两个空列表。

    说明：
    - 不递归：嵌套子目录内的内容不会出现（调用方需要深扫时应自行递归，
      本函数保持"一层扫描"的单一职责）
    - 目录与文件分类返回，调用方按需取用（如 skill loader 只关心子目录，
      未来知识库扫描可能同时要文件）
    """
    if not path.is_dir():
        return [], []

    subdirs: list[Path] = []
    files: list[Path] = []
    for entry in path.iterdir():
        if entry.is_dir():
            subdirs.append(entry)
        else:
            files.append(entry)
    return subdirs, files