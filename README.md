# JP-merge配音工具

MiniMax 配音工具的独立前端工作区。

页面支持在线文本编辑、单条覆盖音色/语速/音调/音量、Excel 导入导出、单条试听和批量生成。

## 本地密钥与测试

密钥仅从本机的 `MINIMAX_API_KEY` 环境变量读取，绝不能写进网页或提交到 Git。在 Windows PowerShell 执行 `setx MINIMAX_API_KEY "你的密钥"` 后，运行 `python dev_server.py`，再打开 `http://127.0.0.1:8788`。本地代理会读取当前环境或你的 Windows 用户环境变量。

GitHub Pages 只承载前端。公网生成接口需要独立的 Cloudflare Worker，并将同名变量保存为 Worker Secret。

## 钉钉表格导入（本机文档助手）

钉钉凭据和文档内容只在本机处理，不会发送到 GitHub Pages 或 Cloudflare。将以下值写入本项目的 `.env`（可参考 `.env.example`）：

```text
DINGTALK_APP_KEY=...
DINGTALK_APP_SECRET=...
DINGTALK_OPERATOR_UNION_ID=...
```

双击 `启动本机助手.cmd`，保持弹出的窗口运行；随后在网页点击“导入钉钉文档”。粘贴钉钉表格链接（或 Workbook ID），依次选择工作表、表头行与数据起止行，预览后勾选要导入的列。

本机助手只监听 `127.0.0.1:8789`，其他设备无法访问。若你的现有钉钉配置仍放在 `D:\story-translation-automation\.env`，助手也会读取它；建议逐步迁移到本项目的 `.env`。

## 发布

本项目将独立连接一个 Cloudflare Worker，不与 ItemTools 共用网址、密钥或发布流程。
