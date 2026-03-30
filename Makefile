# SecondBrain Makefile
# Convenience targets for common development tasks

.PHONY: help install install-dev test lint format type-check clean

##@ Development

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Available targets:"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install runtime dependencies
	pip install -e .

install-dev: ## Install with development dependencies
	pip install -e ".[dev]"

install-opentelemetry: ## Install with OpenTelemetry support
	pip install -e ".[opentelemetry]"

##@ Testing

test: ## Run all tests
	pytest

test-verbose: ## Run tests with verbose output
	pytest -v

test-coverage: ## Run tests with coverage report
	pytest --cov=secondbrain --cov-report=term-missing

test-integration: ## Run integration tests only
	pytest -m integration

##@ Code Quality

lint: ## Run linter (ruff)
	ruff check .

format: ## Format code (ruff format)
	ruff format .

type-check: ## Run type checker (mypy)
	mypy .

check: lint format type-check ## Run all code quality checks

##@ Dependency Management

deps-check: ## Check for outdated dependencies
	./scripts/update_dependencies.sh check

deps-update: ## Apply safe dependency updates
	./scripts/update_dependencies.sh update

deps-audit: ## Run security audit on dependencies
	./scripts/audit_dependencies.sh

deps-validate: ## Validate dependencies
	./scripts/validate_dependencies.sh

deps-full: deps-check deps-audit deps-validate ## Run full dependency check

##@ SBOM Generation

sbom: ## Generate SBOM in all formats
	./scripts/generate_sbom.sh

sbom-spdx: ## Generate SPDX format SBOM
	./scripts/generate_sbom.sh --format spdx

sbom-cyclonedx: ## Generate CycloneDX format SBOM
	./scripts/generate_sbom.sh --format cyclonedx

sbom-compare: ## Generate SBOM and compare with previous
	./scripts/generate_sbom.sh --compare

##@ Security

security-scan: ## Run comprehensive security scan
	./scripts/security_scan.sh

security-pip-audit: ## Run pip-audit only
	./scripts/audit_dependencies.sh pip-audit

security-safety: ## Run safety check only
	./scripts/audit_dependencies.sh safety

security-bandit: ## Run bandit static analysis
	./scripts/audit_dependencies.sh bandit

##@ Build

build: ## Build distribution packages
	./scripts/build.sh

##@ Cleanup

clean: ## Clean up generated files
	./scripts/cleanup_reports.sh
	./scripts/cleanup_coverage.sh
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache htmlcov/ dist/ build/

clean-all: clean ## Clean including virtual environment
	rm -rf venv/ .venv/

##@ Services

services-start: ## Start test services
	./scripts/start_test_services.sh

services-stop: ## Stop test services
	./scripts/stop_test_services.sh

##@ Documentation

docs-serve: ## Serve documentation locally
	mkdocs serve

docs-build: ## Build documentation
	mkdocs build
