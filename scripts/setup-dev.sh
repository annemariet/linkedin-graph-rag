#!/bin/bash

# Development environment setup script for Code Review Assistant

set -e

echo "Setting up Code Review Assistant development environment..."

# Check if Python 3.11+ is available
python_version=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
required_version="3.11"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "Error: Python 3.11 or higher is required. Found: $python_version"
    exit 1
fi

echo "✓ Python version check passed"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing development dependencies..."
uv sync --all-extras

# Install pre-commit hooks
echo "Installing pre-commit hooks..."
pre-commit install

# Copy environment file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please update .env file with your configuration"
fi

# Check if Docker is available
if command -v docker &> /dev/null; then
    echo "✓ Docker is available"
    
    # Check if Docker Compose is available
    if command -v docker-compose &> /dev/null; then
        echo "✓ Docker Compose is available"
        echo "You can start services with: make docker-up"
    else
        echo "⚠️  Docker Compose not found. Install it for full development experience."
    fi
else
    echo "⚠️  Docker not found. Install it for containerized development."
fi

echo ""
echo "🎉 Development environment setup complete!"
echo ""
echo "Next steps:"
echo "1. Update .env file with your configuration"
echo "2. Start the development server: make run"
echo "3. Or use Docker: make docker-up"
echo "4. Run tests: make test"
echo "5. View available commands: make help"