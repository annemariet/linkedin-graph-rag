#!/usr/bin/env python3
"""
Validation script for project-specific devcontainer migration.
This script validates that the migration to project-specific devcontainers is complete and correct.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional


def validate_project_structure(project_path: Path) -> Dict[str, any]:
    """Validate the structure of a project."""
    required_files = {
        "project.json": "Project configuration file",
        ".env.example": "Environment template file"
    }
    
    devcontainer_files = {
        ".devcontainer/devcontainer.json": "Devcontainer configuration",
        ".devcontainer/Dockerfile": "Docker build configuration"
    }
    
    results = {
        "project_files": {},
        "devcontainer_files": {},
        "valid": True,
        "errors": []
    }
    
    # Check project files
    for file_path, description in required_files.items():
        full_path = project_path / file_path
        if full_path.exists():
            results["project_files"][file_path] = {"exists": True, "description": description}
        else:
            results["project_files"][file_path] = {"exists": False, "description": description}
            results["errors"].append(f"Missing {file_path}")
    
    # Check devcontainer files
    for file_path, description in devcontainer_files.items():
        full_path = project_path / file_path
        if full_path.exists():
            results["devcontainer_files"][file_path] = {"exists": True, "description": description}
        else:
            results["devcontainer_files"][file_path] = {"exists": False, "description": description}
            results["errors"].append(f"Missing {file_path}")
            results["valid"] = False
    
    return results


def validate_old_devcontainer_removed() -> Dict[str, any]:
    """Validate that the old workspace-level devcontainer has been properly handled."""
    old_devcontainer = Path(".devcontainer")
    
    if not old_devcontainer.exists():
        return {
            "removed": True,
            "message": "Old workspace-level devcontainer has been removed"
        }
    else:
        # Check if it's been deprecated or updated
        devcontainer_json = old_devcontainer / "devcontainer.json"
        if devcontainer_json.exists():
            try:
                with open(devcontainer_json, 'r') as f:
                    content = f.read()
                    if "DEPRECATED" in content or "project-specific" in content:
                        return {
                            "removed": False,
                            "deprecated": True,
                            "message": "Old devcontainer exists but appears to be deprecated"
                        }
                    else:
                        return {
                            "removed": False,
                            "deprecated": False,
                            "message": "Old workspace-level devcontainer still exists and appears active"
                        }
            except:
                pass
        
        return {
            "removed": False,
            "deprecated": False,
            "message": "Old workspace-level devcontainer directory still exists"
        }


def validate_port_assignments() -> Dict[str, any]:
    """Validate that port assignments don't conflict between projects."""
    projects_dir = Path("projects")
    port_assignments = {}
    conflicts = []
    
    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        
        devcontainer_json = project_dir / ".devcontainer" / "devcontainer.json"
        if not devcontainer_json.exists():
            continue
        
        try:
            with open(devcontainer_json, 'r') as f:
                config = json.load(f)
            
            ports = config.get("forwardPorts", [])
            for port in ports:
                if port in port_assignments:
                    conflicts.append({
                        "port": port,
                        "projects": [port_assignments[port], project_dir.name]
                    })
                else:
                    port_assignments[port] = project_dir.name
        except:
            continue
    
    return {
        "port_assignments": port_assignments,
        "conflicts": conflicts,
        "valid": len(conflicts) == 0
    }


def main():
    """Main validation function."""
    projects_dir = Path("projects")
    
    if not projects_dir.exists():
        print("❌ Projects directory not found")
        sys.exit(1)
    
    print("🔍 Validating project-specific devcontainer migration...\n")
    
    # Validate old devcontainer status
    print("📁 Checking old workspace-level devcontainer...")
    old_devcontainer_status = validate_old_devcontainer_removed()
    if old_devcontainer_status["removed"]:
        print(f"  ✅ {old_devcontainer_status['message']}")
    elif old_devcontainer_status.get("deprecated"):
        print(f"  ⚠️  {old_devcontainer_status['message']}")
    else:
        print(f"  ❌ {old_devcontainer_status['message']}")
    print()
    
    # Validate each project
    project_results = {}
    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        
        print(f"📁 Validating {project_dir.name}...")
        
        # Validate project structure
        structure_result = validate_project_structure(project_dir)
        project_results[project_dir.name] = structure_result
        
        if structure_result["valid"]:
            print(f"  ✅ Project structure is valid")
            
            # Show what exists
            for file_path, info in structure_result["project_files"].items():
                status = "✅" if info["exists"] else "❌"
                print(f"    {status} {file_path}: {info['description']}")
            
            for file_path, info in structure_result["devcontainer_files"].items():
                status = "✅" if info["exists"] else "❌"
                print(f"    {status} {file_path}: {info['description']}")
        else:
            print(f"  ❌ Project structure has issues:")
            for error in structure_result["errors"]:
                print(f"    - {error}")
        
        print()
    
    # Validate port assignments
    print("🔍 Validating port assignments...")
    port_validation = validate_port_assignments()
    
    if port_validation["valid"]:
        print("  ✅ No port conflicts detected")
        print(f"  📊 Port assignments:")
        for port, project in port_validation["port_assignments"].items():
            print(f"    - Port {port}: {project}")
    else:
        print("  ❌ Port conflicts detected:")
        for conflict in port_validation["conflicts"]:
            projects = " and ".join(conflict["projects"])
            print(f"    - Port {conflict['port']}: {projects}")
    
    print()
    
    # Summary
    valid_projects = sum(1 for result in project_results.values() if result["valid"])
    total_projects = len(project_results)
    
    print(f"📊 Migration Summary:")
    print(f"  - Projects with valid structure: {valid_projects}/{total_projects}")
    print(f"  - Port conflicts: {'None' if port_validation['valid'] else len(port_validation['conflicts'])}")
    print(f"  - Old devcontainer: {'Removed' if old_devcontainer_status['removed'] else 'Still exists'}")
    
    if (valid_projects == total_projects and 
        port_validation["valid"] and 
        (old_devcontainer_status["removed"] or old_devcontainer_status.get("deprecated"))):
        print("\n🎉 Project-specific devcontainer migration is complete and valid!")
        return 0
    else:
        print("\n⚠️  Migration has some issues. Please review the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())