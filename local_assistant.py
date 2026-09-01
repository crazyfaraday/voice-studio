"""Local-only document assistant for JP-merge Voice Tool.

It reads DingTalk credentials from .env and only listens on 127.0.0.1.
No DingTalk credential or document content is sent to GitHub Pages or Cloudflare.
"""

from __future__ import annotations

import base64
import binascii
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
ROOT = Path(os.environ.get("JP_MERGE_APP_ROOT", Path(__file__).resolve().parent))
OUTPUT_DIR = ROOT / "配音输出"
FALLBACK_ENV = Path(r"D:\story-translation-automation\.env")
ALLOWED_ORIGINS = {"https://crazyfaraday.github.io", "http://127.0.0.1:4173", "http://localhost:4173", "http://127.0.0.1:8790", "http://localhost:8790"}


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


def google_credentials_path() -> Path:
    configured = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    return Path(configured) if configured else ROOT / "credentials" / "google-service-account.json"


def google_access_token() -> str:
    path = google_credentials_path()
    if not path.is_file():
        raise ValueError("未找到 credentials/google-service-account.json")
    try:
        from google.auth.transport.requests import Request as GoogleRequest
        from google.oauth2.service_account import Credentials
    except ModuleNotFoundError as error:
        raise ValueError("缺少 Google 认证组件；请重新运行 启动本机助手.cmd") from error
    credentials = Credentials.from_service_account_file(str(path), scopes=["https://www.googleapis.com/auth/spreadsheets"])
    credentials.refresh(GoogleRequest())
    if not credentials.token:
        raise ValueError("获取 Google 服务账号访问令牌失败")
    return str(credentials.token)


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
        nested_error = detail.get("error") if isinstance(detail.get("error"), dict) else {}
        message = detail.get("message") or detail.get("errmsg") or detail.get("errorMessage") or nested_error.get("message") or f"接口返回 HTTP {error.code}"
        raise ValueError(f"HTTP {error.code}：{message}") from error


def safe_error_message(error: Exception) -> str:
    """Return enough diagnostic detail without ever exposing credential content."""
    message = str(error).replace("\r", " ").replace("\n", " ").strip()
    for marker in ("private_key", "client_secret", "access_token", "Authorization"):
        if marker.lower() in message.lower():
            return "认证配置发生错误（敏感内容已隐藏）"
    return message[:700] or error.__class__.__name__


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


def parse_google_spreadsheet_id(value: str) -> str:
    raw = value.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{20,}", raw):
        return raw
    parsed = urlparse(raw)
    match = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]{20,})", parsed.path)
    if match:
        return match.group(1)
    spreadsheet_id = parse_qs(parsed.query).get("id", [""])[0]
    if re.fullmatch(r"[A-Za-z0-9_-]{20,}", spreadsheet_id):
        return spreadsheet_id
    raise ValueError("无法从链接解析 Spreadsheet ID，请直接粘贴 Spreadsheet ID")


def google_request(url: str, *, method: str = "GET", payload: dict | None = None) -> dict:
    return request_json(url, method=method, headers={"Authorization": f"Bearer {google_access_token()}"}, payload=payload)


def google_list_sheets(spreadsheet_id: str) -> list[dict[str, str]]:
    result = google_request(f"https://sheets.googleapis.com/v4/spreadsheets/{quote(spreadsheet_id, safe='')}?fields=sheets.properties(sheetId,title)")
    sheets = [{"name": str(item.get("properties", {}).get("title", "")).strip()} for item in result.get("sheets", []) if isinstance(item, dict)]
    sheets = [item for item in sheets if item["name"]]
    if not sheets:
        raise ValueError("未读取到工作表；请确认已将表格共享给服务账号，且已启用 Google Sheets API")
    return sheets


def google_read_range(spreadsheet_id: str, sheet: str, header_row: int, start_row: int, end_row: int) -> dict:
    if header_row < 1 or start_row < 1 or end_row < start_row:
        raise ValueError("表头行、起始行与结束行必须是有效的行号")
    if end_row - header_row > 1000:
        raise ValueError("单次最多读取 1000 行，请缩小行范围")
    range_address = f"'{sheet}'!A{header_row}:ZZ{end_row}"
    result = google_request(f"https://sheets.googleapis.com/v4/spreadsheets/{quote(spreadsheet_id, safe='')}/values/{quote(range_address, safe='')}")
    values = result.get("values", [])
    if not isinstance(values, list) or not values:
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


