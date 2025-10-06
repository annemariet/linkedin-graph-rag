#!/usr/bin/env python3
"""
Validate project configurations for multi-project setup.
Ensures each project has the necessary configuration files and can run independently.
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional


def validate_project_structure(project_path: Path) -> List[str]:
    """Validate that a project has the required structure."""
    errors = []
    
    # Check for project.json
    project_json = project_path / "project.json"
    if not project_json.exists():
        errors.append(f"Missing project.json in {project_path}")
    else:
        try:
            with open(project_json) as f:
                config = json.load(f)
                required_fields = ["name", "type", "scripts"]
                for field in required_fields:
                    if field not in config:
                        errors.append(f"Missing required field '{field}' in {project_json}")
                
                # Check if project uses uv as package manager
                dependencies = config.get("dependencies", {})
                package_manager = dependencies.get("package_manager")
                if package_manager != "uv":
                    errors.append(f"Project {config.get('name', 'unknown')} should use 'uv' as package_manager")
                
                # Validate that scripts use 'uv run' prefix for Python commands
                scripts = config.get("scripts", {})
                for script_name, script_cmd in scripts.items():
                    if script_name in ["dev", "test", "lint", "format", "type-check", "security"] and not script_cmd.startswith("uv run"):
                        errors.append(f"Script '{script_name}' in {config.get('name', 'unknown')} should use 'uv run' prefix")
                        
        except json.JSONDecodeError as e:
            errors.append(f"Invalid JSON in {project_json}: {e}")
    
    # Check for .env.example
    env_example = project_path / ".env.example"
    if not env_example.exists():
        errors.append(f"Missing .env.example in {project_path}")
    
    # Check for pyproject.toml
    pyproject_toml = project_path / "pyproject.toml"
    if not pyproject_toml.exists():
        errors.append(f"Missing pyproject.toml in {project_path}")
    else:
        # Check if pyproject.toml has uv configuration
        try:
            import tomllib
        except ImportError:
            try:
                import tomli as tomllib
            except ImportError:
                # Skip TOML validation if no parser available
                pass
            else:
                try:
                    with open(pyproject_toml, 'rb') as f:
                        toml_data = tomllib.load(f)
                        if "tool" in toml_data and "uv" not in toml_data["tool"]:
                            errors.append(f"pyproject.toml in {project_path} should include [tool.uv] section for uv compatibility")
                except Exception as e:
                    errors.append(f"Error reading pyproject.toml in {project_path}: {e}")
    
    return errors


def validate_port_conflicts(workspace_config: Dict) -> List[str]:
    """Validate that projects don't have conflicting port assignments."""
    errors = []
    used_ports = set()
    
    for project in workspace_config.get("projects", []):
        project_ports = project.get("ports", [])
        for port in project_ports:
            if port in used_ports:
                errors.append(f"Port conflict: {port} used by multiple projects")
            used_ports.add(port)
    
    return errors


def main():
    """Main validation function."""
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
    
    all_errors = []
    
    # Validate each project
    for project_info in workspace_config.get("projects", []):
        project_name = project_info.get("name")
        project_path = workspace_root / project_info.get("path", "")
        
        print(f"Validating project: {project_name}")
        
        if not project_path.exists():
            all_errors.append(f"Project directory not found: {project_path}")
            continue
        
        project_errors = validate_project_structure(project_path)
        all_errors.extend(project_errors)
    
    # Validate port conflicts
    port_errors = validate_port_conflicts(workspace_config)
    all_errors.extend(port_errors)
    
    # Report results
    if all_errors:
        print("\nValidation FAILED with the following errors:")
        for error in all_errors:
            print(f"  - {error}")
        sys.exit(1)
    else:
        print("\nValidation PASSED: All projects are properly configured!")
        sys.exit(0)


if __name__ == "__main__":
    main()