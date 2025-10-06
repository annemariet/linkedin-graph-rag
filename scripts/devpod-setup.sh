#!/bin/bash
# DevPod setup script for amai-lab workspace

set -e

echo "🚀 Setting up DevPod workspace for amai-lab..."

# Check if DevPod is installed
if ! command -v devpod &> /dev/null; then
    echo "❌ DevPod is not installed. Please install it first:"
    echo "   Windows: winget install loft-sh.devpod"
    echo "   macOS: brew install devpod"
    echo "   Linux: curl -L -o devpod https://github.com/loft-sh/devpod/releases/latest/download/devpod-linux-amd64 && sudo install -c -m 0755 devpod /usr/local/bin"
    exit 1
fi

echo "✅ DevPod found: $(devpod version)"

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed or not running. Please install Docker first."
    exit 1
fi

echo "✅ Docker found: $(docker --version)"

# Set up Docker provider if not already configured
echo "🔧 Configuring Docker provider..."
devpod provider add docker --if-not-exists
devpod provider use docker

# Create the workspace
echo "🏗️  Creating DevPod workspace..."
devpod up . --ide none --provider docker

echo "✅ DevPod workspace created successfully!"
echo ""
echo "📋 Next steps:"
echo "   1. Connect to the workspace: devpod ssh ."
echo "   2. Or run commands directly: devpod exec . -- bash"
echo "   3. Access services:"
echo "      - PostgreSQL: localhost:5432"
echo "      - Redis: localhost:6379"
echo "      - Code Review Assistant: localhost:8000"
echo "      - LinkedIn API Client: localhost:8002"
echo ""
echo "🔧 Available commands in the container:"
echo "   - python scripts/validate-projects.py"
echo "   - python scripts/run-project.py --list"
echo "   - uv --version"
echo ""
echo "🎉 Happy coding!"