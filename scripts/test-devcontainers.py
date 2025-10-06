#!/usr/bin/env python3
"""
Test script to validate project-specific devcontainer configurations.
This script checks that each project's devcontainer configuration is valid.
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional


def validate_devcontainer_json(project_path: Path) -> Dict[str, any]:
    """Validate devcontainer.json configuration."""
    devcontainer_path = project_path / ".devcontainer" / "devcontainer.json"
    
    if not devcontainer_path.exists():
        return {"valid": False, "error": "devcontainer.json not found"}
    
    try:
        with open(devcontainer_path, 'r') as f:
            config = json.load(f)
        
        # Check required fields
        required_fields = ["name", "workspaceFolder", "remoteUser"]
        missing_fields = [field for field in required_fields if field not in config]
        
        if missing_fields:
            return {
                "valid": False, 
                "error": f"Missing required fields: {missing_fields}"
            }
        
        # Check port conflicts
        ports = config.get("forwardPorts", [])
        
        return {
            "valid": True,
            "name": config["name"],
            "ports": ports,
            "features": list(config.get("features", {}).keys()),
            "extensions": len(config.get("customizations", {}).get("vscode", {}).get("extensions", []))
        }
        
    except json.JSONDecodeError as e:
        return {"valid": False, "error": f"Invalid JSON: {e}"}
    except Exception as e:
        return {"valid": False, "error": f"Error reading file: {e}"}


def validate_docker_compose(project_path: Path) -> Dict[str, any]:
    """Validate docker-compose.yml configuration."""
    compose_path = project_path / ".devcontainer" / "docker-compose.yml"
    
    if not compose_path.exists():
        return {"valid": True, "note": "No docker-compose.yml (using Dockerfile only)"}
    
    try:
        # Basic validation - check if file exists and is readable
        with open(compose_path, 'r') as f:
            content = f.read()
        
        # Check for basic structure
        if "services:" not in content:
            return {"valid": False, "error": "No services section found"}
        
        if "app:" not in content:
            return {"valid": False, "error": "No app service found"}
        
        return {"valid": True, "note": "docker-compose.yml found and readable"}
        
    except Exception as e:
        return {"valid": False, "error": f"Error reading docker-compose.yml: {e}"}


def validate_dockerfile(project_path: Path) -> Dict[str, any]:
    """Validate Dockerfile configuration."""
    dockerfile_path = project_path / ".devcontainer" / "Dockerfile"
    
    if not dockerfile_path.exists():
        return {"valid": False, "error": "Dockerfile not found"}
    
    try:
        with open(dockerfile_path, 'r') as f:
            content = f.read()
        
        # Check for basic structure
        if not content.startswith("# ") and "FROM " not in content:
            return {"valid": False, "error": "Invalid Dockerfile format"}
        
        return {"valid": True, "note": "Dockerfile found and readable"}
        
    except Exception as e:
        return {"valid": False, "error": f"Error reading Dockerfile: {e}"}


def check_port_conflicts(projects_config: Dict[str, Dict]) -> List[str]:
    """Check for port conflicts between projects."""
    port_usage = {}
    conflicts = []
    
    for project_name, config in projects_config.items():
        if not config.get("valid"):
            continue
            
        ports = config.get("ports", [])
        for port in ports:
            if port in port_usage:
                conflicts.append(f"Port {port} conflict between {project_name} and {port_usage[port]}")
            else:
                port_usage[port] = project_name
    
    return conflicts


def main():
    """Main validation function."""
    projects_dir = Path("projects")
    
    if not projects_dir.exists():
        print("❌ Projects directory not found")
        sys.exit(1)
    
    print("🔍 Validating project-specific devcontainer configurations...\n")
    
    projects_config = {}
    
    # Find all projects with devcontainer configurations
    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        
        devcontainer_dir = project_dir / ".devcontainer"
        if not devcontainer_dir.exists():
            print(f"⚠️  {project_dir.name}: No devcontainer configuration found")
            continue
        
        print(f"📁 Validating {project_dir.name}...")
        
        # Validate devcontainer.json
        devcontainer_result = validate_devcontainer_json(project_dir)
        projects_config[project_dir.name] = devcontainer_result
        
        if devcontainer_result["valid"]:
            print(f"  ✅ devcontainer.json: {devcontainer_result['name']}")
            print(f"     Ports: {devcontainer_result['ports']}")
            print(f"     Features: {len(devcontainer_result['features'])}")
            print(f"     Extensions: {devcontainer_result['extensions']}")
        else:
            print(f"  ❌ devcontainer.json: {devcontainer_result['error']}")
        
        # Validate docker-compose.yml
        compose_result = validate_docker_compose(project_dir)
        if compose_result["valid"]:
            print(f"  ✅ docker-compose.yml: {compose_result.get('note', 'Valid')}")
        else:
            print(f"  ❌ docker-compose.yml: {compose_result['error']}")
        
        # Validate Dockerfile
        dockerfile_result = validate_dockerfile(project_dir)
        if dockerfile_result["valid"]:
            print(f"  ✅ Dockerfile: {dockerfile_result['note']}")
        else:
            print(f"  ❌ Dockerfile: {dockerfile_result['error']}")
        
        print()
    
    # Check for port conflicts
    print("🔍 Checking for port conflicts...")
    conflicts = check_port_conflicts(projects_config)
    
    if conflicts:
        print("❌ Port conflicts found:")
        for conflict in conflicts:
            print(f"  - {conflict}")
    else:
        print("✅ No port conflicts detected")
    
    # Summary
    valid_projects = sum(1 for config in projects_config.values() if config.get("valid"))
    total_projects = len(projects_config)
    
    print(f"\n📊 Summary: {valid_projects}/{total_projects} projects have valid devcontainer configurations")
    
    if valid_projects == total_projects and not conflicts:
        print("🎉 All project devcontainer configurations are valid!")
        return 0
    else:
        print("⚠️  Some issues found. Please review the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())