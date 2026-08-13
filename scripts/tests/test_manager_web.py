"""网页版服务管理器 - 进程管理核心逻辑测试"""
import sys
import os
import subprocess
import time

# 将 scripts 目录加入模块搜索路径，才能 import manager_web
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import manager_web


# 一个常驻假进程命令：输出一行后睡眠，模拟运行中的服务
FAKE_LONG = f'{sys.executable} -c "print(\'fake started\'); import time; time.sleep(60)"'
# 一个立即退出的假命令
FAKE_SHORT = f'{sys.executable} -c "print(\'fake done\')"'


@pytest.fixture(autouse=True)
def fake_commands(monkeypatch):
    """把所有服务的真实启动命令替换为假命令，避免测试真的拉起前后端"""
    for name in ("backend", "frontend"):
        monkeypatch.setitem(manager_web.SERVICE_COMMANDS, name, FAKE_LONG)
    yield
    # 测试结束后清理残留进程
    manager_web.stop("backend")
    manager_web.stop("frontend")


def test_start_makes_status_running():
    """启动后 get_status 应返回运行中并带 PID"""
    result = manager_web.start("backend")
    assert result["ok"] is True
    status = manager_web.get_status("backend")
    assert status["running"] is True
    assert status["pid"] is not None


def test_start_twice_returns_not_ok():
    """重复启动同一服务应返回 ok=False 且不产生第二个进程"""
    manager_web.start("backend")
    result = manager_web.start("backend")
    assert result["ok"] is False
    assert "已在运行" in result["message"]


def test_stop_when_running():
    """运行中停止应返回 ok=True 且状态变为已停止"""
    manager_web.start("backend")
    pid = manager_web.get_status("backend")["pid"]
    result = manager_web.stop("backend")
    assert result["ok"] is True
    assert manager_web.get_status("backend")["running"] is False
    # 用 tasklist 确认该 PID 已从系统中消失，验证进程树被真正清理
    out = subprocess.run(
        f'tasklist /fi "PID eq {pid}" /nh',
        shell=True,
        capture_output=True,
        text=True,
    ).stdout
    assert str(pid) not in out


def test_stop_when_not_running_returns_not_ok():
    """未运行时停止应返回 ok=False 的友好提示"""
    result = manager_web.stop("frontend")
    assert result["ok"] is False
    assert "未在运行" in result["message"]


def test_restart_keeps_running():
    """重启后服务仍处于运行中"""
    manager_web.start("backend")
    result = manager_web.restart("backend")
    assert result["ok"] is True
    assert manager_web.get_status("backend")["running"] is True


def test_get_status_default_stopped():
    """从未启动的服务默认状态为已停止"""
    assert manager_web.get_status("frontend")["running"] is False


def test_start_unknown_service_raises():
    """未知服务名应抛出 ValueError"""
    with pytest.raises(ValueError):
        manager_web.start("database")


def test_start_after_process_exited(monkeypatch):
    """前一个进程已退出后再次 start 应成功（poll 守卫正确识别死进程）"""
    # 临时把 backend 命令换成立即退出的 FAKE_SHORT，否则要等 sleep 60 才退出
    monkeypatch.setitem(manager_web.SERVICE_COMMANDS, "backend", FAKE_SHORT)
    manager_web.start("backend")
    # FAKE_SHORT 立即打印后退出，轮询等待其结束
    deadline = time.time() + 5
    while manager_web.processes["backend"] and manager_web.processes["backend"].poll() is None:
        if time.time() > deadline:
            break
        time.sleep(0.1)
    result = manager_web.start("backend")
    assert result["ok"] is True
