"""Local MiniMax proxy. The API key is read only from MINIMAX_API_KEY."""
import json, os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

def minimax_key():
    key = os.environ.get("MINIMAX_API_KEY")
    if key or os.name != "nt":
        return key
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as env:
            return winreg.QueryValueEx(env, "MINIMAX_API_KEY")[0]
    except OSError:
        return None

class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        super().end_headers()
    def do_OPTIONS(self): self.send_response(204); self.end_headers()
    def do_POST(self):
        if self.path != "/api/tts": return self.send_error(404)
        key = minimax_key()
        if not key: return self.reply(503, {"error": "MINIMAX_API_KEY is not set in this local environment."})
        try:
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            if not str(data.get("text", "")).strip(): raise ValueError("text is required")
            request = Request("https://api.minimaxi.com/v1/t2a_v2", data=json.dumps(data).encode(), headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, method="POST")
            with urlopen(request, timeout=90) as response: self.reply(response.status, json.loads(response.read()))
        except HTTPError as error: self.reply(error.code, json.loads(error.read() or b"{}"))
        except Exception as error: self.reply(400, {"error": str(error)})
    def reply(self, status, value):
        body = json.dumps(value, ensure_ascii=False).encode(); self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

if __name__ == "__main__":
    print("JP-merge 配音工具本地服务: http://127.0.0.1:8788")
    ThreadingHTTPServer(("127.0.0.1", 8788), Handler).serve_forever()
