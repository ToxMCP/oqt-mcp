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

## [0.3.1] - 2026-04-17

### Added
- **Human review checkpoints** (`OQT-02`). When `require_human_review=true` is passed to `run_oqt_multiagent_workflow`, the workflow now pauses at up to three checkpoints (`chemical_identity`, `ad_assessment`, `final_report`) and returns `status: "review_required"` instead of auto-generating artifacts.
- `approve_workflow_checkpoint` tool to explicitly approve or reject pending workflow checkpoints.
- **Applicability-domain hard gating** (`OQT-01`). Out-of-domain predictions block PDF generation when `require_human_review=true`.
- `PrivacyLogFilter` (`OQT-05`) to scrub SMILES, CAS numbers, and chemical names from free-text log messages and URL query parameters before emission.
- `sanitize_for_llm()` utility (`OQT-04`) to strip control characters, backticks, and dollar signs from untrusted identifiers before they enter LLM-facing contexts.
- Fallback PDF provenance enhancements (`OQT-03`): disclaimer header, applicability-domain warnings section, and provenance summary showing models run and AD warning count.
- `qsar_models_executed` field in the workflow response for full QSAR transparency (`MD-004`).
- Safer search defaults (`HG-001`): `search_type` now defaults to `"name"` instead of `"auto"`.
- Unit tests for sanitization, privacy scrubbing, and review checkpoint orchestration.

### Changed
- HTTP audit middleware now parses query strings into dictionaries so parameter keys remain readable while values are hashed.
- Updated `AGENTS.md` with critical-control policies to prevent future regressions of AD gating, sanitization, privacy, and review defaults.

### Fixed
- Removed raw chemical identifiers from audit logs; all SMILES, CAS, and chemical-name values are now hashed before emission.

---

## [0.3.0] - 2026-04-08

### Added
- Machine-readable boundary and ownership fields in the portable hazard and read-across contracts: `assessmentBoundary`, `decisionBoundary`, `decisionOwner`, `supports`, and `requiredExternalInputs`.
- `semanticCoverage` in the portable hazard uncertainty block to make the qualitative-only uncertainty semantics explicit.
- Live Toolbox smoke coverage for hazard analysis, workflow handoffs, grouping dossiers, log replay, and direct execution helpers.
- Configurable wall-clock safeguards for slow hazard-profiling and discovery-heavy Toolbox paths.

### Changed
- Bumped package metadata and runtime version markers to `0.3.0`.
- Updated the public README, architecture notes, and release docs to match the current contract layer and live-validation surface.
- Refined normalized provenance packaging so endpoint study records, endpoint summaries, evidence blocks, and source-call metadata remain easier to audit downstream.

### Fixed
- Removed stale public-doc references to still-private local module names.
- Eliminated version drift between package metadata, runtime fallbacks, and example payloads.

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

[Unreleased]: https://github.com/ToxMCP/oqt-mcp/compare/v0.3.1...HEAD
[0.3.1]: https://github.com/ToxMCP/oqt-mcp/releases/tag/v0.3.1
[0.3.0]: https://github.com/ToxMCP/oqt-mcp/releases/tag/v0.3.0
[0.2.0]: https://github.com/ToxMCP/oqt-mcp/releases/tag/v0.2.0
[0.1.0]: https://github.com/ToxMCP/oqt-mcp/releases/tag/v0.1.0
