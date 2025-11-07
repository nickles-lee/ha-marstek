.PHONY: help install test lint format clean

# Default Python version
PYTHON := python3
VENV := venv
VENV_BIN := $(VENV)/bin
PYTEST := $(VENV_BIN)/pytest

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

install: venv ## Install dependencies (including dev tools)
	$(VENV_BIN)/pip install --upgrade pip
	$(VENV_BIN)/pip install -r tests/requirements.txt
	$(VENV_BIN)/pip install ruff black isort mypy

venv:
	$(PYTHON) -m venv $(VENV)

test: ## Run unit tests
	$(PYTEST) tests/ -v

lint: ## Run code linters
	$(VENV_BIN)/ruff check custom_components/marstek_local_api/

format: ## Format code with black and isort
	$(VENV_BIN)/black custom_components/marstek_local_api/
	$(VENV_BIN)/isort custom_components/marstek_local_api/

clean: ## Remove virtual environment and cached files
	rm -rf $(VENV) .pytest_cache htmlcov .coverage .ruff_cache .mypy_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

.DEFAULT_GOAL := help

