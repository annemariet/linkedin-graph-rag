#!/usr/bin/env python3
"""
Test script to validate that each project's Docker containers can be built successfully.
This script tests the Docker build process for each project's devcontainer.
"""

import subprocess
import sys
from pathlib import Path
from typing import Dict, List


def test_docker_build(project_path: Path) -> Dict[str, any]:
    """Test Docker build for a project."""
    dockerfile_path = project_path / ".devcontainer" / "Dockerfile"
    
    if not dockerfile_path.exists():
        return {"success": False, "error": "Dockerfile not found"}
    
    try:
        # Build the Docker image
        build_command = [
            "docker", "build",
            "-f", str(dockerfile_path),
            "-t", f"test-{project_path.name}:latest",
            str(project_path / ".devcontainer")
        ]
        
        print(f"  Building Docker image for {project_path.name}...")
        result = subprocess.run(
            build_command,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode == 0:
            return {"success": True, "message": "Docker build successful"}
        else:
            return {
                "success": False, 
                "error": f"Docker build failed: {result.stderr[:500]}"
            }
            
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Docker build timed out (5 minutes)"}
    except Exception as e:
        return {"success": False, "error": f"Error running docker build: {e}"}


def check_docker_available() -> bool:
    """Check if Docker is available."""
    try:
        result = subprocess.run(
            ["docker", "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except:
        return False


def main():
    """Main test function."""
    projects_dir = Path("projects")
    
    if not projects_dir.exists():
        print("❌ Projects directory not found")
        sys.exit(1)
    
    if not check_docker_available():
        print("❌ Docker is not available. Please ensure Docker is installed and running.")
        print("   This test requires Docker to build the devcontainer images.")
        sys.exit(1)
    
    print("🐳 Testing Docker builds for project-specific devcontainers...\n")
    print("⚠️  Note: This test requires Docker to be running and may take several minutes.\n")
    
    results = {}
    
    # Find all projects with devcontainer configurations
    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        
        devcontainer_dir = project_dir / ".devcontainer"
        if not devcontainer_dir.exists():
            print(f"⚠️  {project_dir.name}: No devcontainer configuration found")
            continue
        
        print(f"📁 Testing {project_dir.name}...")
        
        # Test Docker build
        build_result = test_docker_build(project_dir)
        results[project_dir.name] = build_result
        
        if build_result["success"]:
            print(f"  ✅ {build_result['message']}")
        else:
            print(f"  ❌ {build_result['error']}")
        
        print()
    
    # Summary
    successful_builds = sum(1 for result in results.values() if result.get("success"))
    total_projects = len(results)
    
    print(f"📊 Summary: {successful_builds}/{total_projects} projects built successfully")
    
    if successful_builds == total_projects:
        print("🎉 All project Docker builds completed successfully!")
        return 0
    else:
        print("⚠️  Some Docker builds failed. Please review the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())