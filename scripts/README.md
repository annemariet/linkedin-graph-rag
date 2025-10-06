# Project Management Scripts

This directory contains essential Python scripts for managing the multi-project devcontainer setup. All scripts are designed to work reliably on Windows with Python.

## Essential Script

### `manage-projects.py`
The main script that handles all project management tasks.

**Usage:**
```bash
python scripts/manage-projects.py <command> [options]
```

**Commands:**
- `list` - List all projects with status overview
- `validate` - Validate all project configurations
- `validate-secrets [project]` - Validate project secrets
- `setup-secrets [project]` - Setup project secrets interactively
- `start <project>` - Start project in VS Code
- `run <project> [script]` - Run project script (default: dev)
- `docker` - Check Docker status

**Examples:**
```bash
# List all projects
python scripts/manage-projects.py list

# Validate all projects
python scripts/manage-projects.py validate

# Setup secrets for all projects
python scripts/manage-projects.py setup-secrets

# Setup secrets for specific project
python scripts/manage-projects.py setup-secrets code-review-assistant

# Start project in VS Code
python scripts/manage-projects.py start code-review-assistant

# Run project tests
python scripts/manage-projects.py run linkedin-api-client test

# Check Docker status
python scripts/manage-projects.py docker
```

## Project Status Indicators

- ✅ **Valid/Ready** - Project is properly configured
- ❌ **Invalid/Missing** - Project has issues that need fixing
- ⚠️ **Needs Setup** - Project exists but needs configuration

## Prerequisites

1. **Python 3.7+** - Required for all scripts
2. **Docker Desktop** - Must be installed and running
3. **VS Code** - Optional, for opening projects in devcontainers

## Quick Start

1. **Check everything is working:**
   ```bash
   python scripts/manage-projects.py list
   ```

2. **Setup secrets for all projects:**
   ```bash
   python scripts/manage-projects.py setup-secrets
   ```

3. **Start working on a project:**
   ```bash
   python scripts/manage-projects.py start code-review-assistant
   ```

## Security Notes

- All `.env.local` files are automatically ignored by git
- Never commit actual secrets to version control
- The script detects placeholder values and prompts for real ones

## Troubleshooting

### Docker Not Running
```
❌ Docker is not running or not accessible
```
**Solution:** Start Docker Desktop

### VS Code Not Found
```
❌ VS Code not available, try installing VS Code
```
**Solution:** Install VS Code and ensure `code` command works

### Missing Secrets
```
❌ Missing .env.local (run setup-secrets)
```
**Solution:** Run `python scripts/manage-projects.py setup-secrets`