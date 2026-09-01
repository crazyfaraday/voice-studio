@echo off
cd /d "%~dp0"
py -3 -c "import webview, google.oauth2.service_account" >nul 2>nul
if errorlevel 1 (
  echo 正在安装桌面应用所需组件，请稍候...
  py -3 -m pip install -r requirements-desktop.txt
  if errorlevel 1 (
    echo 组件安装失败，请检查网络后重试。
    pause
    exit /b 1
  )
)
py -3 desktop_app.py
if errorlevel 1 pause
