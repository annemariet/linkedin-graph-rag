.PHONY: help install install-dev test test-cov lint format clean run docker-build docker-up docker-down

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install production dependencies
	uv sync

install-dev: ## Install development dependencies
	uv sync --all-extras
	pre-commit install

test: ## Run tests
	pytest

test-cov: ## Run tests with coverage
	pytest --cov=src --cov-report=html --cov-report=term

lint: ## Run linting tools
	ruff check src tests
	mypy src
	bandit -r src

format: ## Format code
	black src tests
	ruff check --fix src tests

clean: ## Clean up build artifacts
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

run: ## Run the development server
	uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

docker-build: ## Build Docker image
	docker-compose build

docker-up: ## Start services with Docker Compose
	docker-compose up -d

docker-down: ## Stop services with Docker Compose
	docker-compose down

docker-logs: ## View Docker logs
	docker-compose logs -f