def google_write_range(spreadsheet_id: str, sheet: str, start_cell: str, values: object) -> dict:
    if not re.fullmatch(r"[A-Z]{1,3}[1-9]\d*", start_cell):
        raise ValueError("起始单元格格式应如 A1")
    if not isinstance(values, list) or not values or any(not isinstance(row, list) for row in values):
        raise ValueError("写入内容格式无效")
    if len(values) > 2000:
        raise ValueError("单次最多写入 2000 行")
    range_address = f"'{sheet}'!{start_cell}"
    return google_request(
        f"https://sheets.googleapis.com/v4/spreadsheets/{quote(spreadsheet_id, safe='')}/values/{quote(range_address, safe='')}?valueInputOption=USER_ENTERED",
        method="PUT",
        payload={"range": range_address, "majorDimension": "ROWS", "values": values},
    )


def google_health() -> dict:
    path = google_credentials_path()
    if not path.is_file():
        return {"ok": True, "configured": False, "error": "未找到 credentials/google-service-account.json"}
    try:
        from google.oauth2.service_account import Credentials  # noqa: F401
    except ModuleNotFoundError:
        return {"ok": True, "configured": False, "error": "缺少 Google 认证组件；请重新运行 启动本机助手.cmd"}
    return {"ok": True, "configured": True}


def save_audio_file(filename: str, encoded_audio: object) -> dict[str, str]:
    """Store a generated audio file beside the desktop app, never outside it."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\.(mp3|wav|flac|opus)", filename, re.IGNORECASE):
        raise ValueError("输出文件名无效")
    if not isinstance(encoded_audio, str) or not encoded_audio:
        raise ValueError("未收到音频内容")
    try:
        audio = base64.b64decode(encoded_audio, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("音频内容格式无效") from error
    if not audio or len(audio) > 30 * 1024 * 1024:
        raise ValueError("音频文件为空或超过 30 MB")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    target = OUTPUT_DIR / filename
    target.write_bytes(audio)
    return {"filename": filename, "folder": str(OUTPUT_DIR), "path": str(target)}


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

    def read_body(self, max_bytes: int = 100_000) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > max_bytes:
            raise ValueError("请求内容过大")
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError as error:
            raise ValueError("请求格式无效") from error

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/health":
            settings = config()
            self.reply(200, {"ok": True, "configured": bool(settings["app_key"] and settings["app_secret"] and settings["operator_id"]), "operatorConfigured": bool(settings["operator_id"])})
            return
        if self.path == "/google/health":
            self.reply(200, google_health())
            return
        self.reply(404, {"error": "Not found"})

    def do_POST(self) -> None:
        try:
            body = self.read_body(42 * 1024 * 1024 if self.path == "/audio/save" else 100_000)
            settings = config()
            if self.path == "/audio/save":
                self.reply(200, save_audio_file(str(body.get("filename", "")), body.get("audioBase64")))
                return
            if self.path == "/audio/open-folder":
                OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                if not hasattr(os, "startfile"):
                    raise ValueError("当前系统无法自动打开输出文件夹")
                os.startfile(str(OUTPUT_DIR))
                self.reply(200, {"folder": str(OUTPUT_DIR)})
                return
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
            if self.path == "/google/sheets":
                spreadsheet_id = parse_google_spreadsheet_id(str(body.get("spreadsheet", "")))
                self.reply(200, {"spreadsheetId": spreadsheet_id, "sheets": google_list_sheets(spreadsheet_id)})
                return
            if self.path == "/google/read":
                spreadsheet_id = parse_google_spreadsheet_id(str(body.get("spreadsheet", "")))
                sheet = str(body.get("sheet", "")).strip()
                if not sheet:
                    raise ValueError("请先选择工作表")
                data = google_read_range(spreadsheet_id, sheet, int(body.get("headerRow", 1)), int(body.get("startRow", 2)), int(body.get("endRow", 100)))
                self.reply(200, {"spreadsheetId": spreadsheet_id, **data})
                return
            if self.path == "/google/write":
                spreadsheet_id = parse_google_spreadsheet_id(str(body.get("spreadsheet", "")))
                sheet = str(body.get("sheet", "")).strip()
                if not sheet:
                    raise ValueError("请先选择工作表")
                result = google_write_range(spreadsheet_id, sheet, str(body.get("startCell", "")).strip().upper(), body.get("values"))
                self.reply(200, {"updatedRange": result.get("updatedRange", ""), "updatedCells": result.get("updatedCells", 0)})
                return
            self.reply(404, {"error": "Not found"})
        except (TypeError, ValueError) as error:
            self.reply(400, {"error": str(error)})
        except Exception as error:
            print(f"[本机文档助手] 未处理错误：{error}")
            source = "Google 表格" if self.path.startswith("/google/") else "钉钉文档"
            detail = safe_error_message(error)
            self.reply(502, {"error": f"读取{source}失败：{detail}", "diagnostic": f"步骤：{self.path}；异常：{error.__class__.__name__}"})


if __name__ == "__main__":
    print(f"JP-merge 本机文档助手已启动：http://{HOST}:{PORT}")
    print("仅允许本机访问。关闭此窗口即可停止服务。")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
