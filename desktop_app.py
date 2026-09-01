"""JP-merge Voice Tool desktop application.

The app hosts the existing web UI locally and starts the document assistant
automatically. Credentials remain next to the app on the user's computer.
"""

from __future__ import annotations

import os
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


APP_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", APP_ROOT))
os.environ.setdefault("JP_MERGE_APP_ROOT", str(APP_ROOT))

import local_assistant


HOST = "127.0.0.1"
DOCUMENT_PORT = 8789
WEB_PORT = 8790


class StaticHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BUNDLE_ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format, *args):
        return


def serve(server: ThreadingHTTPServer) -> None:
    server.serve_forever()


def start_server(port: int, handler) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((HOST, port), handler)
    threading.Thread(target=serve, args=(server,), daemon=True).start()
    return server


def main() -> None:
    try:
        import webview
    except ModuleNotFoundError:
        raise SystemExit("缺少桌面应用组件。请运行 启动桌面应用.cmd。")

    try:
        document_server = start_server(DOCUMENT_PORT, local_assistant.Handler)
    except OSError as error:
        raise SystemExit(f"无法启动本机文档助手（端口 {DOCUMENT_PORT}）：{error}") from error
    try:
        web_server = start_server(WEB_PORT, StaticHandler)
    except OSError as error:
        document_server.shutdown()
        raise SystemExit(f"无法启动桌面页面（端口 {WEB_PORT}）：{error}") from error

    try:
        window = webview.create_window("JP-merge 配音工具", f"http://{HOST}:{WEB_PORT}", width=1440, height=940, min_size=(1024, 720))
        webview.start(debug=False)
    finally:
        web_server.shutdown()
        document_server.shutdown()


if __name__ == "__main__":
    main()
