# Docker Compose service management script for multi-project development (PowerShell)

param(
    [Parameter(Position=0)]
    [string]$Command = "help",
    
    [Parameter(Position=1)]
    [string]$Project = ""
)

# Get script directory and project root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$ComposeFile = Join-Path $ProjectRoot ".devcontainer\docker-compose.yml"

# Function to print colored output
function Write-Status {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Blue
}

function Write-Success {
    param([string]$Message)
    Write-Host "[SUCCESS] $Message" -ForegroundColor Green
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[WARNING] $Message" -ForegroundColor Yellow
}

function Write-Error {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

# Function to show usage
function Show-Usage {
    Write-Host "Usage: .\docker-services.ps1 [COMMAND] [PROJECT]"
    Write-Host ""
    Write-Host "Commands:"
    Write-Host "  start [PROJECT]     Start services (optionally for specific project)"
    Write-Host "  stop [PROJECT]      Stop services (optionally for specific project)"
    Write-Host "  restart [PROJECT]   Restart services (optionally for specific project)"
    Write-Host "  logs [PROJECT]      Show logs (optionally for specific project)"
    Write-Host "  status              Show status of all services"
    Write-Host "  clean               Clean up all containers and volumes"
    Write-Host "  help                Show this help message"
    Write-Host ""
    Write-Host "Projects:"
    Write-Host "  code-review         Code Review Assistant project"
    Write-Host "  linkedin            LinkedIn project"
    Write-Host "  all                 All projects (default)"
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  .\docker-services.ps1 start                    # Start core services (postgres, redis)"
    Write-Host "  .\docker-services.ps1 start code-review        # Start core services + code-review project"
    Write-Host "  .\docker-services.ps1 logs postgres            # Show postgres logs"
    Write-Host "  .\docker-services.ps1 stop                     # Stop all services"
}

# Function to start services
function Start-Services {
    param([string]$ProjectName = "")
    
    Write-Status "Starting Docker Compose services..."
    
    if ([string]::IsNullOrEmpty($ProjectName)) {
        # Start core services only
        docker-compose -f $ComposeFile up -d postgres redis
        Write-Success "Core services (PostgreSQL, Redis) started"
    }
    elseif ($ProjectName -eq "all") {
        # Start all services
        docker-compose -f $ComposeFile --profile code-review --profile linkedin up -d
        Write-Success "All services started"
    }
    elseif ($ProjectName -eq "code-review") {
        # Start core services + code-review
        docker-compose -f $ComposeFile --profile code-review up -d
        Write-Success "Core services + Code Review Assistant started"
    }
    elseif ($ProjectName -eq "linkedin") {
        # Start core services + linkedin
        docker-compose -f $ComposeFile --profile linkedin up -d
        Write-Success "Core services + LinkedIn project started"
    }
    else {
        Write-Error "Unknown project: $ProjectName"
        Show-Usage
        exit 1
    }
}

# Function to stop services
function Stop-Services {
    param([string]$ProjectName = "")
    
    Write-Status "Stopping Docker Compose services..."
    
    if ([string]::IsNullOrEmpty($ProjectName) -or $ProjectName -eq "all") {
        docker-compose -f $ComposeFile --profile code-review --profile linkedin down
        Write-Success "All services stopped"
    }
    elseif ($ProjectName -eq "code-review") {
        docker-compose -f $ComposeFile --profile code-review stop code-review-api
        Write-Success "Code Review Assistant services stopped"
    }
    elseif ($ProjectName -eq "linkedin") {
        docker-compose -f $ComposeFile --profile linkedin stop linkedin-api
        Write-Success "LinkedIn project services stopped"
    }
    else {
        Write-Error "Unknown project: $ProjectName"
        Show-Usage
        exit 1
    }
}

# Function to restart services
function Restart-Services {
    param([string]$ProjectName = "")
    Write-Status "Restarting services..."
    Stop-Services $ProjectName
    Start-Sleep -Seconds 2
    Start-Services $ProjectName
}

# Function to show logs
function Show-Logs {
    param([string]$ServiceName = "")
    
    if ([string]::IsNullOrEmpty($ServiceName)) {
        docker-compose -f $ComposeFile logs -f
    }
    else {
        docker-compose -f $ComposeFile logs -f $ServiceName
    }
}

# Function to show status
function Show-Status {
    Write-Status "Docker Compose services status:"
    docker-compose -f $ComposeFile ps
}

# Function to clean up
function Clean-Services {
    $response = Read-Host "This will remove all containers and volumes. Are you sure? (y/N)"
    if ($response -match "^[Yy]$") {
        Write-Status "Cleaning up Docker Compose services..."
        docker-compose -f $ComposeFile --profile code-review --profile linkedin down -v --remove-orphans
        docker system prune -f
        Write-Success "Cleanup completed"
    }
    else {
        Write-Status "Cleanup cancelled"
    }
}

# Main script logic
switch ($Command.ToLower()) {
    "start" {
        Start-Services $Project
    }
    "stop" {
        Stop-Services $Project
    }
    "restart" {
        Restart-Services $Project
    }
    "logs" {
        Show-Logs $Project
    }
    "status" {
        Show-Status
    }
    "clean" {
        Clean-Services
    }
    "help" {
        Show-Usage
    }
    default {
        Write-Error "Unknown command: $Command"
        Show-Usage
        exit 1
    }
}