PYTHON ?= python3
POETRY ?= poetry

.PHONY: install test lint format fmt ci

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
