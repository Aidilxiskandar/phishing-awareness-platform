# PhishGuard developer tasks. Run `make help` for the list.
.PHONY: help install run test cov lint fmt seed docker-build docker-up docker-down

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Create venv and install dev dependencies
	python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt

run: ## Run the app locally with autoreload
	uvicorn app.main:app --reload

test: ## Run the test suite
	pytest

cov: ## Run tests with a coverage report
	pytest --cov=app --cov-report=term-missing

lint: ## Lint with ruff
	ruff check app tests scripts

fmt: ## Auto-fix lint issues
	ruff check --fix app tests

docker-build: ## Build the Docker image
	docker build -t phishguard .

docker-up: ## Build and run via docker compose
	docker compose up --build

docker-down: ## Stop docker compose
	docker compose down

smoke: ## Real-browser smoke test against a running server (BASE=http://127.0.0.1:8765)
	node scripts/browser_smoke.mjs $${BASE:-http://127.0.0.1:8765}
