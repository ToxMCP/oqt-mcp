# Regulatory Readiness Checklist — O-QT MCP

> **Version:** 0.3.1  
> **Last updated:** April 2026  
> **Target audience:** Regulatory agencies, EU/US/international reviewers, downstream orchestrators

This checklist documents the trustworthiness properties of the O-QT MCP server for regulatory risk-assessment workflows. Each item includes the current status, evidence location, and any known limitations.

---

## 1. Schema Compliance

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1.1 | `oqtWorkflowRecord.v1.json` is fully populated by runtime code | ✅ Complete | `src/tools/implementations/workflow_runner.py` — `_build_portable_workflow_record` |
| 1.2 | `oqtReadAcrossSummary.v1.json` is fully populated by runtime code | ✅ Complete | `src/tools/implementations/workflow_runner.py` — `_build_grouping_portable_handoffs` |
| 1.3 | `oqtHazardEvidenceSummary.v1.json` is fully populated by runtime code | ✅ Complete | `src/tools/implementations/o_qt_qsar_tools.py` + `workflow_runner.py` hazard handoffs |
| 1.4 | `oqtEndpointSummary.v1.json` is fully populated where Toolbox data permits | ✅ Complete | `src/tools/hazard_contracts.py` — `build_endpoint_summaries_from_payload` |
| 1.5 | Every schema has a committed, validated example JSON | ✅ Complete | `schemas/examples/*.v1.example.json` |
| 1.6 | CI validates all schema examples on every build | ✅ Complete | `tests/test_portable_schemas.py` |

### Schema-validation test coverage
- `tests/tools/test_workflow_runner_handoffs.py` — workflow & grouping handoff validation
- `tests/tools/test_hazard_contracts.py` — hazard evidence block & endpoint summary validation
- `tests/tools/test_export_adapters.py` — export bundle ZIP + manifest validation
- `tests/test_portable_schemas.py` — committed example validation against schemas

---

## 2. Provenance & Version Capture

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 2.1 | Every workflow record includes a reproducibility block | ✅ Complete | `reproducibility` object in `oqtWorkflowRecord.v1` |
| 2.2 | Input hash (deterministic SHA-256 of normalized inputs) is captured | ✅ Complete | `reproducibility.inputHash` |
| 2.3 | Toolchain versions (app, Python, FastAPI, Pydantic, httpx) are recorded | ✅ Complete | `reproducibility.toolchainVersions` |
| 2.4 | Upstream API versions (`api-supported-versions` header) are captured | ✅ Complete | `reproducibility.upstreamVersions.apiVersions` |
| 2.5 | Toolbox server date is captured for traceability | ✅ Complete | `reproducibility.upstreamVersions.serverDate` |
| 2.6 | Toolbox build version is captured | ⚠️ Limited | Not exposed by Toolbox API; reported as `"unknown"` |
| 2.7 | Database / data-snapshot version is captured | ⚠️ Limited | Not exposed by Toolbox API; reported as `"unknown"` |
| 2.8 | Model provenance (GUID, title, donator) is attached to QSAR findings | ✅ Complete | `qsarFinding.source` + `model_provenance` in tool responses |
| 2.9 | Profiler & simulator provenance is attached to hazard outputs | ✅ Complete | `profilerFinding.source`, `metabolismFinding.source` |

### Known limitation
The OECD QSAR Toolbox WebAPI does not currently provide a dedicated endpoint for build version or database version. O-QT MCP captures everything the API headers expose (`api-supported-versions`, `Date`). When the Toolbox adds these fields, they will flow into `reproducibility.upstreamVersions` automatically.

---

## 3. Human Review Checkpoint Policy

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 3.1 | Workflows can pause for human review before final report generation | ✅ Complete | `require_human_review=True` in `run_oqt_multiagent_workflow` |
| 3.2 | Review checkpoints are materialized with step IDs and preview data | ✅ Complete | `review_orchestrator.create_checkpoint_if_missing` |
| 3.3 | Checkpoints can be approved via a dedicated MCP tool | ✅ Complete | `approve_workflow_checkpoint` tool |
| 3.4 | Unapproved workflows return `status="review_required"` | ✅ Complete | `_build_workflow_portable_handoffs` + schema enum |
| 3.5 | Review decisions are logged in the workflow record | ✅ Complete | `ReviewDecision` entries in `review_orchestrator` |

### Policy notes
- Human review is **opt-in** (`require_human_review=False` by default) so automated pipelines are not blocked.
- When enabled, checkpoints are created at:
  1. Chemical identity resolution
  2. Final report generation (before PDF artifact creation)
- Downstream systems should treat `review_required` as a hard pause until explicit approval.

---

