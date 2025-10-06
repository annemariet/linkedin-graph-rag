#!/usr/bin/env python3
"""
Migration script to convert projects from pip/poetry to uv.
This script helps migrate existing Python projects to use uv as the package manager.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional


def check_uv_installed() -> bool:
    """Check if uv is installed and available."""
    try:
        result = subprocess.run(["uv", "--version"], capture_output=True, check=True)
        print(f"✓ uv is installed: {result.stdout.decode().strip()}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("✗ uv is not installed")
        print("Install uv: https://docs.astral.sh/uv/getting-started/installation/")
        return False


def migrate_poetry_project(project_path: Path) -> bool:
    """Migrate a Poetry project to uv."""
    poetry_toml = project_path / "pyproject.toml"
    poetry_lock = project_path / "poetry.lock"
    
    if not poetry_toml.exists():
        return False
    
    print(f"Migrating Poetry project: {project_path}")
    
    # Backup original files
    if poetry_toml.exists():
        shutil.copy2(poetry_toml, project_path / "pyproject.toml.poetry-backup")
    if poetry_lock.exists():
        shutil.copy2(poetry_lock, project_path / "poetry.lock.backup")
    
    # Check if we have a uv-compatible version
    uv_toml = project_path / "pyproject.toml.uv"
    if uv_toml.exists():
        print("  ✓ Found uv-compatible pyproject.toml, replacing...")
        shutil.copy2(uv_toml, poetry_toml)
        uv_toml.unlink()  # Remove the .uv file
    else:
        print("  ! No uv-compatible pyproject.toml found, manual conversion needed")
        return False
    
    # Remove poetry.lock if it exists
    if poetry_lock.exists():
        poetry_lock.unlink()
        print("  ✓ Removed poetry.lock")
    
    # Initialize uv project
    try:
        subprocess.run(["uv", "sync"], cwd=project_path, check=True, capture_output=True)
        print("  ✓ uv sync completed successfully")
    except subprocess.CalledProcessError as e:
        print(f"  ✗ uv sync failed: {e}")
        return False
    
    return True


def migrate_pip_project(project_path: Path) -> bool:
    """Migrate a pip-based project to uv."""
    requirements_txt = project_path / "requirements.txt"
    requirements_dev = project_path / "requirements-dev.txt"
    pyproject_toml = project_path / "pyproject.toml"
    
    print(f"Migrating pip project: {project_path}")
    
    # If there's already a pyproject.toml, try to add uv configuration
    if pyproject_toml.exists():
        print("  ✓ pyproject.toml exists, adding uv configuration")
        # This would require TOML parsing and modification
        # For now, we'll just run uv sync to create uv.lock
    
    # Initialize uv project
    try:
        subprocess.run(["uv", "sync"], cwd=project_path, check=True, capture_output=True)
        print("  ✓ uv sync completed successfully")
    except subprocess.CalledProcessError as e:
        print(f"  ✗ uv sync failed: {e}")
        return False
    
    return True


def update_project_json(project_path: Path) -> bool:
    """Update project.json to use uv commands."""
    project_json = project_path / "project.json"
    if not project_json.exists():
        return False
    
    try:
        with open(project_json) as f:
            config = json.load(f)
        
        # Update package manager
        if "dependencies" not in config:
            config["dependencies"] = {}
        config["dependencies"]["package_manager"] = "uv"
        
        # Update scripts to use uv run
        scripts = config.get("scripts", {})
        updated_scripts = {}
        
        for script_name, script_cmd in scripts.items():
            if script_name in ["dev", "test", "lint", "format", "type-check", "security"]:
                if not script_cmd.startswith("uv run"):
                    # Add uv run prefix to Python commands
                    if any(cmd in script_cmd for cmd in ["python", "pytest", "black", "flake8", "mypy", "bandit", "uvicorn"]):
                        updated_scripts[script_name] = f"uv run {script_cmd}"
                    else:
                        updated_scripts[script_name] = script_cmd
                else:
                    updated_scripts[script_name] = script_cmd
            elif script_name in ["install", "install-dev"]:
                if "pip install" in script_cmd:
                    updated_scripts[script_name] = "uv sync --all-extras" if "dev" in script_name else "uv sync"
                elif "poetry install" in script_cmd:
                    updated_scripts[script_name] = "uv sync --all-extras" if "dev" in script_name else "uv sync"
                else:
                    updated_scripts[script_name] = script_cmd
            elif script_name == "build":
                if "poetry build" in script_cmd:
                    updated_scripts[script_name] = "uv build"
                else:
                    updated_scripts[script_name] = script_cmd
            else:
                updated_scripts[script_name] = script_cmd
        
        config["scripts"] = updated_scripts
        
        # Write back to file
        with open(project_json, 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"  ✓ Updated {project_json}")
        return True
        
    except (json.JSONDecodeError, IOError) as e:
        print(f"  ✗ Failed to update {project_json}: {e}")
        return False


def migrate_project(project_path: Path) -> bool:
    """Migrate a single project to uv."""
    if not project_path.is_dir():
        print(f"✗ {project_path} is not a directory")
        return False
    
    print(f"\n--- Migrating {project_path.name} ---")
    
    success = True
    
    # Check what type of project this is
    poetry_toml = project_path / "pyproject.toml"
    poetry_lock = project_path / "poetry.lock"
    requirements_txt = project_path / "requirements.txt"
    
    if poetry_lock.exists():
        success &= migrate_poetry_project(project_path)
    elif requirements_txt.exists() or poetry_toml.exists():
        success &= migrate_pip_project(project_path)
    else:
        print("  ! No Python package files found, skipping")
        return True
    
    # Update project.json
    success &= update_project_json(project_path)
    
    return success


def main():
    """Main migration function."""
    if not check_uv_installed():
        sys.exit(1)
    
    workspace_root = Path(__file__).parent.parent
    projects_dir = workspace_root / "projects"
    
    if not projects_dir.exists():
        print("ERROR: projects/ directory not found")
        sys.exit(1)
    
    # Load workspace configuration
    workspace_config_path = projects_dir / "workspace.json"
    if not workspace_config_path.exists():
        print("ERROR: projects/workspace.json not found")
        sys.exit(1)
    
    try:
        with open(workspace_config_path) as f:
            workspace_config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in workspace.json: {e}")
        sys.exit(1)
    
    # Migrate each project
    all_success = True
    for project_info in workspace_config.get("projects", []):
        project_name = project_info.get("name")
        project_path = workspace_root / project_info.get("path", "")
        
        if project_path.exists():
            success = migrate_project(project_path)
            all_success &= success
        else:
            print(f"✗ Project directory not found: {project_path}")
            all_success = False
    
    # Final validation
    print("\n--- Running validation ---")
    try:
        result = subprocess.run([
            sys.executable, 
            str(workspace_root / "scripts" / "validate-projects.py")
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✓ All projects validated successfully!")
        else:
            print("✗ Validation failed:")
            print(result.stdout)
            all_success = False
    except Exception as e:
        print(f"✗ Could not run validation: {e}")
        all_success = False
    
    if all_success:
        print("\n🎉 Migration completed successfully!")
        print("All projects are now configured to use uv.")
    else:
        print("\n⚠️  Migration completed with some issues.")
        print("Please review the output above and fix any remaining issues.")
    
    sys.exit(0 if all_success else 1)


if __name__ == "__main__":
    main()