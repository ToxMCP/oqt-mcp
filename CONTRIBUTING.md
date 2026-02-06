# Contributing to O-QT MCP Server

Thanks for your interest in contributing.

## Development setup

```bash
git clone https://github.com/senseibelbi/O_QT_MCP.git
cd O_QT_MCP/o-qt-mcp-server
poetry install --with dev
cp .env.example .env
```

## Quality checks

Before opening a pull request, run:

```bash
poetry run isort .
poetry run black .
poetry run python -m pytest
```

## Pull request guidelines

- Keep pull requests focused and small enough to review.
- Update tests and docs for behavior changes.
- Do not commit secrets or environment-specific files.
- Confirm CI passes before requesting review.

## Commit style

Conventional Commit prefixes are preferred (`feat:`, `fix:`, `docs:`, `chore:`, `test:`), but not required.

## Reporting bugs

Open a GitHub issue with:

- A clear description of expected vs actual behavior.
- Reproduction steps.
- Logs and stack traces (with secrets removed).

## Questions

For general questions, open a GitHub discussion or issue in this repository.
