PYTHON ?= python3
POETRY ?= poetry

.PHONY: install test lint format fmt ci run run-prod

install:
	$(POETRY) install --no-root

test:
	PYTHONPATH=src $(POETRY) run python -m pytest

lint:
	$(POETRY) run isort --check .
	$(POETRY) run black --check .

format fmt:
	$(POETRY) run isort .
	$(POETRY) run black .

ci: format lint test

# Run the MCP server for local development
run:
	$(POETRY) run uvicorn src.api.server:app --host 127.0.0.1 --port 8000 --reload

# Run the MCP server without auto-reload (closer to production)
run-prod:
	$(POETRY) run uvicorn src.api.server:app --host 0.0.0.0 --port 8000
