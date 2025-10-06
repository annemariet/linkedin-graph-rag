#!/usr/bin/env python3
"""
Validation script to check if the development environment is properly set up.
"""

import subprocess
import sys
from pathlib import Path


def run_command(command: str, description: str) -> bool:
    """Run a command and return True if successful."""
    try:
        result = subprocess.run(
            command.split(),
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            print(f"✓ {description}")
            return True
        else:
            print(f"✗ {description}: {result.stderr.strip()}")
            return False
    except subprocess.TimeoutExpired:
        print(f"✗ {description}: Command timed out")
        return False
    except FileNotFoundError:
        print(f"✗ {description}: Command not found")
        return False


def check_file_exists(file_path: str, description: str) -> bool:
    """Check if a file exists."""
    if Path(file_path).exists():
        print(f"✓ {description}")
        return True
    else:
        print(f"✗ {description}: File not found")
        return False


def main():
    """Main validation function."""
    print("Validating Code Review Assistant development environment...\n")
    
    checks = []
    
    # Check Python version
    checks.append(run_command("python --version", "Python installation"))
    
    # Check uv
    checks.append(run_command("uv --version", "uv installation"))
    
    # Check required files
    checks.append(check_file_exists("pyproject.toml", "Project configuration"))
    checks.append(check_file_exists(".env", "Environment configuration"))
    checks.append(check_file_exists("src/main.py", "Main application file"))
    
    # Check development tools
    checks.append(run_command("black --version", "Black formatter"))
    checks.append(run_command("ruff --version", "Ruff linter"))
    checks.append(run_command("mypy --version", "MyPy type checker"))
    checks.append(run_command("pytest --version", "Pytest testing framework"))
    checks.append(run_command("pre-commit --version", "Pre-commit hooks"))
    
    # Check static analysis tools
    checks.append(run_command("bandit --version", "Bandit security scanner"))
    
    # Check optional tools
    run_command("docker --version", "Docker (optional)")
    run_command("docker-compose --version", "Docker Compose (optional)")
    
    # Summary
    passed = sum(checks)
    total = len(checks)
    
    print(f"\nValidation Summary: {passed}/{total} checks passed")
    
    if passed == total:
        print("🎉 All checks passed! Development environment is ready.")
        return 0
    else:
        print("⚠️  Some checks failed. Please review the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())