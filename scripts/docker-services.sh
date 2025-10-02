#!/bin/bash

# Docker Compose service management script for multi-project development

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$PROJECT_ROOT/.devcontainer/docker-compose.yml"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [COMMAND] [PROJECT]"
    echo ""
    echo "Commands:"
    echo "  start [PROJECT]     Start services (optionally for specific project)"
    echo "  stop [PROJECT]      Stop services (optionally for specific project)"
    echo "  restart [PROJECT]   Restart services (optionally for specific project)"
    echo "  logs [PROJECT]      Show logs (optionally for specific project)"
    echo "  status              Show status of all services"
    echo "  clean               Clean up all containers and volumes"
    echo "  help                Show this help message"
    echo ""
    echo "Projects:"
    echo "  code-review         Code Review Assistant project"
    echo "  linkedin            LinkedIn project"
    echo "  all                 All projects (default)"
    echo ""
    echo "Examples:"
    echo "  $0 start                    # Start core services (postgres, redis)"
    echo "  $0 start code-review        # Start core services + code-review project"
    echo "  $0 logs postgres            # Show postgres logs"
    echo "  $0 stop                     # Stop all services"
}

# Function to start services
start_services() {
    local project=${1:-""}
    
    print_status "Starting Docker Compose services..."
    
    if [ -z "$project" ]; then
        # Start core services only
        docker-compose -f "$COMPOSE_FILE" up -d postgres redis
        print_success "Core services (PostgreSQL, Redis) started"
    elif [ "$project" = "all" ]; then
        # Start all services
        docker-compose -f "$COMPOSE_FILE" --profile code-review --profile linkedin up -d
        print_success "All services started"
    elif [ "$project" = "code-review" ]; then
        # Start core services + code-review
        docker-compose -f "$COMPOSE_FILE" --profile code-review up -d
        print_success "Core services + Code Review Assistant started"
    elif [ "$project" = "linkedin" ]; then
        # Start core services + linkedin
        docker-compose -f "$COMPOSE_FILE" --profile linkedin up -d
        print_success "Core services + LinkedIn project started"
    else
        print_error "Unknown project: $project"
        show_usage
        exit 1
    fi
}

# Function to stop services
stop_services() {
    local project=${1:-""}
    
    print_status "Stopping Docker Compose services..."
    
    if [ -z "$project" ] || [ "$project" = "all" ]; then
        docker-compose -f "$COMPOSE_FILE" --profile code-review --profile linkedin down
        print_success "All services stopped"
    elif [ "$project" = "code-review" ]; then
        docker-compose -f "$COMPOSE_FILE" --profile code-review stop code-review-api
        print_success "Code Review Assistant services stopped"
    elif [ "$project" = "linkedin" ]; then
        docker-compose -f "$COMPOSE_FILE" --profile linkedin stop linkedin-api
        print_success "LinkedIn project services stopped"
    else
        print_error "Unknown project: $project"
        show_usage
        exit 1
    fi
}

# Function to restart services
restart_services() {
    local project=${1:-""}
    print_status "Restarting services..."
    stop_services "$project"
    sleep 2
    start_services "$project"
}

# Function to show logs
show_logs() {
    local service=${1:-""}
    
    if [ -z "$service" ]; then
        docker-compose -f "$COMPOSE_FILE" logs -f
    else
        docker-compose -f "$COMPOSE_FILE" logs -f "$service"
    fi
}

# Function to show status
show_status() {
    print_status "Docker Compose services status:"
    docker-compose -f "$COMPOSE_FILE" ps
}

# Function to clean up
clean_services() {
    print_warning "This will remove all containers and volumes. Are you sure? (y/N)"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        print_status "Cleaning up Docker Compose services..."
        docker-compose -f "$COMPOSE_FILE" --profile code-review --profile linkedin down -v --remove-orphans
        docker system prune -f
        print_success "Cleanup completed"
    else
        print_status "Cleanup cancelled"
    fi
}

# Main script logic
case "${1:-help}" in
    start)
        start_services "${2:-}"
        ;;
    stop)
        stop_services "${2:-}"
        ;;
    restart)
        restart_services "${2:-}"
        ;;
    logs)
        show_logs "${2:-}"
        ;;
    status)
        show_status
        ;;
    clean)
        clean_services
        ;;
    help|--help|-h)
        show_usage
        ;;
    *)
        print_error "Unknown command: $1"
        show_usage
        exit 1
        ;;
esac