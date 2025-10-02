# Multi-Project Devcontainer Setup

This directory contains the devcontainer configuration for the multi-project development environment.

## Services

### Core Services (Always Available)

- **PostgreSQL** (`postgres`): Database server with multiple project databases
  - Port: 5432
  - Default database: `devdb`
  - Project databases: `code_review_assistant`, `linkedin_project`
  - Credentials: `devuser` / `devpass`

- **Redis** (`redis`): Cache and session storage
  - Port: 6379
  - Multiple databases for project isolation (0, 1, 2)

### Project-Specific Services

- **Code Review Assistant** (`code-review-api`): 
  - Profile: `code-review`
  - Port: 8000
  - Database: `code_review_assistant`
  - Redis DB: 1

- **LinkedIn Project** (`linkedin-api`):
  - Profile: `linkedin`
  - Port: 8001
  - Database: `linkedin_project`
  - Redis DB: 2

## Service Management

Use the provided scripts to manage services:

### Linux/macOS
```bash
# Start core services only
./scripts/docker-services.sh start

# Start specific project
./scripts/docker-services.sh start code-review
./scripts/docker-services.sh start linkedin

# Start all services
./scripts/docker-services.sh start all

# View logs
./scripts/docker-services.sh logs postgres
./scripts/docker-services.sh logs

# Stop services
./scripts/docker-services.sh stop
```

### Windows (PowerShell)
```powershell
# Start core services only
.\scripts\docker-services.ps1 start

# Start specific project
.\scripts\docker-services.ps1 start code-review
.\scripts\docker-services.ps1 start linkedin

# Start all services
.\scripts\docker-services.ps1 start all

# View logs
.\scripts\docker-services.ps1 logs postgres
.\scripts\docker-services.ps1 logs

# Stop services
.\scripts\docker-services.ps1 stop
```

## Service Isolation

### Network Isolation
- All services run on the `dev-network` bridge network
- Services can communicate using service names as hostnames
- External access is controlled through port forwarding

### Database Isolation
- Each project gets its own PostgreSQL database
- Database names follow the pattern: `{project_name}_database`
- All projects share the same PostgreSQL instance but have separate schemas

### Redis Isolation
- Each project uses a different Redis database number:
  - Database 0: Shared/general use
  - Database 1: Code Review Assistant
  - Database 2: LinkedIn Project
  - Database 3+: Future projects

### Volume Management
- **postgres-data**: Persistent PostgreSQL data
- **redis-data**: Persistent Redis data with AOF enabled
- **vscode-extensions**: VS Code extension cache
- Project source code is mounted from the host

## Environment Variables

### Core Service Variables
```bash
DATABASE_URL=postgresql://devuser:devpass@postgres:5432/devdb
REDIS_URL=redis://redis:6379/0
```

### Project-Specific Variables
Each project service gets its own database URL and Redis database:

**Code Review Assistant:**
```bash
DATABASE_URL=postgresql://devuser:devpass@postgres:5432/code_review_assistant
REDIS_URL=redis://redis:6379/1
```

**LinkedIn Project:**
```bash
DATABASE_URL=postgresql://devuser:devpass@postgres:5432/linkedin_project
REDIS_URL=redis://redis:6379/2
```

## Health Checks

Both PostgreSQL and Redis services include health checks:
- **PostgreSQL**: `pg_isready` command every 30 seconds
- **Redis**: `redis-cli ping` command every 30 seconds

Project services depend on healthy core services before starting.

## Profiles

Docker Compose profiles are used for project isolation:
- No profile: Core services only (postgres, redis)
- `code-review`: Core services + Code Review Assistant
- `linkedin`: Core services + LinkedIn Project

## Troubleshooting

### Service Won't Start
1. Check if ports are already in use: `netstat -an | grep :5432`
2. View service logs: `docker-compose logs [service-name]`
3. Restart services: `docker-compose restart [service-name]`

### Database Connection Issues
1. Verify PostgreSQL is healthy: `docker-compose ps postgres`
2. Test connection: `docker-compose exec postgres psql -U devuser -d devdb`
3. Check database exists: `\l` in psql

### Redis Connection Issues
1. Verify Redis is healthy: `docker-compose ps redis`
2. Test connection: `docker-compose exec redis redis-cli ping`
3. Check Redis info: `docker-compose exec redis redis-cli info`

### Performance Issues
1. Check resource usage: `docker stats`
2. Optimize volume mounts for your platform
3. Consider adjusting memory limits in docker-compose.yml

## Adding New Projects

To add a new project:

1. Add a new service to `docker-compose.yml` with a unique profile
2. Create project-specific database in the init script
3. Assign a unique Redis database number
4. Update the service management scripts
5. Document the new service in this README