# Testing & Tooling

## Installing Dependencies

```bash
poetry install --no-root
```

## Running Tests

```bash
PYTHONPATH=src poetry run python -m pytest
```

Pytest configuration lives in `pyproject.toml` (pythonpath, asyncio mode, warning filters).

## Formatting & Linting

```bash
poetry run black .
poetry run isort .
```

or use `make format`.

## Make Targets

| Command       | Description                   |
|---------------|-------------------------------|
| `make install`| Install dependencies          |
| `make test`   | Run test suite                |
| `make lint`   | Run `isort` + `black` checks  |
| `make fmt`    | Auto-format with `isort`+`black` |

## Continuous Integration

GitHub Actions workflow (`.github/workflows/ci.yml`) runs lint and tests against Python 3.10/3.11 on pushes and pull requests.
