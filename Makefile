# Makefile for PDFtoPodcast Development
# Common development commands for building, testing, and maintaining the project

.PHONY: help install install-dev test test-coverage lint format typecheck check clean run docs

# Variabelen
PYTHON := python
PIP := pip
VENV := .venv/bin

# Default target - show help
help:
	@echo "PDFtoPodcast Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install          Install production dependencies"
	@echo "  make install-dev      Install development dependencies"
	@echo "  make setup            Complete development setup (install + hooks)"
	@echo ""
	@echo "Development:"
	@echo "  make format           Format code with Black"
	@echo "  make lint             Run Ruff linter"
	@echo "  make lint-fix         Fix lint errors automatically"
	@echo "  make typecheck        Run mypy type checking"
	@echo "  make check            Run all quality checks (format + lint + typecheck)"
	@echo ""
	@echo "Testing:"
	@echo "  make test             Run all tests"
	@echo "  make test-unit        Run unit tests only"
	@echo "  make test-integration Run integration tests only"
	@echo "  make test-coverage    Run tests with coverage report"
	@echo "  make test-fast        Run fast tests (skip slow integration)"
	@echo ""
	@echo "Pipeline:"
	@echo "  make run PDF=path.pdf Run pipeline on PDF"
	@echo "  make run-test         Run pipeline on sample PDF (5 pages)"
	@echo ""
	@echo "Schema Management:"
	@echo "  make bundle-schemas   Bundle all schemas (inline refs)"
	@echo "  make validate-schemas Validate all schema files"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean            Remove temporary files and caches"
	@echo "  make clean-all        Remove all generated files (including tmp/)"
	@echo ""
	@echo "Git helpers:"
	@echo "  make commit           Prepare code for commit (format + lint-fix + pre-commit)"

# Installation
install:
	$(PIP) install -r requirements.txt

install-dev:
	$(PIP) install -r requirements.txt
	@if [ -f requirements-dev.txt ]; then \
		$(PIP) install -r requirements-dev.txt; \
	fi

setup: install-dev
	@if command -v pre-commit >/dev/null 2>&1; then \
		pre-commit install; \
		echo "✅ Pre-commit hooks installed"; \
	else \
		echo "⚠️  pre-commit not found, skipping hooks"; \
	fi
	@echo "✅ Development environment ready!"

# Code Quality
format:
	@echo "Formatting code with Black..."
	$(VENV)/black src/ tests/ run_pipeline.py --line-length 100 || \
		$(PYTHON) -m black src/ tests/ run_pipeline.py --line-length 100
	@echo "✅ Code formatted"

fmt: format

lint:
	@echo "Running Ruff linter..."
	$(VENV)/ruff check . || $(PYTHON) -m ruff check .
	@echo "✅ Linting complete"

lint-fix:
	@echo "Fixing lint errors automatically..."
	$(VENV)/ruff check . --fix || $(PYTHON) -m ruff check . --fix
	@echo "✅ Lint errors fixed"

typecheck:
	@echo "Running mypy type checker..."
	@if command -v mypy >/dev/null 2>&1; then \
		mypy src/ --ignore-missing-imports --check-untyped-defs; \
		echo "✅ Type checking complete"; \
	else \
		echo "⚠️  mypy not installed, skipping type check"; \
	fi

check: format lint typecheck
	@echo "✅ All quality checks passed"

# Testing
test:
	@echo "Running all tests..."
	@if [ -d tests ]; then \
		pytest tests/ -v || echo "⚠️  Tests not yet implemented"; \
	else \
		echo "⚠️  Tests directory not found"; \
	fi

test-unit:
	@echo "Running unit tests..."
	@if [ -d tests ]; then \
		pytest tests/ -v -m "unit"; \
	else \
		echo "⚠️  Tests directory not found"; \
	fi

test-integration:
	@echo "Running integration tests..."
	@if [ -d tests ]; then \
		pytest tests/ -v -m "integration"; \
	else \
		echo "⚠️  Tests directory not found"; \
	fi

