"""Hello —— 示例服务 App。

运行即在中枢进程内开一个可访问的 HTTP 端口（127.0.0.1:8787），
模拟「实际服务在后台跑」的测试场景。

- 界面（ui/index.html）显示服务状态与访问地址
- 生命周期由中枢「后台」面板统一管理（App 实例的创建/终止）
- 不提供停止按钮——App 实例被终止时服务线程自动回收
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "127.0.0.1"
PORT = 8787
NAME = "Hello"

# ---------- 服务状态（模块级单例，进程内共享） ----------
_server: "ThreadingHTTPServer | None" = None
_thread: "threading.Thread | None" = None


def is_running() -> bool:
    return _server is not None and _thread is not None and _thread.is_alive()


def status() -> dict:
    return {
        "running": is_running(),
        "host": HOST,
        "port": PORT,
        "url": f"http://{HOST}:{PORT}/",
    }


PAGE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><title>Hello</title>
<style>
  :root { color-scheme: light dark; }
  body { margin: 0; padding: 20px; font-family: system-ui, "Microsoft YaHei", sans-serif;
         background: #f5f7fb; color: #1f2937; }
  .card { max-width: 520px; margin: 0 auto; background: #fff; border-radius: 14px;
          padding: 20px 22px; box-shadow: 0 2px 12px rgba(15,23,42,.08); }
  h1 { font-size: 18px; margin: 0 0 4px; }
  .desc { color: #6b7280; font-size: 13px; margin-bottom: 16px; }
  .row { display: flex; justify-content: space-between; padding: 8px 0;
         border-bottom: 1px solid #eef1f6; font-size: 13px; }
  .row:last-of-type { border-bottom: 0; }
  .k { color: #6b7280; }
  .v { font-weight: 600; }
  a { color: #3b82f6; }
  .hint { margin-top: 14px; font-size: 12px; color: #9aa4b2; line-height: 1.7; }
</style></head>
<body>
  <div class="card">
    <h1>Hello 服务</h1>
    <div class="desc">这是一个示例服务 App，验证「App 在后台开端口」的运行模式。</div>
    <div class="row"><span class="k">服务名</span><span class="v">Hello</span></div>
    <div class="row"><span class="k">版本</span><span class="v">1.0.0</span></div>
    <div class="row"><span class="k">监听</span><span class="v">127.0.0.1:8787</span></div>
    <div class="row"><span class="k">健康检查</span><span class="v"><a href="/health">/health</a></span></div>
    <div class="hint">
      这个 HTTP 服务跑在中枢进程内（后台线程），不依赖外部进程。<br>
      生命周期由中枢「后台」面板统一管理。
    </div>
  </div>
</body></html>
"""


class Handler(BaseHTTPRequestHandler):

    def _send(self, code: int, body, ctype: str = "text/html; charset=utf-8") -> None:
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE)
        elif self.path == "/health":
            self._send(200, json.dumps({"ok": True, "service": NAME}),
                       "application/json; charset=utf-8")
        else:
            self._send(404, "<h1>404</h1>")

    def log_message(self, *args):  # 静音访问日志
        pass


def _start_server():
    """启动 HTTP 服务（后台线程）。已在跑则直接返回成功。"""
    global _server, _thread
    if is_running():
        return
    try:
        _server = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError:
        _server = None
        raise

    _thread = threading.Thread(target=_server.serve_forever, daemon=True)
    _thread.start()


def stop_server():
    """停止 HTTP 服务（App 实例终止时由框架回收，或主动调用）。"""
    global _server, _thread
    if _server:
        try:
            _server.shutdown()
            _server.server_close()
        except Exception:
            pass
    _server = None
    _thread = None


def teardown() -> dict:
    """生命周期钩子：实例终止时由框架调用，回收后台 HTTP 端口。"""
    was_running = is_running()
    stop_server()
    return {"ok": True, "teardown": "hello", "was_running": was_running}


def run(params: dict) -> dict:
    """App 逻辑入口：启动服务并返回状态。"""
    try:
        _start_server()
    except OSError as e:
        return {"ok": False, "error": f"端口 {PORT} 被占用: {e}"}
    return {"ok": True, "service": NAME, **status()}


if __name__ == "__main__":
    print(json.dumps(run({}), ensure_ascii=False))
