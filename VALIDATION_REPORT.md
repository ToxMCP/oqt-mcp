# O-QT MCP Validation Report

> **Auto-generated:** 2026-04-17T20:25:32.695318Z  
> **Source:** `scripts/generate_validation_report.py`

## Test Suite Summary

| Metric | Count |
|--------|-------|
| Total tests | 158 |
| Passed | 139 ✅ |
| Skipped | 19 |
| Failed | 0 ✅ |
| Errors | 0 ✅ |

**Pytest summary:** `139 passed, 19 skipped, 1 warning in 11.91s`

### Skipped test breakdown
Skipped tests are live QSAR Toolbox integration tests that require a running Toolbox instance:
- `tests/integration/test_qsar_live.py` — live client tests
- `tests/integration/test_tool_live_smoke.py` — live tool execution tests

These are skipped by default in CI because they depend on an external service. All other tests (unit + regression + schema compliance) run without a live Toolbox.

---

## Schema Compliance Status

| Schema | Example JSON | Status |
|--------|-------------|--------|
| `oqtEndpointSummary.v1.json` | `oqtEndpointSummary.v1.example.json` | ✅ Validated |
| `oqtHazardEvidenceSummary.v1.json` | `oqtHazardEvidenceSummary.v1.example.json` | ✅ Validated |
| `oqtReadAcrossSummary.v1.json` | `oqtReadAcrossSummary.v1.example.json` | ✅ Validated |
| `oqtWorkflowRecord.v1.json` | `oqtWorkflowRecord.v1.example.json` | ✅ Validated |

Schema validation is enforced in CI via `tests/test_portable_schemas.py`, which validates every committed example against its schema using `jsonschema` Draft 2020-12.

---

## Golden-File Regression Tests

| Chemical | Snapshot | Drift Status |
|----------|----------|-------------|
| Grouping Benzene | `grouping_benzene.json` | ✅ No drift |
| Workflow Benzene | `workflow_benzene.json` | ✅ No drift |

Golden-file tests live in `tests/regression/`. They run `build_grouping_justification` and `run_oqt_multiagent_workflow` with fixed, monkeypatched inputs and compare the normalized output (volatile fields stripped) against committed snapshots in `tests/regression/snapshots/`.

If a snapshot drifts, the test fails and the developer must either fix the regression or update the snapshot intentionally.

---

## Reproducibility Metadata Coverage

| Field | Coverage | Notes |
|-------|----------|-------|
| `inputHash` | ✅ SHA-256 | Deterministic hash of canonical JSON inputs |
| `snapshotHash` | — | Reserved for future full-handoff hashing |
| `toolchainVersions` | ✅ app, python, fastapi, pydantic, httpx | Captured at module load time |
| `upstreamVersions.apiVersions` | ✅ From `api-supported-versions` header | Captured per Toolbox call |
| `upstreamVersions.serverDate` | ✅ From `Date` header | Captured per Toolbox call |
| `upstreamVersions.toolboxBuildVersion` | ⚠️ `"unknown"` | Not exposed by Toolbox API |
| `upstreamVersions.databaseVersion` | ⚠️ `"unknown"` | Not exposed by Toolbox API |
| `executionTimestamp` | ✅ ISO 8601 | UTC timestamp of handoff generation |
| `randomSeed` | ✅ `null` | No stochastic steps currently |

---

## Package Semantics Coverage

| Mode | `isReadOnly` | `manifest.json` | Use Case |
|------|-------------|-----------------|----------|
| `working_bundle` | `false` | Optional | Live MCP response, editable |
| `packaged_dossier` | `true` | Required | Frozen export for downstream ingestion |

---

## CI Status

- **GitHub Actions workflow:** `.github/workflows/ci.yml`
- **Python versions tested:** 3.10, 3.11 (per CI matrix)
- **Current local environment:** Python 3.14.3

---

## Raw Pytest Output