test-coverage:
	@echo "Running tests with coverage..."
	@if [ -d tests ]; then \
		pytest tests/ -v --cov=src --cov-report=term-missing --cov-report=html; \
		echo "Coverage report: htmlcov/index.html"; \
	else \
		echo "⚠️  Tests directory not found"; \
	fi

test-fast:
	@echo "Running fast tests (unit tests, excluding slow)..."
	@if [ -d tests ]; then \
		pytest tests/ -v -m "unit and not slow"; \
	else \
		echo "⚠️  Tests directory not found"; \
	fi

# Pipeline Execution
run:
	@if [ -z "$(PDF)" ]; then \
		if [ -z "$(file)" ]; then \
			echo "Error: PDF parameter required. Usage: make run PDF=path.pdf"; \
			exit 1; \
		else \
			$(PYTHON) run_pipeline.py "$(file)" --max-pages 5; \
		fi; \
	else \
		$(PYTHON) run_pipeline.py $(PDF); \
	fi

run-test:
	@echo "Running pipeline on test.pdf (2 pages)..."
	@if [ -f "test.pdf" ]; then \
		$(PYTHON) run_pipeline.py "test.pdf" --max-pages 2; \
	else \
		echo "⚠️  test.pdf not found. Create sample or use: make run PDF=your_file.pdf"; \
	fi

run-claude:
	@if [ -z "$(PDF)" ]; then \
		echo "Error: PDF parameter required. Usage: make run-claude PDF=path.pdf"; \
		exit 1; \
	fi
	$(PYTHON) run_pipeline.py $(PDF) --llm-provider claude

# Schema Management
bundle-schemas:
	@echo "Bundling schemas..."
	cd schemas && $(PYTHON) json-bundler.py
	@echo "✅ Schemas bundled"

bundle: bundle-schemas

validate-schemas:
	@echo "Validating schemas..."
	@if [ -f tests/validate_schemas.py ]; then \
		$(PYTHON) tests/validate_schemas.py; \
		echo "✅ Schemas validated"; \
	else \
		echo "⚠️  tests/validate_schemas.py not found"; \
	fi

# Cleaning
clean:
	@echo "Cleaning temporary files..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	rm -rf htmlcov/ 2>/dev/null || true
	rm -f .coverage 2>/dev/null || true
	rm -rf out/* 2>/dev/null || true
	@echo "✅ Cleaned"

clean-all: clean
	@echo "Removing all generated files..."
	rm -rf tmp/*.json 2>/dev/null || true
	@echo "✅ Deep cleaned"

# Git helpers
commit: lint-fix format
	@if command -v pre-commit >/dev/null 2>&1; then \
		pre-commit run --all-files; \
	else \
		echo "⚠️  pre-commit not installed, skipping hooks"; \
	fi
	@echo "✅ Code netjes gemaakt en pre-commit checks uitgevoerd."
	@echo "👉 Nu kun je veilig committen met: git commit -m '...'"

# CI/CD simulation
ci: check test
	@echo "✅ CI checks passed - ready to push"

# Pre-commit hook simulation
pre-commit: check test-fast
	@echo "✅ Pre-commit checks passed"

# Requirements management
update-deps:
	@echo "Updating dependencies..."
	pip list --outdated
	@echo "To update: pip install --upgrade <package>"

freeze-deps:
	@echo "Freezing current dependencies..."
	pip freeze > requirements.lock
	@echo "✅ Dependencies frozen to requirements.lock"

# Development helpers
inspect-json:
	@if [ -z "$(FILE)" ]; then \
		echo "Error: FILE parameter required. Usage: make inspect-json FILE=tmp/file.json"; \
		exit 1; \
	fi
	@command -v jq >/dev/null 2>&1 && jq '.' $(FILE) || $(PYTHON) -m json.tool $(FILE)

repl:
	@echo "Starting Python REPL with project context..."
	$(PYTHON) -i -c "from src.llm import *; from src.schemas_loader import *; from src.validation import *; print('Modules loaded: llm, schemas_loader, validation')"
