#!/usr/bin/env python3
"""
Run a specific project in the multi-project workspace.
Provides a unified interface to run any project with its specific configuration.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional


def load_project_config(project_path: Path) -> Optional[Dict]:
    """Load project configuration from project.json."""
    config_path = project_path / "project.json"
    if not config_path.exists():
        print(f"ERROR: No project.json found in {project_path}")
        return None
    
    try:
        with open(config_path) as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in {config_path}: {e}")
        return None


def run_project_script(project_path: Path, script_name: str, config: Dict) -> int:
    """Run a specific script for the project."""
    scripts = config.get("scripts", {})
    if script_name not in scripts:
        print(f"ERROR: Script '{script_name}' not found in project configuration")
        print(f"Available scripts: {', '.join(scripts.keys())}")
        return 1
    
    command = scripts[script_name]
    print(f"Running: {command}")
    print(f"Working directory: {project_path}")
    
    # Check if uv is available
    try:
        subprocess.run(["uv", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("ERROR: uv is not installed or not available in PATH")
        print("Please install uv: https://docs.astral.sh/uv/getting-started/installation/")
        return 1
    
    # Set up environment
    env = os.environ.copy()
    project_env = config.get("environment", {})
    env.update(project_env)
    
    # Ensure uv sync is run before executing scripts that use uv run
    if command.startswith("uv run") and script_name != "install":
        print("Ensuring dependencies are synced...")
        try:
            sync_result = subprocess.run(
                ["uv", "sync"],
                cwd=project_path,
                env=env,
                capture_output=True,
                text=True
            )
            if sync_result.returncode != 0:
                print(f"Warning: uv sync failed: {sync_result.stderr}")
        except Exception as e:
            print(f"Warning: Could not run uv sync: {e}")
    
    # Run the command
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=project_path,
            env=env
        )
        return result.returncode
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        return 130
    except Exception as e:
        print(f"ERROR: Failed to run command: {e}")
        return 1


def list_projects() -> None:
    """List all available projects."""
    workspace_root = Path(__file__).parent.parent
    workspace_config_path = workspace_root / "projects" / "workspace.json"
    
    if not workspace_config_path.exists():
        print("ERROR: workspace.json not found")
        return
    
    try:
        with open(workspace_config_path) as f:
            workspace_config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in workspace.json: {e}")
        return
    
    print("Available projects:")
    for project in workspace_config.get("projects", []):
        name = project.get("name", "Unknown")
        description = project.get("description", "No description")
        status = project.get("status", "unknown")
        print(f"  - {name} ({status}): {description}")


def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("Usage: python run-project.py <project-name> [script-name]")
        print("       python run-project.py --list")
        print("\nExamples:")
        print("  python run-project.py code-review-assistant dev")
        print("  python run-project.py linkedin-api-client test")
        print("  python run-project.py --list")
        sys.exit(1)
    
    if sys.argv[1] == "--list":
        list_projects()
        sys.exit(0)
    
    project_name = sys.argv[1]
    script_name = sys.argv[2] if len(sys.argv) > 2 else "dev"
    
    workspace_root = Path(__file__).parent.parent
    
    # Find project path
    workspace_config_path = workspace_root / "projects" / "workspace.json"
    if workspace_config_path.exists():
        try:
            with open(workspace_config_path) as f:
                workspace_config = json.load(f)
            
            project_path = None
            for project in workspace_config.get("projects", []):
                if project.get("name") == project_name:
                    project_path = workspace_root / project.get("path", "")
                    break
            
            if not project_path:
                print(f"ERROR: Project '{project_name}' not found in workspace configuration")
                list_projects()
                sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid JSON in workspace.json: {e}")
            sys.exit(1)
    else:
        # Fallback: try to find project directly
        project_path = workspace_root / "projects" / project_name
        if not project_path.exists():
            print(f"ERROR: Project directory not found: {project_path}")
            sys.exit(1)
    
    # Load project configuration
    config = load_project_config(project_path)
    if not config:
        sys.exit(1)
    
    # Run the script
    exit_code = run_project_script(project_path, script_name, config)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()