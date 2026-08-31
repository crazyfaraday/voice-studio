# JP-merge配音工具

MiniMax 配音工具的独立前端工作区。

页面支持在线文本编辑、单条覆盖音色/语速/音调/音量、Excel 导入导出、单条试听和批量生成。

## 本地密钥与测试

密钥仅从本机的 `MINIMAX_API_KEY` 环境变量读取，绝不能写进网页或提交到 Git。在 Windows PowerShell 执行 `setx MINIMAX_API_KEY "你的密钥"` 后，运行 `python dev_server.py`，再打开 `http://127.0.0.1:8788`。本地代理会读取当前环境或你的 Windows 用户环境变量。

GitHub Pages 只承载前端。公网生成接口需要独立的 Cloudflare Worker，并将同名变量保存为 Worker Secret。

## 发布

本项目将独立连接一个 Cloudflare Worker，不与 ItemTools 共用网址、密钥或发布流程。
