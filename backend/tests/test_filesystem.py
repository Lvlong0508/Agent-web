# backend/tests/test_filesystem.py
"""文件系统工具测试：list_dir_contents 列出目录第一层内容（不递归）"""

import pytest

from app.utils.filesystem import list_dir_contents


def _make_tree(root):
    """构造测试目录树：含子目录、文件、嵌套子目录"""
    (root / "sub1").mkdir(parents=True)
    (root / "sub2").mkdir()
    (root / "sub1" / "nested").mkdir()  # 嵌套目录，不应出现在第一层
    (root / "a.txt").write_text("a", encoding="utf-8")
    (root / "b.md").write_text("b", encoding="utf-8")
    return root


def test_lists_subdirs_and_files(tmp_path):
    """正常目录：子目录与文件分别返回，嵌套子目录不出现（不递归）"""
    root = _make_tree(tmp_path)
    subdirs, files = list_dir_contents(root)
    assert sorted(p.name for p in subdirs) == ["sub1", "sub2"]
    assert sorted(p.name for p in files) == ["a.txt", "b.md"]


def test_empty_dir(tmp_path):
    """空目录：返回两个空列表"""
    subdirs, files = list_dir_contents(tmp_path)
    assert subdirs == []
    assert files == []


def test_missing_dir(tmp_path):
    """目录不存在：返回两个空列表（与 loader 降级行为一致，不抛异常）"""
    subdirs, files = list_dir_contents(tmp_path / "not-exist")
    assert subdirs == []
    assert files == []


def test_return_order_deterministic(tmp_path):
    """返回顺序确定性：目录内先子目录后文件，各自有序（依赖 Path.iterdir 顺序）
    说明：iterdir 本身不保证顺序，但按路径排序后结果稳定，测试只校验集合内容"""
    root = _make_tree(tmp_path)
    subdirs, files = list_dir_contents(root)
    assert {p.name for p in subdirs} == {"sub1", "sub2"}
    assert {p.name for p in files} == {"a.txt", "b.md"}


def test_returns_path_objects(tmp_path):
    """返回值是 Path 对象（保留完整路径，调用方可自行取 name/拼接）"""
    root = _make_tree(tmp_path)
    subdirs, _ = list_dir_contents(root)
    assert all(isinstance(p, type(tmp_path)) for p in subdirs)