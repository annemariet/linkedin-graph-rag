# Multi-Project Devcontainer Setup Design

## Overview

This design transforms the current single-project workspace into a multi-project development environment using devcontainers and Docker. The solution provides consistent cross-platform development experiences while maintaining secure secret management and efficient project isolation.

The architecture follows devcontainer best practices with a monorepo structure that supports multiple independent projects, each with their own configurations while sharing common development tooling and infrastructure.

## Architecture

### High-Level Structure

```
workspace/
├── .devcontainer/                 # Devcontainer configuration
│   ├── devcontainer.json         # Primary devcontainer config
│   ├── Dockerfile                # Development environment image
│   └── docker-compose.yml        # Multi-service development stack
├── projects/                     # All projects organized here
│   ├── code-review-assistant/    # Existing project (moved from root)
│   │   ├── src/
│   │   ├── tests/
│   │   ├── pyproject.toml
│   │   └── .env.example
│   ├── linkedin/                 # Existing project (moved from root)
│   │   └── [existing linkedin project structure]
│   └── [future-projects]/        # Additional projects
├── scripts/                      # Shared development scripts
├── .github/                      # GitHub workflows and templates
│   └── workflows/
└── README.md                     # Workspace overview
```

### Devcontainer Architecture

The devcontainer setup uses a multi-stage approach:

1. **Base Development Image**: Contains common tools (Python, Node.js, Git, Docker CLI)
2. **Project-Specific Extensions**: Each project can extend the base with specific requirements
3. **Service Integration**: Docker Compose manages databases, Redis, and other services
4. **Volume Management**: Separate volumes for each project's data and shared caches

## Components and Interfaces

### 1. Devcontainer Configuration

**Primary Configuration** (`.devcontainer/devcontainer.json`):
- Base image definition with multi-language support
- VS Code extensions for Python, Docker, Git, testing
- Port forwarding for web services and databases
- Environment variable management
- Post-creation scripts for setup

**Docker Compose Integration**:
- Development services (PostgreSQL, Redis, etc.)
- Project-specific service definitions
- Network isolation between projects
- Volume management for persistence and caching

### 2. Project Organization System

**Project Configuration Files**:
Each project will have a simple `project.json` configuration file:

```json
{
  "name": "project-name",
  "type": "python|node|mixed",
  "services": ["postgres", "redis"],
  "ports": [8000, 8001],
  "scripts": {
    "dev": "command to start development",
    "test": "command to run tests",
    "build": "command to build project"
  }
}
```

**File Organization**:
- `projects/{project-name}/project.json` - Project configuration
- `projects/{project-name}/.env.example` - Environment template
- `projects/{project-name}/.env.local` - Local secrets (git-ignored)

### 3. Secret Management System

**Environment Variable Hierarchy**:
1. `.env.local` (git-ignored, machine-specific secrets)
2. `.env.example` (template, committed to git)
3. Project-specific environment files
4. Devcontainer environment variables

**AI Tool Security Measures**:
- All secret files (`.env.local`, `.env`) added to `.gitignore`
- Secret files added to `.kiroignore` to prevent AI tool access
- Encrypted secret storage option for sensitive environments
- Clear separation between example templates and actual secrets

**Secret Management Interface**:
```bash
# Setup script interface
./scripts/setup-secrets.sh [project-name]
./scripts/validate-secrets.sh [project-name]
```

### 4. Development Tooling Integration

**Code Quality Pipeline**:
- Pre-commit hooks with project-aware configuration
- Shared linting and formatting rules with project overrides
- Automated testing with project isolation
- Security scanning across all projects

**Testing Framework**:
- Project-specific test runners
- Shared testing utilities and fixtures
- Cross-project integration testing capabilities
- TDD workflow support with fast feedback loops

## Configuration Files

### Workspace-Level Configuration

**`.devcontainer/devcontainer.json`** - Main devcontainer configuration
**`.devcontainer/docker-compose.yml`** - Service definitions
**`scripts/`** - Shared setup and utility scripts

### Project-Level Configuration

**`projects/{name}/project.json`** - Project metadata and scripts
**`projects/{name}/.env.example`** - Environment variable template
**`projects/{name}/.env.local`** - Local environment variables (git-ignored)

## Error Handling

### Environment Setup Errors

1. **Missing Dependencies**: Clear error messages with installation instructions
2. **Port Conflicts**: Automatic port detection and alternative suggestions
3. **Service Connection Failures**: Retry logic with fallback configurations
4. **Permission Issues**: Platform-specific guidance for Docker/WSL setup

### Project Management Errors

1. **Invalid Project Structure**: Validation with auto-fix suggestions
2. **Configuration Conflicts**: Merge conflict resolution strategies
3. **Missing Secrets**: Interactive secret setup with secure prompts
4. **Service Startup Failures**: Diagnostic information and recovery steps

### Cross-Platform Compatibility

1. **Path Handling**: Consistent path resolution across Windows/Unix systems
2. **Line Ending Issues**: Git configuration and editor settings
3. **Permission Mapping**: Docker volume permission handling for different hosts
4. **Shell Script Compatibility**: PowerShell and Bash script alternatives

## Testing Strategy

### Development Environment Testing

1. **Container Build Tests**: Verify devcontainer builds successfully on all platforms
2. **Service Integration Tests**: Ensure all services start and communicate properly
3. **Cross-Platform Tests**: Validate functionality on Windows/WSL, Mac, and Linux
4. **Performance Tests**: Measure container startup times and resource usage

### Project Isolation Testing

1. **Dependency Isolation**: Verify projects don't interfere with each other
2. **Port Conflict Resolution**: Test automatic port assignment
3. **Environment Variable Isolation**: Ensure secrets don't leak between projects
4. **Service Namespace Testing**: Verify database and cache isolation

### Secret Management Testing

1. **Template Generation**: Verify .env.example files are generated correctly
2. **Validation Scripts**: Test environment variable validation
3. **Security Tests**: Ensure secrets are never committed to git and are excluded from AI tool access
4. **Cross-Machine Setup**: Test secret setup process on fresh machines
5. **AI Tool Isolation**: Verify .kiroignore prevents AI tools from reading secret files

### Code Quality Integration Testing

1. **Pre-commit Hook Tests**: Verify hooks work across all projects
2. **Linting Integration**: Test project-specific and shared linting rules
3. **Test Runner Integration**: Verify TDD workflow with fast feedback
4. **CI/CD Integration**: Test GitHub Actions with multi-project setup

## Implementation Phases

### Phase 1: Core Infrastructure
- Devcontainer base configuration
- Docker Compose service setup
- Basic project organization structure
- Secret management foundation

### Phase 2: Project Migration
- Move existing code-review-assistant to projects/ structure
- Move existing linkedin project to projects/ structure
- Implement project configuration system
- Create setup and validation scripts
- Test cross-platform compatibility

### Phase 3: Development Tooling
- Integrate code quality tools
- Set up pre-commit hooks
- Implement TDD workflow support
- Create project templates

### Phase 4: Documentation and Optimization
- Comprehensive documentation
- Performance optimization
- GitHub integration and workflows