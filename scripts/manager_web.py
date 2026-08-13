"""网页版前后端服务管理器

职责：在浏览器中管理项目的前后端服务（启动/停止/重启）并实时查看日志。
独立运行在 127.0.0.1:8001，不干扰业务后端(8000)与 Vite(5173)。
"""
import asyncio
import os
import subprocess
import threading
import time
import webbrowser
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
        # 累计写入的行数（含被 maxlen 淘汰的行），作为单调递增的日志序号
        self._count = 0
        self._lock = threading.Lock()

    def append(self, line):
        """追加一行日志"""
        with self._lock:
            self._lines.append(line)
            self._count += 1

    def clear(self):
        """清空缓冲区（服务重启时调用），序号同步归零"""
        with self._lock:
            self._lines.clear()
            self._count = 0

    def all_lines(self):
        """返回全部历史日志"""
        with self._lock:
            return list(self._lines)

    def lines_from(self, start_index):
        """返回 start_index 之后的增量日志与当前累计行数

        序号语义：每 append 一行累计计数加一。缓冲区满淘汰旧行不影响序号，
        因此即使总行数不再增长，调用方仍能凭序号拿到新日志。
        """
        with self._lock:
            lines = list(self._lines)
            total = self._count
        # 当前缓冲里第一行对应的序号
        earliest = total - len(lines)
        # 若客户端序号落后于被淘汰的行，回退到最早可用位置（全量重发）
        if start_index < earliest:
            start_index = earliest
        # 若客户端序号超前于 total（服务重启清空缓冲区后旧连接），同样回退全量重发
        if start_index > total:
            start_index = earliest
        # 在 lines 中的偏移 = start_index 与 earliest 的差值
        offset = start_index - earliest
        return lines[offset:], total


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


async def event_stream(name):
    """SSE 异步生成器：先推全部历史日志，之后每 0.5 秒推送增量

    每次迭代产出一条 SSE 格式消息（data: 内容\n\n）。
    无新日志时发送注释心跳行，保持连接不断。
    """
    if name not in SERVICE_COMMANDS:
        # 与 start/stop 保持一致的异常类型，方便前端统一捕获
        raise ValueError(f"未知服务: {name}")

    buf = _ensure_buffer(name)
    total = 0  # 记录已推送到的总行数
    while True:
        new_lines, total = buf.lines_from(total)
        if new_lines:
            for line in new_lines:
                yield f"data: {line}\n\n"
        else:
            # SSE 心跳：空注释行，避免连接被中间设备超时断开
            yield ": keep-alive\n\n"
        # 让出事件循环，避免阻塞其他请求；0.5 秒对本地单用户足够实时
        await asyncio.sleep(0.5)


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
        # Windows 下子进程 stdout 走管道时默认用 GBK 编码，强制 utf-8 避免中文乱码
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
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


# FastAPI 相关导入放在中部：让文件顶部先展示纯进程管理逻辑，便于初学者逐段理解
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse

