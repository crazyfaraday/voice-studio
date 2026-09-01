@echo off
cd /d "%~dp0"
py -3 local_assistant.py
if errorlevel 1 (
  echo.
  echo 启动失败：请确认已安装 Python 3，然后按任意键关闭。
  pause
)
