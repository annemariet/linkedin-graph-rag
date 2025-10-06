@echo off
REM Get DevPod SSH connection information (Windows)

echo 🔍 DevPod SSH Connection Information
echo ==================================

REM Check if DevPod is running
devpod list | findstr "Running" >nul
if %errorlevel% neq 0 (
    echo ❌ No running DevPod workspaces found.
    echo    Start your workspace first: devpod up .
    exit /b 1
)

echo 📋 Available workspaces:
devpod list

echo.
echo 🔑 SSH connection details:
echo =========================
devpod ssh-server . --print-config

echo.
echo 🚀 Quick connection options:
echo ============================
echo 1. Direct SSH via DevPod:
echo    devpod ssh .
echo.
echo 2. For VSCodium Remote-SSH, add this to ~/.ssh/config:
echo    Host devpod-amai-lab
devpod ssh-server . --print-config

echo.
echo ✅ Ready to connect!