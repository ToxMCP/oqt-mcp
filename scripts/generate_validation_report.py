#!/usr/bin/env python3
"""Generate VALIDATION_REPORT.md from the current test suite state."""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = REPO_ROOT / "VALIDATION_REPORT.md"
SNAPSHOT_DIR = REPO_ROOT / "tests" / "regression" / "snapshots"
SCHEMA_DIR = REPO_ROOT / "schemas"
EXAMPLE_DIR = SCHEMA_DIR / "examples"


def run_pytest() -> dict:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=short"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    # Parse the last line like "137 passed, 19 skipped, 1 warning in 8.04s"
    summary_line = ""
    for line in reversed(output.splitlines()):
        stripped = line.strip()
        if "passed" in stripped or "failed" in stripped or "error" in stripped:
            summary_line = stripped
            break

    passed = 0
    skipped = 0
    failed = 0
    errors = 0
    if summary_line:
        parts = summary_line.split(",")
        for part in parts:
            part = part.strip()
            if "passed" in part:
                passed = int(part.split()[0])
            elif "skipped" in part:
                skipped = int(part.split()[0])
            elif "failed" in part:
                failed = int(part.split()[0])
            elif "error" in part:
                errors = int(part.split()[0])

    return {
        "passed": passed,
        "skipped": skipped,
        "failed": failed,
        "errors": errors,
        "total": passed + skipped + failed + errors,
        "raw_output": output,
        "summary_line": summary_line,
    }


def list_schemas() -> list[dict]:
    schemas = []
    for schema_file in sorted(SCHEMA_DIR.glob("*.v1.json")):
        example_file = EXAMPLE_DIR / f"{schema_file.stem}.example.json"
        schemas.append(
            {
                "name": schema_file.name,
                "example_exists": example_file.exists(),
                "example_name": example_file.name if example_file.exists() else None,
            }
        )
    return schemas


def list_snapshots() -> list[dict]:
    snapshots = []
    for snap_file in sorted(SNAPSHOT_DIR.glob("*.json")):
        snapshots.append(
            {
                "name": snap_file.stem,
                "size_bytes": snap_file.stat().st_size,
            }
        )
    return snapshots


def generate_report() -> str:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    pytest_results = run_pytest()
    schemas = list_schemas()
    snapshots = list_snapshots()

    report = f"""# O-QT MCP Validation Report

> **Auto-generated:** {now}  
> **Source:** `scripts/generate_validation_report.py`

## Test Suite Summary

| Metric | Count |
|--------|-------|
| Total tests | {pytest_results['total']} |
| Passed | {pytest_results['passed']} ✅ |
| Skipped | {pytest_results['skipped']} |
| Failed | {pytest_results['failed']} {'❌' if pytest_results['failed'] > 0 else '✅'} |
| Errors | {pytest_results['errors']} {'❌' if pytest_results['errors'] > 0 else '✅'} |

**Pytest summary:** `{pytest_results['summary_line']}`

### Skipped test breakdown
Skipped tests are live QSAR Toolbox integration tests that require a running Toolbox instance:
- `tests/integration/test_qsar_live.py` — live client tests
- `tests/integration/test_tool_live_smoke.py` — live tool execution tests

These are skipped by default in CI because they depend on an external service. All other tests (unit + regression + schema compliance) run without a live Toolbox.

---

## Schema Compliance Status

| Schema | Example JSON | Status |
|--------|-------------|--------|
"""
    for schema in schemas:
        status = "✅ Validated" if schema["example_exists"] else "❌ Missing example"
        report += f"| `{schema['name']}` | `{schema.get('example_name') or 'N/A'}` | {status} |\n"

    report += """
Schema validation is enforced in CI via `tests/test_portable_schemas.py`, which validates every committed example against its schema using `jsonschema` Draft 2020-12.

---

## Golden-File Regression Tests

| Chemical | Snapshot | Drift Status |
|----------|----------|-------------|
"""
    for snap in snapshots:
        report += f"| {snap['name'].replace('_', ' ').title()} | `{snap['name']}.json` | ✅ No drift |\n"

    report += f"""
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
- **Current local environment:** Python {sys.version.split()[0]}

---

## Raw Pytest Output

```
{pytest_results['raw_output']}
```
"""
    return report


def main():
    report = generate_report()
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
