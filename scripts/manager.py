import os
import subprocess
import threading
import time
import signal
import sys

# 项目根目录（manager.py 在 scripts 目录下，其上一级才是项目根）
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 后端与前端路径
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend", "AgentWeb-user")

# 后端启动命令（推荐使用 conda run 避免激活问题）
# 如果 conda run 不可用，可以改为直接使用环境中的 python 解释器
# 例如：r"C:\Users\你的用户名\anaconda3\envs\agent-web\python.exe -m uvicorn app.main:app ..."
BACKEND_CMD = (
    f'cd /d "{BACKEND_DIR}" && '
    f'conda run -n agent-web uvicorn app.main:app --reload --host 0.0.0.0 --port 8000'
)

# 前端启动命令（包含清理旧 vite 进程）
# 注意：for 循环用括号包裹并用 & 与 npm 连接，而不是把 && npm 放在 do 里。
# 否则当没有 vite 进程需要清理时，for 循环体一次都不执行，npm run dev 也不会执行。
FRONTEND_CMD = (
    f'cd /d "{FRONTEND_DIR}" && '
    f'(for /f "tokens=2" %a in (\'tasklist /fi "imagename eq node.exe" /nh ^| findstr /i vite\') '
    f'do taskkill /f /pid %a >nul 2>&1) & '
    f'npm run dev'
)

# 存储子进程的字典
processes = {
    "backend": None,
    "frontend": None
}

# 日志输出锁，防止多线程打印混乱
print_lock = threading.Lock()

def log(name, message):
    """打印带前缀的日志"""
    with print_lock:
        print(f"[{name}] {message.strip()}")

def read_output(proc, name):
    """读取子进程输出并打印"""
    for line in iter(proc.stdout.readline, ''):
        if line:
            log(name, line)
    # 当进程退出时，读取结束
    proc.stdout.close()

def start_process(name):
    """启动指定服务"""
    if processes[name] and processes[name].poll() is None:
        print(f"{name} 已经在运行中 (PID: {processes[name].pid})")
        return

    if name == "backend":
        cmd = BACKEND_CMD
    elif name == "frontend":
        cmd = FRONTEND_CMD
    else:
        print("未知服务名")
        return

    print(f"正在启动 {name} ...")
    proc = subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # 合并 stderr 到 stdout
        text=True,
        encoding='utf-8',
        errors='replace',
        bufsize=1,
        universal_newlines=True
    )
    processes[name] = proc

    # 启动线程读取输出
    thread = threading.Thread(target=read_output, args=(proc, name), daemon=True)
    thread.start()

def stop_process(name):
    """停止指定服务"""
    proc = processes.get(name)
    if proc and proc.poll() is None:
        print(f"正在停止 {name} (PID: {proc.pid}) ...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print(f"{name} 未在5秒内终止，强制结束...")
            proc.kill()
        processes[name] = None
        print(f"{name} 已停止")
    else:
        print(f"{name} 未在运行")

def stop_all():
    """停止所有服务"""
    stop_process("backend")
    stop_process("frontend")

def show_status():
    """显示服务状态"""
    for name, proc in processes.items():
        if proc and proc.poll() is None:
            print(f"{name:10} 运行中 (PID: {proc.pid})")
        else:
            print(f"{name:10} 已停止")

def interactive_shell():
    """交互式命令循环"""
    print("=" * 50)
    print("前端+后端服务管理器")
    print("可用命令：")
    print("  start backend   - 启动后端")
    print("  start frontend  - 启动前端")
    print("  start all       - 启动所有")
    print("  stop backend    - 停止后端")
    print("  stop frontend   - 停止前端")
    print("  stop all        - 停止所有")
    print("  status          - 查看状态")
    print("  restart <name>  - 重启指定服务 (backend/frontend/all)")
    print("  exit / quit     - 退出并停止所有服务")
    print("=" * 50)

    while True:
        try:
            user_input = input(">>> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n退出...")
            break

        if not user_input:
            continue

        parts = user_input.split()
        command = parts[0]

        if command in ("exit", "quit"):
            break
        elif command == "start":
            if len(parts) < 2:
                print("用法: start <backend|frontend|all>")
                continue
            target = parts[1]
            if target == "all":
                start_process("backend")
                start_process("frontend")
            elif target in ("backend", "frontend"):
                start_process(target)
            else:
                print("未知目标，可用: backend, frontend, all")
        elif command == "stop":
            if len(parts) < 2:
                print("用法: stop <backend|frontend|all>")
                continue
            target = parts[1]
            if target == "all":
                stop_all()
            elif target in ("backend", "frontend"):
                stop_process(target)
            else:
                print("未知目标，可用: backend, frontend, all")
        elif command == "restart":
            if len(parts) < 2:
                print("用法: restart <backend|frontend|all>")
                continue
            target = parts[1]
            if target == "all":
                stop_all()
                time.sleep(1)
                start_process("backend")
                start_process("frontend")
            elif target in ("backend", "frontend"):
                stop_process(target)
                time.sleep(1)
                start_process(target)
            else:
                print("未知目标，可用: backend, frontend, all")
        elif command == "status":
            show_status()
        else:
            print("未知命令，输入 'help' 查看帮助（或输入 exit 退出）")

def main():
    # 捕获 Ctrl+C 以确保清理
    try:
        interactive_shell()
    finally:
        print("正在清理所有子进程...")
        stop_all()
        print("所有服务已停止，退出。")

if __name__ == "__main__":
    main()