```
.................sssssssssssssssssss.................................... [ 45%]
........................................................................ [ 91%]
..............                                                           [100%]
=============================== warnings summary ===============================
.venv/lib/python3.14/site-packages/pythonjsonlogger/jsonlogger.py:11
  /Volumes/Storage/topotox_space_relief_20260220/O-QT_MCP/o-qt-mcp-server-public/.venv/lib/python3.14/site-packages/pythonjsonlogger/jsonlogger.py:11: DeprecationWarning: pythonjsonlogger.jsonlogger has been moved to pythonjsonlogger.json
    warnings.warn(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
SKIPPED [1] tests/integration/test_qsar_live.py:47: Live QSAR Toolbox integration tests are disabled. Set QSAR_LIVE_TESTS=1 to enable.
SKIPPED [1] tests/integration/test_qsar_live.py:57: Slow live Toolbox integration tests are disabled. Set QSAR_LIVE_SLOW_TESTS=1 to enable.
SKIPPED [1] tests/integration/test_qsar_live.py:69: Live QSAR Toolbox integration tests are disabled. Set QSAR_LIVE_TESTS=1 to enable.
SKIPPED [1] tests/integration/test_tool_live_smoke.py:369: Live QSAR Toolbox integration tests are disabled. Set QSAR_LIVE_TESTS=1 to enable.
SKIPPED [1] tests/integration/test_tool_live_smoke.py:435: Slow live Toolbox execution tests are disabled. Set QSAR_LIVE_SLOW_TESTS=1 to enable.
SKIPPED [1] tests/integration/test_tool_live_smoke.py:449: Slow live Toolbox execution tests are disabled. Set QSAR_LIVE_SLOW_TESTS=1 to enable.
SKIPPED [1] tests/integration/test_tool_live_smoke.py:467: Slow live Toolbox execution tests are disabled. Set QSAR_LIVE_SLOW_TESTS=1 to enable.
SKIPPED [1] tests/integration/test_tool_live_smoke.py:484: Slow live Toolbox execution tests are disabled. Set QSAR_LIVE_SLOW_TESTS=1 to enable.
SKIPPED [1] tests/integration/test_tool_live_smoke.py:501: Slow live Toolbox execution tests are disabled. Set QSAR_LIVE_SLOW_TESTS=1 to enable.
SKIPPED [1] tests/integration/test_tool_live_smoke.py:565: Slow live Toolbox execution tests are disabled. Set QSAR_LIVE_SLOW_TESTS=1 to enable.
SKIPPED [1] tests/integration/test_tool_live_smoke.py:586: Slow live Toolbox execution tests are disabled. Set QSAR_LIVE_SLOW_TESTS=1 to enable.
SKIPPED [1] tests/integration/test_tool_live_smoke.py:603: Slow live Toolbox execution tests are disabled. Set QSAR_LIVE_SLOW_TESTS=1 to enable.
SKIPPED [1] tests/integration/test_tool_live_smoke.py:622: Slow live Toolbox execution tests are disabled. Set QSAR_LIVE_SLOW_TESTS=1 to enable.
SKIPPED [1] tests/integration/test_tool_live_smoke.py:639: Slow live Toolbox execution tests are disabled. Set QSAR_LIVE_SLOW_TESTS=1 to enable.
SKIPPED [1] tests/integration/test_tool_live_smoke.py:656: Slow live Toolbox execution tests are disabled. Set QSAR_LIVE_SLOW_TESTS=1 to enable.
SKIPPED [1] tests/integration/test_tool_live_smoke.py:678: Slow live Toolbox execution tests are disabled. Set QSAR_LIVE_SLOW_TESTS=1 to enable.
SKIPPED [1] tests/integration/test_tool_live_smoke.py:695: Slow live Toolbox execution tests are disabled. Set QSAR_LIVE_SLOW_TESTS=1 to enable.
SKIPPED [1] tests/integration/test_tool_live_smoke.py:753: Slow live Toolbox execution tests are disabled. Set QSAR_LIVE_SLOW_TESTS=1 to enable.
SKIPPED [1] tests/integration/test_tool_live_smoke.py:781: Slow live Toolbox execution tests are disabled. Set QSAR_LIVE_SLOW_TESTS=1 to enable.
139 passed, 19 skipped, 1 warning in 11.91s

```
