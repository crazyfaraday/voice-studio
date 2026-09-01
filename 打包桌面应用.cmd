@echo off
cd /d "%~dp0"
py -3 -m pip install pyinstaller
if errorlevel 1 (
  echo PyInstaller 安装失败，请检查网络后重试。
  pause
  exit /b 1
)
py -3 -m PyInstaller --noconfirm --clean --windowed --onedir --name JPMergeVoiceTool --add-data "index.html;." --add-data "app.js;." --add-data "styles.css;." --add-data "requirements-local-assistant.txt;." desktop_app.py
if errorlevel 1 pause
