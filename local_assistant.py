"""Local-only document assistant for JP-merge Voice Tool.

It reads DingTalk credentials from .env and only listens on 127.0.0.1.
No DingTalk credential or document content is sent to GitHub Pages or Cloudflare.
"""

from __future__ import annotations

import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, quote, urlencode, urlparse
from urllib.request import Request, urlopen


HOST = "127.0.0.1"
PORT = 8789
ROOT = Path(__file__).resolve().parent
FALLBACK_ENV = Path(r"D:\story-translation-automation\.env")
ALLOWED_ORIGINS = {"https://crazyfaraday.github.io", "http://127.0.0.1:4173", "http://localhost:4173"}


def load_env() -> dict[str, str]:
    """Read a simple .env file while allowing real environment variables to win."""
    values: dict[str, str] = {}
    configured = os.environ.get("JP_MERGE_ENV_FILE", "").strip()
    candidates = [Path(configured)] if configured else [ROOT / ".env", FALLBACK_ENV]
    for path in candidates:
        if not path.is_file():
            continue
        for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
        break
    values.update({key: value for key, value in os.environ.items() if value})
    return values


def config() -> dict[str, str]:
    values = load_env()
    return {
        "app_key": values.get("DINGTALK_APP_KEY", "").strip(),
        "app_secret": values.get("DINGTALK_APP_SECRET", "").strip(),
        "operator_id": (values.get("DINGTALK_OPERATOR_UNION_ID") or values.get("DINGTALK_OPERATOR_ID") or "").strip(),
    }


def request_json(url: str, *, method: str = "GET", headers: dict[str, str] | None = None, payload: dict | None = None) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = Request(url, data=body, method=method, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read()
            return json.loads(raw or b"{}")
    except HTTPError as error:
        raw = error.read()
        try:
            detail = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            detail = {}
        message = detail.get("message") or detail.get("errmsg") or detail.get("errorMessage") or f"钉钉接口返回 HTTP {error.code}"
        raise ValueError(message) from error


def access_token(settings: dict[str, str]) -> str:
    if not settings["app_key"] or not settings["app_secret"]:
        raise ValueError("缺少 DINGTALK_APP_KEY 或 DINGTALK_APP_SECRET")
    result = request_json(
        "https://api.dingtalk.com/v1.0/oauth2/accessToken",
        method="POST",
        payload={"appKey": settings["app_key"], "appSecret": settings["app_secret"]},
    )
    token = result.get("accessToken")
    if not token:
        raise ValueError(result.get("message") or "获取钉钉临时访问令牌失败")
    return str(token)


def parse_workbook_id(value: str) -> str:
    raw = value.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", raw):
        return raw
    parsed = urlparse(raw)
    query = parse_qs(parsed.query)
    for key in ("workbookId", "workbook_id", "nodeId", "node_id", "docId", "doc_id"):
        if query.get(key, [""])[0]:
            return query[key][0]
    match = re.search(r"/(?:workbooks|nodes|spreadsheets)/([A-Za-z0-9_-]{10,})", parsed.path, re.IGNORECASE)
    if match:
        return match.group(1)
    raise ValueError("无法从链接解析 Workbook ID，请直接粘贴 Workbook ID")


def dingtalk_get(path: str, settings: dict[str, str], params: dict[str, str] | None = None) -> dict:
    if not settings["operator_id"]:
        raise ValueError("缺少 DINGTALK_OPERATOR_UNION_ID（或 DINGTALK_OPERATOR_ID）")
    token = access_token(settings)
    suffix = f"?{urlencode(params or {})}" if params else ""
    return request_json(
        f"https://api.dingtalk.com{path}{suffix}",
        headers={"x-acs-dingtalk-access-token": token},
    )


def find_list(value: object, keys: tuple[str, ...]) -> list:
    if isinstance(value, dict):
        for key in keys:
            if isinstance(value.get(key), list):
                return value[key]
        for child in value.values():
            found = find_list(child, keys)
            if found:
                return found
    return []


def list_sheets(workbook_id: str, settings: dict[str, str]) -> list[dict[str, str]]:
    result = dingtalk_get(
        f"/v1.0/doc/workbooks/{quote(workbook_id, safe='')}/sheets",
        settings,
        {"operatorId": settings["operator_id"]},
    )
    sheets: list[dict[str, str]] = []
    for item in find_list(result, ("sheets", "items", "list")):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("title") or item.get("sheetName") or item.get("id") or "").strip()
        if name:
            sheets.append({"name": name})
    if not sheets:
        raise ValueError("未读取到工作表；请确认应用拥有文档读取权限，且操作人有该表格权限")
    return sheets


