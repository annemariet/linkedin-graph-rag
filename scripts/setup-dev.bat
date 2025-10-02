@echo off
REM Development environment setup script for Code Review Assistant (Windows)

echo Setting up Code Review Assistant development environment...

REM Check if Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python is not installed or not in PATH
    exit /b 1
)

echo ✓ Python is available

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip

REM Install dependencies
echo Installing development dependencies...
pip install -e ".[dev,tools]"

REM Install pre-commit hooks
echo Installing pre-commit hooks...
pre-commit install

REM Copy environment file if it doesn't exist
if not exist ".env" (
    echo Creating .env file from template...
    copy .env.example .env
    echo ⚠️  Please update .env file with your configuration
)

REM Check if Docker is available
docker --version >nul 2>&1
if %errorlevel% equ 0 (
    echo ✓ Docker is available
    
    REM Check if Docker Compose is available
    docker-compose --version >nul 2>&1
    if %errorlevel% equ 0 (
        echo ✓ Docker Compose is available
        echo You can start services with: make docker-up
    ) else (
        echo ⚠️  Docker Compose not found. Install it for full development experience.
    )
) else (
    echo ⚠️  Docker not found. Install it for containerized development.
)

echo.
echo 🎉 Development environment setup complete!
echo.
echo Next steps:
echo 1. Update .env file with your configuration
echo 2. Start the development server: make run
echo 3. Or use Docker: make docker-up
echo 4. Run tests: make test
echo 5. View available commands: make help

pause