@echo off
REM DevPod setup script for amai-lab workspace (Windows)

echo 🚀 Setting up DevPod workspace for amai-lab...

REM Check if DevPod is installed
devpod version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ DevPod is not installed. Please install it first:
    echo    winget install loft-sh.devpod
    echo    Or download from: https://github.com/loft-sh/devpod/releases
    exit /b 1
)

echo ✅ DevPod found
devpod version

REM Check if Docker is available
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Docker is not installed or not running. Please install Docker first.
    exit /b 1
)

echo ✅ Docker found
docker --version

REM Set up Docker provider if not already configured
echo 🔧 Configuring Docker provider...
devpod provider add docker --if-not-exists
devpod provider use docker

REM Create the workspace
echo 🏗️  Creating DevPod workspace...
devpod up . --ide none --provider docker

echo ✅ DevPod workspace created successfully!
echo.
echo 📋 Next steps:
echo    1. Connect to the workspace: devpod ssh .
echo    2. Or run commands directly: devpod exec . -- bash
echo    3. Access services:
echo       - PostgreSQL: localhost:5432
echo       - Redis: localhost:6379
echo       - Code Review Assistant: localhost:8000
echo       - LinkedIn API Client: localhost:8002
echo.
echo 🔧 Available commands in the container:
echo    - python scripts/validate-projects.py
echo    - python scripts/run-project.py --list
echo    - uv --version
echo.
echo 🎉 Happy coding!