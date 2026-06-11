SHELL := /usr/bin/env bash

COMPOSE_ENV_FILE := $(if $(wildcard .env),--env-file .env,)
COMPOSE_DEV := docker compose $(COMPOSE_ENV_FILE) -f infra/compose/docker-compose.dev.yml
COMPOSE_PROD := docker compose $(COMPOSE_ENV_FILE) -f infra/compose/docker-compose.prod.yml
PNPM := corepack pnpm

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show available commands
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "%-18s %s\n", $$1, $$2}'

.PHONY: bootstrap
bootstrap: ## Check required local tools
	@command -v uv >/dev/null || { echo "uv is required"; exit 1; }
	@command -v node >/dev/null || { echo "node is required"; exit 1; }
	@command -v corepack >/dev/null || { echo "corepack is required"; exit 1; }
	@$(PNPM) --version >/dev/null
	@command -v docker >/dev/null || { echo "docker is required"; exit 1; }
	@docker compose version >/dev/null
	@echo "Bootstrap checks passed"

.PHONY: install
install: ## Install backend and frontend dependencies
	uv sync
	cd frontend && $(PNPM) install

.PHONY: lint
lint: ## Run backend and frontend lint checks
	uv run ruff check .
	uv run mypy backend
	cd frontend && $(PNPM) lint

.PHONY: test
test: ## Run backend and frontend tests
	uv run pytest -q
	cd frontend && $(PNPM) test

.PHONY: eval
eval: ## Run local AI coach eval samples
	uv run python -m backend.app.evals.coach_eval_runner

.PHONY: build
build: ## Run local verification and build frontend assets
	uv run ruff check .
	uv run mypy backend
	uv run pytest -q
	cd frontend && $(PNPM) lint
	cd frontend && $(PNPM) test
	cd frontend && $(PNPM) build

.PHONY: docker-build
docker-build: ## Build development Docker images
	$(COMPOSE_DEV) build

.PHONY: up
up: ## Start development Docker stack
	$(COMPOSE_DEV) up --build -d

.PHONY: down
down: ## Stop development Docker stack
	$(COMPOSE_DEV) down

.PHONY: logs
logs: ## Follow development Docker logs
	$(COMPOSE_DEV) logs -f

.PHONY: db-migrate
db-migrate: ## Run Alembic migrations in backend container
	$(COMPOSE_DEV) exec backend uv run --no-sync alembic upgrade head

.PHONY: prepare-problem-seed
prepare-problem-seed: ## Prepare local problem seed files from ignored source data
	uv run python scripts/prepare_problem_seed.py --source data/sources/leetcode-problemset --output data/seed

.PHONY: db-seed
db-seed: ## Import generated problem seed data into the database
	uv run python -m backend.app.cli.problem_seed

.PHONY: smoke
smoke: ## Run development smoke checks against running services
	COMPOSE_FILE=infra/compose/docker-compose.dev.yml ./scripts/smoke_all.sh

.PHONY: package
package: ## Build packageable Docker images for current foundation stage
	$(COMPOSE_PROD) build

.PHONY: clean
clean: ## Remove local build and cache artifacts
	rm -rf frontend/dist
	rm -rf .pytest_cache .ruff_cache .mypy_cache
	find backend tests demo -type d -name __pycache__ -prune -exec rm -rf {} +