# 管理页面 HTML：内嵌 CSS 与 JS，不依赖任何外部库/网络
HTML_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AgentWeb 服务管理器</title>
<style>
  body { font-family: "Microsoft YaHei", sans-serif; background: #f5f6fa; margin: 0; padding: 20px; }
  h1 { font-size: 20px; color: #333; }
  .cards { display: flex; gap: 16px; flex-wrap: wrap; }
  .card { background: #fff; border-radius: 8px; padding: 16px 20px; box-shadow: 0 1px 4px rgba(0,0,0,.1); flex: 1; min-width: 260px; }
  .card h2 { font-size: 16px; margin: 0 0 10px; display: flex; align-items: center; gap: 8px; }
  .badge { display: inline-block; font-size: 12px; padding: 2px 10px; border-radius: 999px; }
  .badge.running { background: #e6f7e6; color: #2e7d32; }
  .badge.stopped { background: #fdecea; color: #c62828; }
  .meta { color: #666; font-size: 13px; margin: 6px 0; }
  button { padding: 6px 16px; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; margin-right: 8px; }
  button:disabled { opacity: .4; cursor: not-allowed; }
  .btn-start { background: #2e7d32; color: #fff; }
  .btn-stop { background: #c62828; color: #fff; }
  .btn-restart { background: #1976d2; color: #fff; }
  .logs { display: flex; gap: 16px; margin-top: 20px; flex-wrap: wrap; }
  .log-panel { flex: 1; min-width: 320px; background: #1e1e2e; color: #d4d4d4; border-radius: 8px; overflow: hidden; }
  .log-panel header { padding: 8px 12px; background: #2a2a3c; font-size: 13px; display: flex; justify-content: space-between; align-items: center; }
  .log-panel pre { margin: 0; padding: 10px 12px; height: 320px; overflow-y: auto; font-size: 12px; line-height: 1.5; white-space: pre-wrap; word-break: break-all; }
  .toolbar { margin-top: 10px; font-size: 13px; display: flex; gap: 16px; align-items: center; color: #555; }
  #toast { position: fixed; top: 16px; left: 50%; transform: translateX(-50%); background: #333; color: #fff; padding: 8px 18px; border-radius: 4px; display: none; z-index: 99; }
  #toast.show { display: block; }
  .clear-btn { font-size: 12px; padding: 2px 10px; background: #444; color: #ddd; border: none; border-radius: 3px; cursor: pointer; }
</style>
</head>
<body>
<div id="toast"></div>
<h1>AgentWeb 服务管理器</h1>

<div class="cards">
  <div class="card" id="card-backend">
    <h2>后端 <span class="badge" id="badge-backend">—</span></h2>
    <div class="meta" id="meta-backend">未启动</div>
    <div>
      <button class="btn-start" data-name="backend" data-action="start">启动</button>
      <button class="btn-stop" data-name="backend" data-action="stop">停止</button>
      <button class="btn-restart" data-name="backend" data-action="restart">重启</button>
    </div>
  </div>
  <div class="card" id="card-frontend">
    <h2>前端 <span class="badge" id="badge-frontend">—</span></h2>
    <div class="meta" id="meta-frontend">未启动</div>
    <div>
      <button class="btn-start" data-name="frontend" data-action="start">启动</button>
      <button class="btn-stop" data-name="frontend" data-action="stop">停止</button>
      <button class="btn-restart" data-name="frontend" data-action="restart">重启</button>
    </div>
  </div>
</div>

<div class="logs">
  <div class="log-panel">
    <header>后端日志 <button class="clear-btn" data-name="backend">清空显示</button></header>
    <pre id="log-backend"></pre>
  </div>
  <div class="log-panel">
    <header>前端日志 <button class="clear-btn" data-name="frontend">清空显示</button></header>
    <pre id="log-frontend"></pre>
  </div>
</div>

<div class="toolbar">
  <label><input type="checkbox" id="autoscroll" checked> 自动滚动到底部</label>
  <span>状态每 2 秒自动刷新</span>
</div>

<script>
const SERVICES = ["backend", "frontend"];

// 顶部提示条：短暂显示操作结果
function toast(msg, isError) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.style.background = isError ? "#b71c1c" : "#333";
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 2500);
}

// 每 2 秒轮询状态接口，刷新徽章、PID 与按钮可用性
async function refreshStatus() {
  try {
    const resp = await fetch("/api/status");
    const data = await resp.json();
    for (const name of SERVICES) {
      const s = data[name];
      const badge = document.getElementById("badge-" + name);
      const meta = document.getElementById("meta-" + name);
      if (s.running) {
        badge.textContent = "● 运行中";
        badge.className = "badge running";
        meta.textContent = "PID: " + s.pid + " · 已运行 " + s.elapsed + " 秒";
      } else {
        badge.textContent = "○ 已停止";
        badge.className = "badge stopped";
        meta.textContent = "未启动";
      }
      // 按钮状态：运行中禁用"启动"，停止时禁用"停止/重启"
      document.querySelectorAll('#card-' + name + ' button').forEach(btn => {
        const act = btn.dataset.action;
        btn.disabled = (s.running && act === "start") || (!s.running && act !== "start");
      });
    }
  } catch (e) {
    toast("状态刷新失败: " + e, true);
  }
}

// 点击按钮 → POST 操作接口 → 提示结果并立即刷新状态
document.querySelectorAll("button[data-action]").forEach(btn => {
  btn.addEventListener("click", async () => {
    const name = btn.dataset.name, action = btn.dataset.action;
    btn.disabled = true;
    try {
      const resp = await fetch("/api/" + action + "/" + name, { method: "POST" });
      const body = await resp.json();
      toast(body.message || body.detail || (body.ok ? "操作成功" : "操作失败"), !body.ok);
    } catch (e) {
      toast("请求失败: " + e, true);
    }
    refreshStatus();
  });
});

// 清空显示：只清浏览器面板，不影响服务与缓冲区
document.querySelectorAll(".clear-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.getElementById("log-" + btn.dataset.name).textContent = "";
  });
});

// SSE 日志流：监听后端/前端日志，断线后自动重连
function connectLog(name) {
  const pre = document.getElementById("log-" + name);
  const evtSource = new EventSource("/api/logs/" + name);
  evtSource.onmessage = (e) => {
    pre.textContent += e.data + "\\n";
    if (document.getElementById("autoscroll").checked) pre.scrollTop = pre.scrollHeight;
  };
  evtSource.onerror = () => {
    // 连接断开（如服务重启），1.5 秒后重连
    evtSource.close();
    setTimeout(() => connectLog(name), 1500);
  };
}

SERVICES.forEach(name => connectLog(name));
refreshStatus();
setInterval(refreshStatus, 2000);
</script>
</body>
</html>
"""

app = FastAPI(title="AgentWeb 服务管理器")


@app.get("/", response_class=HTMLResponse)
async def index():
    """首页：返回内嵌的管理页面"""
    return HTML_PAGE


@app.get("/api/status")
async def api_status():
    """查询前后端运行状态"""
    return {name: get_status(name) for name in SERVICE_COMMANDS}


@app.post("/api/{action}/{name}")
def api_control(action: str, name: str):
    """启停/重启接口：action 为 start|stop|restart

    用普通 def 而非 async def：stop/restart 内含 taskkill 子进程与
    time.sleep 等阻塞调用，async 端点会把事件循环卡住，使 SSE 心跳与
    状态轮询短暂冻结；普通 def 由 FastAPI 放入线程池执行，互不干扰。
    """
    if name not in SERVICE_COMMANDS:
        raise HTTPException(status_code=404, detail=f"未知服务: {name}")
    if action == "start":
        return start(name)
    if action == "stop":
        return stop(name)
    if action == "restart":
        return restart(name)
    raise HTTPException(status_code=400, detail=f"未知操作: {action}")


@app.get("/api/logs/{name}")
async def api_logs(name: str):
    """SSE 实时日志流"""
    if name not in SERVICE_COMMANDS:
        raise HTTPException(status_code=404, detail=f"未知服务: {name}")
    return StreamingResponse(
        event_stream(name),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


def main():
    """启动管理服务并自动打开浏览器"""
    port = 8001
    url = f"http://127.0.0.1:{port}"
    # 1 秒后自动打开浏览器（等服务真正监听）
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"服务管理器已启动: {url}  (按 Ctrl+C 退出)")
    # 借用项目后端同款启动方式：uvicorn 运行 app
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
