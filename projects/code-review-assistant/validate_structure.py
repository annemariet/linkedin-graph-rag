#!/usr/bin/env python3
"""
Simple validation script to check project structure.
"""

from pathlib import Path


def check_structure():
    """Check if the project structure is correct."""
    required_files = [
        "pyproject.toml",
        "README.md",
        "Dockerfile",
        "docker-compose.yml",
        ".env.example",
        ".pre-commit-config.yaml",
        "Makefile",
        "src/__init__.py",
        "src/main.py",
        "src/core/__init__.py",
        "src/core/config.py",
        "src/core/database.py",
        "src/core/celery_app.py",
        "src/core/tasks.py",
        "src/core/logging.py",
        "src/core/middleware.py",
        "src/core/exceptions.py",
        "src/core/utils.py",
        "src/api/__init__.py",
        "src/api/routes/__init__.py",
        "src/api/routes/health.py",
        "src/models/__init__.py",
        "src/models/base.py",
        "src/models/submission.py",
        "src/models/analysis.py",
        "tests/__init__.py",
        "tests/conftest.py",
        "tests/test_main.py",
        "scripts/setup-dev.sh",
        "scripts/setup-dev.bat",
        "scripts/validate-setup.py",
    ]
    
    required_dirs = [
        "src",
        "src/core",
        "src/api",
        "src/api/routes",
        "src/models",
        "tests",
        "scripts",
    ]
    
    print("Checking project structure...")
    
    # Check directories
    missing_dirs = []
    for dir_path in required_dirs:
        if not Path(dir_path).is_dir():
            missing_dirs.append(dir_path)
        else:
            print(f"✓ Directory: {dir_path}")
    
    # Check files
    missing_files = []
    for file_path in required_files:
        if not Path(file_path).is_file():
            missing_files.append(file_path)
        else:
            print(f"✓ File: {file_path}")
    
    # Summary
    if missing_dirs:
        print(f"\n❌ Missing directories: {', '.join(missing_dirs)}")
    
    if missing_files:
        print(f"\n❌ Missing files: {', '.join(missing_files)}")
    
    if not missing_dirs and not missing_files:
        print("\n🎉 Project structure is complete!")
        return True
    else:
        print(f"\n⚠️  Project structure incomplete. Missing {len(missing_dirs)} directories and {len(missing_files)} files.")
        return False


if __name__ == "__main__":
    check_structure()