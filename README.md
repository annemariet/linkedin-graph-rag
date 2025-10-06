# Code Review Assistant

A multi-agent code review system that leverages specialized LLM agents to perform comprehensive code analysis including style, security, performance, and test coverage evaluation.

## Features

- **Multi-Agent Architecture**: Specialized agents for different aspects of code review
- **Comprehensive Analysis**: Style, security, performance, and test coverage analysis
- **Interactive Feedback**: Ask questions and get clarifications on review findings
- **Configurable Rules**: Customize analysis based on project requirements
- **Multiple Language Support**: Python, JavaScript, TypeScript, Java, and more

## Quick Start

### Prerequisites

- Python 3.12+
- Docker and Docker Compose
- Git

### Installation

#### Option 1: DevPod (Recommended)

1. Install DevPod:
```bash
# Windows
winget install loft-sh.devpod

# macOS
brew install devpod

# Linux
curl -L -o devpod https://github.com/loft-sh/devpod/releases/latest/download/devpod-linux-amd64
sudo install -c -m 0755 devpod /usr/local/bin
```

2. Clone and setup:
```bash
git clone <repository-url>
cd amai-lab

# Run setup script
./scripts/devpod-setup.sh    # Linux/macOS
scripts\devpod-setup.bat     # Windows

# Connect to the workspace
devpod ssh .
```

#### Option 2: Local Development

1. Clone the repository:
```bash
git clone <repository-url>
cd amai-lab
```

2. Create and activate virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
uv sync --all-extras
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

5. Start the development environment:
```bash
docker-compose up -d
```

6. Run the application:
```bash
uvicorn src.main:app --reload
```

## Development

### Running Tests
```bash
pytest
```

### Code Formatting
```bash
black src tests
```

### Linting
```bash
flake8 src tests
mypy src
```

### Pre-commit Hooks
```bash
pre-commit install
```

## Architecture

The system uses a multi-agent architecture with CrewAI for orchestration:

- **Coordinator Agent**: Manages workflow and task distribution
- **Style Analyzer Agent**: Code quality and formatting analysis
- **Security Scanner Agent**: Vulnerability and security issue detection
- **Performance Analyzer Agent**: Performance bottleneck identification
- **Test Coverage Agent**: Test quality and coverage analysis
- **Report Synthesizer Agent**: Consolidates findings into comprehensive reports
- **Interactive Assistant Agent**: Handles follow-up questions and clarifications

## API Documentation

Once running, visit `http://localhost:8000/docs` for interactive API documentation.

## License

MIT License - see LICENSE file for details.