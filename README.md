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

## Google 表格导入与写入

将服务账号凭据保存到 `credentials/google-service-account.json`（该目录下的 JSON 已被 Git 忽略，绝不会提交）。在 Google 表格的“共享”中，把表格分享给该服务账号的邮箱，并赋予“查看者”权限以导入、“编辑者”权限以写入。

启动本机助手时会自动安装 `google-auth` 组件。网页可读取指定工作表的表头、行范围和所选列；“写入 Google 表格”会把当前配音文本写进指定 Sheet 和起始单元格。写入前会出现最后一次确认，目标范围的内容会被覆盖。

## 发布

本项目将独立连接一个 Cloudflare Worker，不与 ItemTools 共用网址、密钥或发布流程。

## Windows 桌面应用

双击 `启动桌面应用.cmd` 即可打开桌面版。它会自动启动本机文档助手，并在应用关闭时一并停止，因此不再需要单独运行“启动本机助手”。

要制作可分发版本，运行 `打包桌面应用.cmd`。生成结果位于 `dist/JPMergeVoiceTool/`；将 `.env` 与 `credentials/google-service-account.json` 放在该目录下即可让成品继续读取钉钉与 Google 表格。密钥文件不会被打包或提交到 Git。