def find_values(value: object) -> list[list[object]]:
    if isinstance(value, dict):
        candidate = value.get("values")
        if isinstance(candidate, list):
            return candidate
        for child in value.values():
            found = find_values(child)
            if found:
                return found
    return []


def excel_column(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def unique_headers(row: list[object], width: int) -> list[str]:
    seen: dict[str, int] = {}
    headers: list[str] = []
    for index in range(width):
        raw = str(row[index] if index < len(row) else "").strip()
        base = raw or f"列{excel_column(index + 1)}"
        seen[base] = seen.get(base, 0) + 1
        headers.append(base if seen[base] == 1 else f"{base}_{seen[base]}")
    return headers


def read_range(workbook_id: str, sheet: str, header_row: int, start_row: int, end_row: int, settings: dict[str, str]) -> dict:
    if header_row < 1 or start_row < 1 or end_row < start_row:
        raise ValueError("表头行、起始行与结束行必须是有效的行号")
    if end_row - header_row > 1000:
        raise ValueError("单次最多读取 1000 行，请缩小行范围")
    range_address = f"A{header_row}:ZZ{end_row}"
    path = f"/v1.0/doc/workbooks/{quote(workbook_id, safe='')}/sheets/{quote(sheet, safe='')}/ranges/{quote(range_address, safe='')}"
    result = dingtalk_get(path, settings, {"select": "values", "operatorId": settings["operator_id"]})
    values = find_values(result)
    if not values:
        return {"headers": [], "records": []}
    width = max((len(row) for row in values if isinstance(row, list)), default=0)
    if not width:
        return {"headers": [], "records": []}
    headers = unique_headers(values[0] if isinstance(values[0], list) else [], width)
    offset = max(start_row - header_row, 1)
    records: list[dict[str, str]] = []
    for row in values[offset:]:
        if not isinstance(row, list):
            continue
        record = {headers[index]: str(row[index]).strip() if index < len(row) and row[index] is not None else "" for index in range(width)}
        if any(record.values()):
            records.append(record)
    return {"headers": headers, "records": records}


class Handler(BaseHTTPRequestHandler):
    server_version = "JPMergeLocalAssistant/1.0"

    def log_message(self, format: str, *args: object) -> None:
        print(f"[本机文档助手] {format % args}")

    def end_headers(self) -> None:
        origin = self.headers.get("Origin", "")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def reply(self, status: int, value: dict) -> None:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 100_000:
            raise ValueError("请求内容过大")
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError as error:
            raise ValueError("请求格式无效") from error

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def do_GET(self) -> None:
        if self.path != "/health":
            self.reply(404, {"error": "Not found"})
            return
        settings = config()
        self.reply(200, {"ok": True, "configured": bool(settings["app_key"] and settings["app_secret"] and settings["operator_id"]), "operatorConfigured": bool(settings["operator_id"])})

    def do_POST(self) -> None:
        try:
            body = self.read_body()
            settings = config()
            if self.path == "/dingtalk/sheets":
                workbook_id = parse_workbook_id(str(body.get("workbook", "")))
                self.reply(200, {"workbookId": workbook_id, "sheets": list_sheets(workbook_id, settings)})
                return
            if self.path == "/dingtalk/read":
                workbook_id = parse_workbook_id(str(body.get("workbook", "")))
                sheet = str(body.get("sheet", "")).strip()
                if not sheet:
                    raise ValueError("请先选择工作表")
                data = read_range(workbook_id, sheet, int(body.get("headerRow", 1)), int(body.get("startRow", 2)), int(body.get("endRow", 100)), settings)
                self.reply(200, {"workbookId": workbook_id, **data})
                return
            self.reply(404, {"error": "Not found"})
        except (TypeError, ValueError) as error:
            self.reply(400, {"error": str(error)})
        except Exception as error:
            print(f"[本机文档助手] 未处理错误：{error}")
            self.reply(502, {"error": "读取钉钉文档失败，请检查本机助手窗口中的错误信息"})


if __name__ == "__main__":
    print(f"JP-merge 本机文档助手已启动：http://{HOST}:{PORT}")
    print("仅允许本机访问。关闭此窗口即可停止服务。")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
