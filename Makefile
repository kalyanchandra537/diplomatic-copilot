.DEFAULT_GOAL := help

# Variables
AGENT_DIR := app

.PHONY: help install playground run test lint

help: ## Show available commands
	@echo "Available commands:"
	@echo "  make install    - Install dependencies"
	@echo "  make playground - Launch ADK web playground (Windows-safe)"
	@echo "  make run        - Run local web server (uvicorn)"
	@echo "  make test       - Run unit tests"
	@echo "  make lint       - Lint code with ruff"

install: ## Install all Python dependencies
	uv sync

playground: ## Launch ADK web playground at http://localhost:18081
	uv run adk web $(AGENT_DIR) --host 127.0.0.1 --port 18081 --reload_agents

run: ## Run local FastAPI web server
	uv run uvicorn app.agent_runtime_app:agent_runtime --host 127.0.0.1 --port 8090 --reload

test: ## Run unit tests
	uv run pytest tests/unit -v

lint: ## Lint with ruff
	uv run ruff check app/
