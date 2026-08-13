"""网页版前后端服务管理器

职责：在浏览器中管理项目的前后端服务（启动/停止/重启）并实时查看日志。
独立运行在 127.0.0.1:8001，不干扰业务后端(8000)与 Vite(5173)。
"""
import subprocess
import threading
import time
from collections import deque

from manager import BACKEND_CMD, FRONTEND_CMD  # 复用终端版的启动命令

# 各服务的启动命令
SERVICE_COMMANDS = {
    "backend": BACKEND_CMD,
    "frontend": FRONTEND_CMD,
}

# 全局持有各服务的 subprocess 对象
processes = {"backend": None, "frontend": None}
# 各服务进程的启动时间戳，用于页面显示运行时长
started_at = {"backend": None, "frontend": None}
# 各服务的日志环形缓冲区
buffers = {"backend": None, "frontend": None}


class LogBuffer:
    """线程安全的日志环形缓冲：子进程输出先写入这里，SSE 再从增量读取"""

    def __init__(self, maxlen=2000):
        # deque(maxlen) 满了会自动丢弃最旧的行，防止内存无限增长
        self._lines = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def append(self, line):
        """追加一行日志"""
        with self._lock:
            self._lines.append(line)

    def clear(self):
        """清空缓冲区（服务重启时调用）"""
        with self._lock:
            self._lines.clear()

    def all_lines(self):
        """返回全部历史日志"""
        with self._lock:
            return list(self._lines)

    def lines_from(self, start_index):
        """返回从 start_index 开始的增量日志与当前总行数

        调用方记住返回的总行数作为下一次的 start_index 即可实现增量读取。
        """
        with self._lock:
            lines = list(self._lines)
        # 若 start_index 对应位置已超出当前范围，回退到最早的可用位置
        if start_index < 0:
            start_index = 0
        if start_index > len(lines):
            start_index = 0
        return lines[start_index:], len(lines)


def _ensure_buffer(name):
    """懒初始化日志缓冲区"""
    if buffers.get(name) is None:
        buffers[name] = LogBuffer()
    return buffers[name]


def _read_output(proc, name):
    """后台线程：持续读取子进程 stdout 并写入日志缓冲区"""
    buf = _ensure_buffer(name)
    for line in iter(proc.stdout.readline, ""):
        if line:
            # strip 掉末尾换行，避免日志区出现多余空行
            buf.append(line.strip())
    proc.stdout.close()


def start(name):
    """启动指定服务；已运行则返回友好提示"""
    if name not in SERVICE_COMMANDS:
        raise ValueError(f"未知服务: {name}")

    proc = processes.get(name)
    if proc and proc.poll() is None:
        return {"ok": False, "message": f"{name} 已在运行中 (PID: {proc.pid})"}

    cmd = SERVICE_COMMANDS[name]
    # shell=True 以支持 cd /d 与管道组合的 Windows 命令
    proc = subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # 合并 stderr 到 stdout，日志完整不丢失
        text=True,
        encoding="utf-8",
        errors="replace",  # 避免个别非 UTF-8 字节导致读取崩溃
        bufsize=1,
    )
    processes[name] = proc
    started_at[name] = time.time()
    # 新进程从零开始记日志，清空上一轮残留
    _ensure_buffer(name).clear()

    # 启动后台线程持续读取输出
    threading.Thread(target=_read_output, args=(proc, name), daemon=True).start()
    return {"ok": True, "message": f"{name} 已启动 (PID: {proc.pid})"}


def _kill_tree(pid):
    """递归杀掉以 pid 为根的整棵进程树

    Windows 下 shell=True 启动的实际是 cmd.exe 中间层，仅 terminate 只杀
    cmd.exe，真正的服务子进程会成为孤儿继续占用端口，必须用 taskkill /t
    把整棵树一并清除。
    """
    subprocess.run(
        f"taskkill /f /t /pid {pid}",
        shell=True,
        capture_output=True,
    )


def stop(name):
    """停止指定服务；未运行则返回友好提示"""
    proc = processes.get(name)
    if not proc or proc.poll() is not None:
        return {"ok": False, "message": f"{name} 未在运行"}

    pid = proc.pid
    # 必须先杀树再终止：若根进程已退出，taskkill /t 将找不到其后代
    # 子进程，孤儿会残留。根进程存活时枚举树，后代才能一并被清除。
    _kill_tree(pid)
    try:
        # 根进程被 taskkill 清除后 wait 立即返回
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        # 极端情况根进程未随树退出，则强制结束
        proc.kill()
    processes[name] = None
    started_at[name] = None
    return {"ok": True, "message": f"{name} 已停止"}


def restart(name):
    """重启指定服务：先停止，等 1 秒再启动"""
    stop(name)
    time.sleep(1)
    return start(name)


def get_status(name):
    """查询服务状态，返回可 JSON 序列化的字典"""
    proc = processes.get(name)
    if proc and proc.poll() is None:
        elapsed = int(time.time() - started_at.get(name, time.time()))
        return {
            "name": name,
            "running": True,
            "pid": proc.pid,
            "elapsed": elapsed,  # 运行秒数，供页面显示运行时长
        }
    return {"name": name, "running": False, "pid": None, "elapsed": 0}
