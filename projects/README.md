# Projects Directory

This directory contains all projects in the multi-project workspace. Each project is organized independently with its own configuration, dependencies, and environment settings.

## Prerequisites

All projects use **uv** as the package manager for fast and reliable Python dependency management. Make sure uv is installed:

```bash
# Install uv (choose one method)
curl -LsSf https://astral.sh/uv/install.sh | sh  # Unix/macOS
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows
pip install uv  # Via pip (fallback method)
```

Verify installation:
```bash
uv --version
```

## Project Structure

Each project follows this structure:
```
projects/
├── project-name/
│   ├── project.json          # Project configuration and scripts
│   ├── .env.example          # Environment variable template
│   ├── .env.local            # Local environment variables (git-ignored)
│   ├── pyproject.toml        # Python project configuration
│   └── [project files...]    # Project-specific files
└── workspace.json            # Workspace-level configuration
```

## Available Projects

### code-review-assistant
- **Type**: Python (FastAPI)
- **Description**: Multi-agent code review system using CrewAI and FastAPI
- **Ports**: 8000, 8001
- **Services**: PostgreSQL, Redis
- **Status**: Active

### linkedin-api-client
- **Type**: Python (Library)
- **Description**: Official Python client library for LinkedIn APIs
- **Ports**: 8002, 8003
- **Services**: None
- **Status**: Active

### fitbit-analysis
- **Type**: Python (Analysis)
- **Description**: Fitbit data analysis and visualization project
- **Ports**: 8004, 8005
- **Services**: None
- **Status**: Development

## Running Projects

### Using the run-project script:
```bash
# List all available projects
python scripts/run-project.py --list

# Run a project's development server
python scripts/run-project.py code-review-assistant dev
python scripts/run-project.py linkedin-api-client dev

# Run tests
python scripts/run-project.py code-review-assistant test
python scripts/run-project.py linkedin-api-client test

# Run other scripts
python scripts/run-project.py code-review-assistant lint
python scripts/run-project.py code-review-assistant format
```

### Direct project execution:
```bash
# Navigate to project directory
cd projects/code-review-assistant

# Install dependencies with uv
uv sync --all-extras

# Run development server
uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
uv run pytest
```

## Environment Configuration

Each project has its own environment configuration:

1. **`.env.example`**: Template file with all required environment variables
2. **`.env.local`**: Local environment variables (git-ignored, create from .env.example)

### Setting up environment variables:
```bash
# Copy template to local file
cp projects/code-review-assistant/.env.example projects/code-review-assistant/.env.local

# Edit the .env.local file with your actual values
# Never commit .env.local files to git
```

## Project Configuration

Each project has a `project.json` file that defines:
- Project metadata (name, type, description)
- Available scripts (dev, test, lint, etc.)
- Port assignments
- Required services
- Environment variables
- Dependencies

Example `project.json`:
```json
{
  "name": "my-project",
  "type": "python",
  "description": "My awesome project",
  "services": ["postgres", "redis"],
  "ports": [8000, 8001],
  "scripts": {
    "dev": "uvicorn main:app --reload",
    "test": "pytest",
    "lint": "flake8 ."
  }
}
```

## Port Allocation

Projects are assigned specific port ranges to avoid conflicts:
- **code-review-assistant**: 8000-8001
- **linkedin-api-client**: 8002-8003
- **fitbit-analysis**: 8004-8005
- **Future projects**: 8006+

## Services

Shared services are managed at the workspace level:
- **PostgreSQL**: Port 5432 (for projects that need a database)
- **Redis**: Port 6379 (for caching and task queues)

## Validation

Use the validation script to ensure all projects are properly configured:
```bash
python scripts/validate-projects.py
```

This checks:
- All projects have required configuration files
- No port conflicts exist
- Project configurations are valid JSON
- Environment templates are present

## Adding New Projects

1. Create a new directory under `projects/`
2. Add a `project.json` configuration file
3. Add a `.env.example` template file
4. Update `projects/workspace.json` to include the new project
5. Run validation: `python scripts/validate-projects.py`

## Development Workflow

1. **Prerequisites**: Ensure uv is installed (`uv --version`)
2. **Setup**: Copy `.env.example` to `.env.local` and configure
3. **Install Dependencies**: `uv sync --all-extras` (or use run-project script)
4. **Development**: Use `python scripts/run-project.py <project> dev`
5. **Testing**: Use `python scripts/run-project.py <project> test`
6. **Code Quality**: Use lint, format, and type-check scripts
7. **Validation**: Run `python scripts/validate-projects.py` before commits

### Why uv?

- **Fast**: 10-100x faster than pip for dependency resolution and installation
- **Reliable**: Consistent dependency resolution across environments
- **Modern**: Built-in support for lockfiles, virtual environments, and project management
- **Compatible**: Works with existing pip and PyPI ecosystem