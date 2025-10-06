#!/usr/bin/env python3
"""
Consolidated Project Management Script
Handles project discovery, validation, secrets, and devcontainer management.
"""

import json
import os
import sys
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class ProjectManager:
    """Consolidated project management functionality."""
    
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.projects_dir = workspace_root / "projects"
        self.workspace_config_path = self.projects_dir / "workspace.json"
    
    def discover_projects(self) -> List[Dict]:
        """Discover all projects in the workspace."""
        projects = []
        
        if not self.projects_dir.exists():
            return projects
        
        for item in self.projects_dir.iterdir():
            if item.is_dir() and item.name not in ['.', '..']:
                project_info = self._analyze_project(item)
                if project_info:
                    projects.append(project_info)
        
        return sorted(projects, key=lambda x: x['name'])
    
    def _analyze_project(self, project_path: Path) -> Optional[Dict]:
        """Analyze a single project directory."""
        project_info = {
            'name': project_path.name,
            'path': str(project_path.relative_to(self.workspace_root)),
            'type': self._detect_project_type(project_path),
            'has_devcontainer': (project_path / ".devcontainer").exists(),
            'has_env_example': (project_path / ".env.example").exists(),
            'has_env_local': (project_path / ".env.local").exists(),
            'has_project_config': (project_path / "project.json").exists(),
            'validation_errors': []
        }
        
        # Validate project structure
        project_info['validation_errors'] = self._validate_project_structure(project_path)
        
        return project_info
    
    def _validate_project_structure(self, project_path: Path) -> List[str]:
        """Validate project structure and configuration."""
        errors = []
        
        # Check for project.json
        project_json = project_path / "project.json"
        if project_json.exists():
            try:
                with open(project_json) as f:
                    config = json.load(f)
                    required_fields = ["name", "type", "scripts"]
                    for field in required_fields:
                        if field not in config:
                            errors.append(f"Missing required field '{field}' in project.json")
            except json.JSONDecodeError as e:
                errors.append(f"Invalid JSON in project.json: {e}")
        
        # Check for essential files
        if not (project_path / ".env.example").exists():
            errors.append("Missing .env.example")
        
        if not (project_path / ".devcontainer").exists():
            errors.append("Missing .devcontainer directory")
        elif not (project_path / ".devcontainer" / "devcontainer.json").exists():
            errors.append("Missing devcontainer.json")
        
        return errors
    
    def _detect_project_type(self, project_path: Path) -> str:
        """Detect project type based on files present."""
        if (project_path / "pyproject.toml").exists():
            return "python"
        elif (project_path / "package.json").exists():
            return "node"
        elif (project_path / "Cargo.toml").exists():
            return "rust"
        elif (project_path / "go.mod").exists():
            return "go"
        else:
            return "unknown"
    
    def validate_secrets(self, project_name: str = None) -> bool:
        """Validate project secrets."""
        projects = [project_name] if project_name else [p['name'] for p in self.discover_projects()]
        all_valid = True
        
        for proj_name in projects:
            project_path = self.projects_dir / proj_name
            env_example = project_path / ".env.example"
            env_local = project_path / ".env.local"
            
            print(f"Validating secrets for: {proj_name}")
            
            if not env_example.exists():
                print(f"  ❌ Missing .env.example")
                all_valid = False
                continue
            
            if not env_local.exists():
                print(f"  ❌ Missing .env.local (run setup-secrets)")
                all_valid = False
                continue
            
            # Load environment variables
            env_vars = self._load_env_file(env_local)
            example_vars = self._load_env_file(env_example)
            
            missing_vars = []
            placeholder_vars = []
            
            for var_name, example_value in example_vars.items():
                actual_value = env_vars.get(var_name, "")
                
                if not actual_value:
                    missing_vars.append(var_name)
                elif self._is_placeholder(actual_value) and not var_name.startswith("TEST_"):
                    placeholder_vars.append(var_name)
            
            if missing_vars:
                print(f"  ❌ Missing variables: {', '.join(missing_vars)}")
                all_valid = False
            
            if placeholder_vars:
                print(f"  ⚠️  Placeholder values: {', '.join(placeholder_vars)}")
                all_valid = False
            
            if not missing_vars and not placeholder_vars:
                print(f"  ✅ All secrets configured")
        
        return all_valid
    
    def setup_secrets(self, project_name: str = None):
        """Interactive secret setup."""
        projects = [project_name] if project_name else [p['name'] for p in self.discover_projects()]
        
        for proj_name in projects:
            project_path = self.projects_dir / proj_name
            env_example = project_path / ".env.example"
            env_local = project_path / ".env.local"
            
            print(f"\nSetting up secrets for: {proj_name}")
            
            if not env_example.exists():
                print(f"  ❌ No .env.example found")
                continue
            
            # Create .env.local from example if it doesn't exist
            if not env_local.exists():
                print(f"  Creating .env.local from .env.example")
                env_local.write_text(env_example.read_text())
            
            # Load current values
            env_vars = self._load_env_file(env_local)
            example_vars = self._load_env_file(env_example)
            updated = False
            
            for var_name, example_value in example_vars.items():
                current_value = env_vars.get(var_name, "")
                
                if self._is_placeholder(current_value):
                    print(f"  {var_name} (current: {current_value})")
                    new_value = input(f"    Enter new value (or press Enter to keep): ").strip()
                    
                    if new_value:
                        env_vars[var_name] = new_value
                        updated = True
                        print(f"    ✅ Updated {var_name}")
            
            if updated:
                self._save_env_file(env_local, env_vars)
                print(f"  ✅ Secrets updated for {proj_name}")
            else:
                print(f"  ℹ️  No changes needed for {proj_name}")
    
    def _load_env_file(self, env_file: Path) -> Dict[str, str]:
        """Load environment variables from file."""
        env_vars = {}
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()
        return env_vars
    
    def _save_env_file(self, env_file: Path, env_vars: Dict[str, str]):
        """Save environment variables to file."""
        lines = []
        for key, value in env_vars.items():
            lines.append(f"{key}={value}")
        env_file.write_text('\n'.join(lines) + '\n')
    
    def _is_placeholder(self, value: str) -> bool:
        """Check if value looks like a placeholder."""
        placeholders = [
            'your-', 'change-in-production', 'test-', 'password', 'secret',
            'replace-me', 'todo', 'fixme', 'example'
        ]
        return any(placeholder in value.lower() for placeholder in placeholders)
    
    def check_docker(self) -> Tuple[bool, str]:
        """Check if Docker is available."""
        try:
            result = subprocess.run(['docker', 'info'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return True, "Docker is running"
            else:
                return False, f"Docker error: {result.stderr}"
        except subprocess.TimeoutExpired:
            return False, "Docker command timed out"
        except FileNotFoundError:
            return False, "Docker not found in PATH"
        except Exception as e:
            return False, f"Docker check failed: {e}"
    
    def start_project(self, project_name: str, mode: str = "code"):
        """Start a project devcontainer."""
        project_path = self.projects_dir / project_name
        
        if not project_path.exists():
            print(f"❌ Project '{project_name}' not found")
            return False
        
        if not (project_path / ".devcontainer").exists():
            print(f"❌ No devcontainer configuration found for '{project_name}'")
            return False
        
        print(f"Starting devcontainer for: {project_name}")
        
        # Validate secrets first
        if not self.validate_secrets(project_name):
            print("⚠️  Secret validation failed, but continuing...")
        
        if mode == "code":
            try:
                # Try to open in VS Code
                subprocess.run(['code', str(project_path)], check=True)
                print(f"✅ Opened {project_name} in VS Code")
                print("   Use Command Palette -> 'Dev Containers: Reopen in Container'")
                return True
            except (subprocess.CalledProcessError, FileNotFoundError):
                print("❌ VS Code not available, try installing VS Code")
                return False
        else:
            print("❌ Only VS Code mode is supported on Windows")
            return False
    
    def run_project_script(self, project_name: str, script_name: str = "dev") -> bool:
        """Run a project script using its configuration."""
        project_path = self.projects_dir / project_name
        project_json = project_path / "project.json"
        
        if not project_path.exists():
            print(f"❌ Project '{project_name}' not found")
            return False
        
        if not project_json.exists():
            print(f"❌ No project.json found for '{project_name}'")
            return False
        
        try:
            with open(project_json) as f:
                config = json.load(f)
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON in project.json: {e}")
            return False
        
        scripts = config.get("scripts", {})
        if script_name not in scripts:
            print(f"❌ Script '{script_name}' not found")
            print(f"Available scripts: {', '.join(scripts.keys())}")
            return False
        
        command = scripts[script_name]
        print(f"Running: {command}")
        
        try:
            result = subprocess.run(command, shell=True, cwd=project_path)
            return result.returncode == 0
        except KeyboardInterrupt:
            print("\nInterrupted by user")
            return False
        except Exception as e:
            print(f"❌ Failed to run command: {e}")
            return False
    
    def validate_all_projects(self) -> bool:
        """Validate all projects in the workspace."""
        projects = self.discover_projects()
        all_valid = True
        
        print("Validating all projects...\n")
        
        for project in projects:
            print(f"Validating: {project['name']}")
            
            if project['validation_errors']:
                print(f"  ❌ Errors found:")
                for error in project['validation_errors']:
                    print(f"    - {error}")
                all_valid = False
            else:
                print(f"  ✅ Project structure valid")
        
        return all_valid
    
    def list_projects(self):
        """List all projects with status."""
        projects = self.discover_projects()
        
        if not projects:
            print("No projects found")
            return
        
        print(f"Found {len(projects)} projects:\n")
        
        # Print header
        print(f"{'Name':<25} {'Type':<10} {'DevContainer':<12} {'Secrets':<10} {'Valid':<8}")
        print("-" * 70)
        
        for project in projects:
            name = project['name']
            proj_type = project['type']
            devcontainer = "✅" if project['has_devcontainer'] else "❌"
            valid = "✅" if not project['validation_errors'] else "❌"
            
            # Check secrets status
            if not project['has_env_example']:
                secrets = "No template"
            elif not project['has_env_local']:
                secrets = "Not setup"
            else:
                # Quick validation
                project_path = self.projects_dir / name
                env_vars = self._load_env_file(project_path / ".env.local")
                example_vars = self._load_env_file(project_path / ".env.example")
                
                has_placeholders = any(
                    self._is_placeholder(env_vars.get(var, ""))
                    for var in example_vars.keys()
                    if not var.startswith("TEST_")
                )
                
                secrets = "⚠️  Needs setup" if has_placeholders else "✅"
            
            print(f"{name:<25} {proj_type:<10} {devcontainer:<12} {secrets:<10} {valid:<8}")
            
            # Show validation errors if any
            if project['validation_errors']:
                for error in project['validation_errors']:
                    print(f"  ⚠️  {error}")
        
        # Show Docker status
        docker_ok, docker_msg = self.check_docker()
        print(f"\nDocker Status: {docker_msg}")


def main():
    """Main function."""
    workspace_root = Path(__file__).parent.parent
    manager = ProjectManager(workspace_root)
    
    if len(sys.argv) < 2:
        print("Usage: python manage-projects.py <command> [options]")
        print("\nCommands:")
        print("  list                    List all projects")
        print("  validate                Validate all project configurations")
        print("  validate-secrets [project]  Validate project secrets")
        print("  setup-secrets [project]     Setup project secrets interactively")
        print("  start <project>         Start project in VS Code")
        print("  run <project> [script]  Run project script (default: dev)")
        print("  docker                  Check Docker status")
        print("\nExamples:")
        print("  python manage-projects.py list")
        print("  python manage-projects.py validate")
        print("  python manage-projects.py setup-secrets")
        print("  python manage-projects.py start code-review-assistant")
        print("  python manage-projects.py run linkedin-api-client test")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "list":
        manager.list_projects()
    
    elif command == "validate":
        success = manager.validate_all_projects()
        sys.exit(0 if success else 1)
    
    elif command == "validate-secrets":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        success = manager.validate_secrets(project)
        sys.exit(0 if success else 1)
    
    elif command == "setup-secrets":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        manager.setup_secrets(project)
    
    elif command == "start":
        if len(sys.argv) < 3:
            print("Usage: python manage-projects.py start <project-name>")
            sys.exit(1)
        
        project = sys.argv[2]
        success = manager.start_project(project)
        sys.exit(0 if success else 1)
    
    elif command == "run":
        if len(sys.argv) < 3:
            print("Usage: python manage-projects.py run <project-name> [script-name]")
            sys.exit(1)
        
        project = sys.argv[2]
        script = sys.argv[3] if len(sys.argv) > 3 else "dev"
        success = manager.run_project_script(project, script)
        sys.exit(0 if success else 1)
    
    elif command == "docker":
        docker_ok, docker_msg = manager.check_docker()
        print(f"Docker Status: {docker_msg}")
        sys.exit(0 if docker_ok else 1)
    
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()