# Testing & Tooling

## Installing Dependencies

```bash
poetry install --no-root
```

## Running Tests

```bash
poetry run pytest
```

Pytest configuration lives in `pyproject.toml`. You can target specific directories or files (e.g. `poetry run pytest tests/auth -q`) without additional `PYTHONPATH` tweaks.

### Live QSAR integration tests (optional)

The suite includes opt-in tests that exercise the sandbox QSAR Toolbox API end-to-end. They are skipped by default because they require network access and a stable test endpoint.

```bash
export QSAR_TOOLBOX_API_URL=http://13.50.204.132:8804
export QSAR_LIVE_TESTS=1
poetry run pytest tests/integration -m integration
```

Ensure `QSAR_TOOLBOX_API_URL` points to the host root (no `/api/v6` suffix) and that the target environment is safe for automated calls.

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
