# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- _TBD_

### Changed
- _TBD_

### Fixed
- _TBD_

---

## [0.2.0] - 2026-03-23

### Added
- Portable O-QT handoff schemas for workflow provenance, hazard evidence, and read-across support under `schemas/`, plus validated examples for downstream orchestrators.
- New architecture and downstream-orchestration docs clarifying how O-QT fits inside the ToxMCP suite without becoming the suite orchestrator.

### Changed
- Repositioned O-QT MCP as the ToxMCP suite's specialized OECD QSAR Toolbox workflow engine, with `run_oqt_multiagent_workflow` documented as the primary default entrypoint and lower-level tools framed as expert helpers.
- Updated public README, quick start instructions, and release docs to point at `ToxMCP/oqt-mcp` and describe the synchronous deployment model honestly.
- Bumped package metadata to `0.2.0` and updated project URLs to the current repository.

### Fixed
- Removed stale repository identity drift from release metadata and setup instructions.

---

## [0.1.0] - 2025-11-01

### Added
- Initial MCP server scaffold with FastAPI transport, OIDC/RBAC security, QSAR client boilerplate, and developer tooling.
- Dockerfile and docker-compose stack for local development with Toolbox API stub.
- Taskmaster backlog, documentation set (`docs/auth_testing.md`, `docs/observability.md`, `docs/testing.md`), and CI workflow skeleton.

[Unreleased]: https://github.com/ToxMCP/oqt-mcp/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/ToxMCP/oqt-mcp/releases/tag/v0.2.0
[0.1.0]: https://github.com/ToxMCP/oqt-mcp/releases/tag/v0.1.0
