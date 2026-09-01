@echo off
cd /d "%~dp0"
py -3 -c "import google.oauth2.service_account" >nul 2>nul
if errorlevel 1 (
  echo 正在安装 Google 表格本机助手所需组件...
  py -3 -m pip install -r requirements-local-assistant.txt
  if errorlevel 1 (
    echo Google 组件安装失败，请检查网络后重试。
    pause
    exit /b 1
  )
)
py -3 local_assistant.py
if errorlevel 1 (
  echo.
  echo 启动失败：请确认已安装 Python 3，然后按任意键关闭。
  pause
)
