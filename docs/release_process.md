# Release Management Guide

This guide describes how to cut releases for the O-QT MCP server, including semantic versioning, tagging, and publishing changelog entries.

## Versioning Policy

- We follow **Semantic Versioning**: `MAJOR.MINOR.PATCH`.
- Increment:
  - `MAJOR` when backwards-incompatible API or contract changes are introduced.
  - `MINOR` for backwards-compatible functionality additions (new tools, endpoints, or deployment options).
  - `PATCH` for bug fixes or documentation-only changes that do not alter behaviour.

## Pre-release Checklist

1. **Validate tests**: `poetry run python -m pytest`.
2. **Run linters/formatters** (optional but recommended): `poetry run black .` and `poetry run isort .`.
3. **Build Docker image**: `docker build -t o-qt-mcp-server .` (ensures the container still builds).
4. **Update docs**:
   - Ensure `README.md` reflects deployment instructions and configuration changes.
   - Update `CHANGELOG.md` with the additions/changes/fixes for this release.
5. **Review security toggles**: confirm production defaults (`BYPASS_AUTH=false`, correct `QSAR_TOOLBOX_API_URL`).
6. **Verify Taskmaster tasks**: close out completed tasks or capture follow-ups.

## Publishing a Release

1. Decide the new version (e.g., `v0.2.0`) and update `pyproject.toml` accordingly.
2. Move entries from `## [Unreleased]` in `CHANGELOG.md` into a new section `## [x.y.z] - YYYY-MM-DD`.
3. Commit changes with a message such as `chore: prepare v0.2.0 release`.
4. Tag the commit:
   ```bash
   git tag -a v0.2.0 -m "O-QT MCP Server v0.2.0"
   git push origin v0.2.0
   ```
5. Create a GitHub release for the new tag, pasting the changelog entry. Include links to documentation and any upgrade notes.

## Post-release

- Open a new `## [Unreleased]` section in `CHANGELOG.md` if it was consumed.
- If required, notify downstream teams (assistant integrators, infra) about the release.
- Update deployment manifests (Kubernetes, Compose overrides) with the new image tag if applicable.
