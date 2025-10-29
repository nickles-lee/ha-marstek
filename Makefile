.PHONY: help venv install install-dev test test-unit test-integration clean lint activate

# Default Python version
PYTHON := python3
VENV := venv
VENV_BIN := $(VENV)/bin
PYTEST := $(VENV_BIN)/pytest

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
NC := \033[0m # No Color

help: ## Show this help message
	@echo "$(BLUE)Marstek Local API - Development Makefile$(NC)"
	@echo ""
	@echo "$(GREEN)Available targets:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(GREEN)Quick Start:$(NC)"
	@echo "  1. make venv          # Create virtual environment"
	@echo "  2. make install       # Install dependencies"
	@echo "  3. source venv/bin/activate  # Activate environment"
	@echo "  4. make test          # Run all tests"

venv: ## Create virtual environment
	@echo "$(BLUE)Creating virtual environment...$(NC)"
	$(PYTHON) -m venv $(VENV)
	@echo "$(GREEN)✓ Virtual environment created$(NC)"
	@echo ""
	@echo "$(YELLOW)To activate the environment, run:$(NC)"
	@echo "  source $(VENV_BIN)/activate"

install: venv ## Install all dependencies
	@echo "$(BLUE)Installing dependencies...$(NC)"
	$(VENV_BIN)/pip install --upgrade pip
	$(VENV_BIN)/pip install -r tests/requirements.txt
	@echo "$(GREEN)✓ Dependencies installed$(NC)"

install-dev: install ## Install development dependencies (includes linting, etc.)
	@echo "$(BLUE)Installing development dependencies...$(NC)"
	$(VENV_BIN)/pip install ruff black isort mypy
	@echo "$(GREEN)✓ Development dependencies installed$(NC)"

test: test-unit ## Run all tests (unit tests)
	@echo "$(GREEN)✓ All tests completed$(NC)"

test-unit: ## Run unit tests with pytest
	@echo "$(BLUE)Running unit tests...$(NC)"
	$(PYTEST) tests/ -v

test-integration: ## Run integration tests (requires actual device)
	@echo "$(BLUE)Running integration tests...$(NC)"
	@echo "$(YELLOW)Note: Integration tests require an actual Marstek device on the network$(NC)"
	$(VENV_BIN)/python manual_tests/test_discovery.py

test-coverage: ## Run unit tests with coverage report
	@echo "$(BLUE)Running tests with coverage...$(NC)"
	$(PYTEST) tests/ -v --cov=custom_components.marstek_local_api --cov-report=term-missing --cov-report=html
	@echo "$(GREEN)✓ Coverage report generated in htmlcov/index.html$(NC)"

lint: ## Run code linters (ruff)
	@echo "$(BLUE)Running linters...$(NC)"
	$(VENV_BIN)/ruff check custom_components/marstek_local_api/
	@echo "$(GREEN)✓ Linting complete$(NC)"

format: ## Format code with black and isort
	@echo "$(BLUE)Formatting code...$(NC)"
	$(VENV_BIN)/black custom_components/marstek_local_api/
	$(VENV_BIN)/isort custom_components/marstek_local_api/
	@echo "$(GREEN)✓ Code formatted$(NC)"

activate: ## Show activation command (can't actually activate from Makefile)
	@echo "$(YELLOW)To activate the virtual environment, run:$(NC)"
	@echo "  source $(VENV_BIN)/activate"
	@echo ""
	@echo "$(YELLOW)To deactivate later, run:$(NC)"
	@echo "  deactivate"

clean: ## Remove virtual environment and cached files
	@echo "$(BLUE)Cleaning up...$(NC)"
	rm -rf $(VENV)
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo "$(GREEN)✓ Cleanup complete$(NC)"

clean-all: clean ## Remove all generated files including test artifacts
	@echo "$(BLUE)Deep cleaning...$(NC)"
	rm -rf .ruff_cache
	rm -rf .mypy_cache
	@echo "$(GREEN)✓ Deep cleanup complete$(NC)"

check: lint test ## Run linters and tests
	@echo "$(GREEN)✓ All checks passed$(NC)"

dev-setup: install-dev ## Complete development setup
	@echo "$(GREEN)✓ Development environment ready!$(NC)"
	@echo ""
	@echo "$(YELLOW)Next steps:$(NC)"
	@echo "  1. source $(VENV_BIN)/activate"
	@echo "  2. make test"
	@echo ""
	@echo "$(YELLOW)Available commands:$(NC)"
	@echo "  make test           - Run unit tests"
	@echo "  make lint           - Check code quality"
	@echo "  make format         - Format code"
	@echo "  make test-coverage  - Generate coverage report"

.DEFAULT_GOAL := help

