.PHONY: help install lint typecheck test test-unit test-integration format up down build migrate seed clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install all dependencies
	pip install -e ".[dev]"

lint: ## Run ruff linter
	ruff check app tests

typecheck: ## Run mypy type checker
	mypy app

test: ## Run all tests
	pytest

test-unit: ## Run unit tests only
	pytest -m unit

test-integration: ## Run integration tests only
	pytest -m integration

format: ## Format code with ruff
	ruff format app tests
	ruff check --fix app tests

up: ## Start development services
	docker compose up -d

down: ## Stop development services
	docker compose down

build: ## Build Docker image
	docker compose build

migrate: ## Run database migrations
	alembic upgrade head

seed: ## Run seed script
	python scripts/seed.py

clean: ## Clean build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf dist build *.egg-info htmlcov .coverage

check: lint typecheck test ## Run all checks (lint + typecheck + test)