## 4. Privacy & Audit Logging

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 4.1 | PII scrubbing is applied before audit-log serialization | ✅ Complete | `src/utils/privacy.py` — `_hash_value`, `_scrub_dict` |
| 4.2 | Audit events are emitted for tool execution, auth decisions, and checkpoints | ✅ Complete | `src/utils/audit.py` — `audit_event()` decorator |
| 4.3 | Consent tracking is present in privacy configuration | ✅ Complete | `PrivacyConfig` in `src/utils/privacy.py` |
| 4.4 | Raw user API keys are never logged or returned in handoffs | ✅ Complete | Keys are passed to assistant config but excluded from `log_bundle["inputs"]` serialization |

---

## 5. Determinism & Regression Testing

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 5.1 | Golden-file regression tests exist for workflow outputs | ✅ Complete | `tests/regression/test_golden_workflow.py` |
| 5.2 | Golden-file regression tests exist for grouping outputs | ✅ Complete | `tests/regression/test_golden_grouping.py` |
| 5.3 | Snapshots exclude volatile fields (timestamps, UUIDs, durations) | ✅ Complete | `tests/regression/_helpers.py` — `normalize_for_snapshot()` |
| 5.4 | Committed snapshots are re-validated on every CI run | ✅ Complete | `pytest tests/regression/` runs in standard test suite |
| 5.5 | Input-hash stability allows downstream systems to detect input changes | ✅ Complete | `reproducibility.inputHash` is SHA-256 of canonical JSON |

### Golden-file chemicals
- **Benzene** — workflow snapshot (`tests/regression/snapshots/workflow_benzene.json`)
- **Benzene** — grouping snapshot (`tests/regression/snapshots/grouping_benzene.json`)

---

## 6. Package Semantics & Export Adapters

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 6.1 | `working_bundle` mode returns live, mutable MCP responses | ✅ Complete | `packageSemantics.mode="working_bundle"`, `isReadOnly=False` |
| 6.2 | `packaged_dossier` mode returns frozen, read-only exports | ✅ Complete | `packageSemantics.mode="packaged_dossier"`, `isReadOnly=True` |
| 6.3 | Every artifact in `packaged_dossier` has SHA-256 checksum | ✅ Complete | `_build_artifact_entry` computes checksums |
| 6.4 | A `manifest.json` is auto-generated and attached in `packaged_dossier` | ✅ Complete | `_build_attachment_manifest` generates manifest |
| 6.5 | Export adapter tools produce clean ZIP archives for downstream ingestion | ✅ Complete | `export_grouping_bundle`, `export_hazard_summary` |
| 6.6 | ZIP members have correct `role`, `mediaType`, `sizeBytes`, `checksumSha256` | ✅ Complete | `_describe_binary_artifact` + `_inject_attachment_context` |

---

## 7. Known Limitations & Out-of-Scope Items

### Limitations (documented, not bugs)
1. **Toolbox API does not expose build/database version.** `upstreamVersions.toolboxBuildVersion` and `databaseVersion` are `"unknown"` until the API provides them.
2. **No cross-module synthesis.** O-QT MCP packages evidence; it does not perform exposure assessment, PBPK modeling, or final regulatory classification.
3. **No probabilistic confidence.** Uncertainty is expressed as qualitative `low/medium/high` bands with explicit quantitative metrics, not as statistical confidence intervals.
4. **Stochastic steps are not supported.** `randomSeed` is always `null` because all current processing is deterministic.
5. **Live Toolbox availability affects completeness.** If the Toolbox API times out, the workflow returns `status="partial"` with explicit warnings rather than failing silently.

### Out of scope (by design)
- Replacing IUCLID or becoming a full dossier management system
- Embedded database persistence for workflow state (stateless server with documented in-memory limits)
- Direct regulatory decision text generation

---

## 8. Recommendations for Agency Integration

1. **Consume portable handoffs directly** (`oqtWorkflowRecord.v1`, `oqtReadAcrossSummary.v1`, `oqtHazardEvidenceSummary.v1`) rather than parsing raw MCP text responses.
2. **Validate `reproducibility.inputHash`** when comparing runs for the same chemical to confirm identical inputs were used.
3. **Use `packaged_dossier` mode** for batch export/ingestion pipelines where immutability is required.
4. **Require `require_human_review=True`** for any workflow that feeds into a final regulatory decision.
5. **Treat `status="partial"` as a signal to inspect `log_json.errors` and `evidenceBlocks` for missing data**, not as a hard failure.

---

## 9. Validation Artifacts

- **Test suite:** `pytest tests/`
- **Schema examples:** `schemas/examples/`
- **Exported bundles:** `examples/exported_bundles/`
- **Agency dossiers:** `examples/agency_dossiers/`
- **Validation report:** `VALIDATION_REPORT.md` (auto-generated)
