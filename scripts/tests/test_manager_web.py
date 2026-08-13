"""网页版服务管理器 - 进程管理核心逻辑测试"""
import asyncio
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


def test_log_buffer_append_and_all_lines():
    """日志缓冲区应能追加并返回全部行"""
    buf = manager_web.LogBuffer()
    buf.append("line1")
    buf.append("line2")
    assert buf.all_lines() == ["line1", "line2"]


def test_log_buffer_clear():
    """clear 后缓冲区应为空"""
    buf = manager_web.LogBuffer()
    buf.append("line1")
    buf.clear()
    assert buf.all_lines() == []


def test_log_buffer_maxlen_evicts_oldest():
    """超过 maxlen 时最旧的行被丢弃"""
    buf = manager_web.LogBuffer(maxlen=3)
    for i in range(5):
        buf.append(f"line{i}")
    assert buf.all_lines() == ["line2", "line3", "line4"]


def test_log_buffer_full_no_stall():
    """缓冲区满后增量读取仍能继续（回归：序号停滞导致日志冻结）"""
    buf = manager_web.LogBuffer(maxlen=3)
    for i in range(3):
        buf.append(f"line{i}")
    new_lines, total = buf.lines_from(0)
    assert new_lines == ["line0", "line1", "line2"] and total == 3
    # 继续写入超过 maxlen，total 序号仍在增长
    buf.append("line3")
    buf.append("line4")
    new_lines, total = buf.lines_from(total)
    assert new_lines == ["line3", "line4"] and total == 5


def test_log_buffer_lines_from_incremental():
    """lines_from 应返回增量行并给出新的总行数"""
    buf = manager_web.LogBuffer()
    buf.append("a")
    buf.append("b")
    new_lines, total = buf.lines_from(0)
    assert new_lines == ["a", "b"] and total == 2
    buf.append("c")
    new_lines, total = buf.lines_from(total)
    assert new_lines == ["c"] and total == 3


def test_event_stream_sends_history():
    """SSE 生成器第一条消息应是历史日志 data 行"""
    buf = manager_web._ensure_buffer("backend")
    buf.clear()
    buf.append("hello-from-fake")

    async def collect_first():
        stream = manager_web.event_stream("backend")
        first = await anext(stream)
        await stream.aclose()
        return first

    first = asyncio.run(collect_first())
    assert first == "data: hello-from-fake\n\n"


def test_event_stream_unknown_service_raises():
    """未知服务的日志流应抛 ValueError（与 start/stop 一致）"""
    async def collect():
        stream = manager_web.event_stream("database")
        try:
            await anext(stream)
        finally:
            # 无论是否抛错都关闭生成器，避免资源泄漏
            await stream.aclose()

    with pytest.raises(ValueError):
        asyncio.run(collect())
