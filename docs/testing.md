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

The suite includes opt-in tests that exercise a live QSAR Toolbox API end-to-end. They are skipped by default because they require network access and a stable test endpoint.

```bash
export QSAR_TOOLBOX_API_URL=http://127.0.0.1:49692
export QSAR_LIVE_TESTS=1
poetry run pytest tests/integration -m integration
```

Ensure `QSAR_TOOLBOX_API_URL` points to the host root (no `/api/v6` suffix) and that the target environment is safe for automated calls.

### Fast vs slow live lanes

The integration suite now has two live layers:

- `QSAR_LIVE_TESTS=1`: enables the fast live checks. This covers the discovery tools, quick QSAR helper flows, and the baseline live client tests.
- `QSAR_LIVE_SLOW_TESTS=1`: additionally enables the slow execution/report workflows that depend on heavier Toolbox server-side processing.

Typical commands:

```bash
# Fast live lane
export QSAR_TOOLBOX_API_URL=http://127.0.0.1:49692
export QSAR_LIVE_TESTS=1
poetry run pytest tests/integration/test_qsar_live.py tests/integration/test_tool_live_smoke.py -q
```

```bash
# Slow live lane (workflows, reports, grouping)
export QSAR_TOOLBOX_API_URL=http://127.0.0.1:49692
export QSAR_LIVE_TESTS=1
export QSAR_LIVE_SLOW_TESTS=1
export QSAR_LIGHT_TIMEOUT_SECONDS=20
export QSAR_LIGHT_MAX_ATTEMPTS=1
export QSAR_HEAVY_TIMEOUT_SECONDS=70
export QSAR_HEAVY_MAX_ATTEMPTS=1
poetry run pytest tests/integration/test_tool_live_smoke.py -m slow -q
```

The slow lane is intentionally separate because some Toolbox endpoints can take minutes to return, especially profiling, metabolism, grouping, and report-generation calls.

The QSAR client budgets are deployment-tunable through environment variables. The most relevant knobs for live testing are:

- `QSAR_LIGHT_TIMEOUT_SECONDS` and `QSAR_HEAVY_TIMEOUT_SECONDS`
- `QSAR_LIGHT_MAX_ATTEMPTS` and `QSAR_HEAVY_MAX_ATTEMPTS`
- `QSAR_HAZARD_PROFILING_WALLCLOCK_TIMEOUT_SECONDS`
- `QSAR_DISCOVERY_LIST_ALL_TOTAL_WALLCLOCK_TIMEOUT_SECONDS`
- `QSAR_DISCOVERY_LIST_ALL_PER_POSITION_TIMEOUT_SECONDS`
- `QSAR_DISCOVERY_SEARCH_DATABASES_WALLCLOCK_TIMEOUT_SECONDS`

Use the wall-clock settings when you want the MCP to fail soft with explicit partial evidence. Use the retry settings when the Toolbox is usually healthy but occasionally transient.

On some Toolbox instances, `search/databases` and name-based search resolution can also be noticeably slower or intermittently unavailable. The fast lane therefore resolves the shared smoke-test chemical via SMILES, while the dedicated search-database check remains in the slow lane.

Catalog-style discovery is also bounded now. `list_all_qsar_models` can return `status="partial"` together with `catalog_metadata` and `warnings` when some endpoint-tree positions time out during enumeration. That is expected behavior on slow Toolbox instances and should be treated as explicit incompleteness, not as a silent success.

If your local Toolbox intermittently times out on catalog discovery endpoints during the slow lane, you can provide fallback identifiers for the smoke harness:

```bash
export QSAR_LIVE_FALLBACK_CHEM_ID=25511866-347f-d9f9-d598-d23f9501a8cb
export QSAR_LIVE_FALLBACK_SMILES='CC(C)=O'
export QSAR_LIVE_FALLBACK_PROFILER_GUID='<profiler-guid>'
export QSAR_LIVE_FALLBACK_PROFILER_CAPTION='<profiler-caption>'
export QSAR_LIVE_FALLBACK_SIMULATOR_GUID='<simulator-guid>'
export QSAR_LIVE_FALLBACK_SIMULATOR_CAPTION='<simulator-caption>'
export QSAR_LIVE_FALLBACK_QSAR_GUID='<qsar-guid>'
export QSAR_LIVE_FALLBACK_WORKFLOW_GUID='<workflow-guid>'
export QSAR_LIVE_FALLBACK_ANALOGUE_SMILES='CCC(C)=O'
```

The tests still prefer live discovery first. These values are only used when the corresponding discovery call times out.

The current smoke harness also supports direct `chemId` execution paths for the high-level workflow tools. That is the preferred live-test mode when you already know the Toolbox identifier and want to avoid a fragile name or SMILES search round-trip.

Known live-toolbox limitations observed on Toolbox `4.8.2`:

- `download_workflow_report` may time out or return an empty payload even when the Toolbox host is otherwise responsive. The live test marks that as an expected upstream limitation after direct verification.
- `group_chemicals_by_profiler` may time out for otherwise valid profilers. The live test marks that as an expected upstream limitation when the direct grouping endpoint does not return within the configured budget.
- `download_qsar_report` can return a ZIP bundle rather than a bare PDF. The smoke test now validates `content_type`, archive entries, and any extracted `pdf_report_base64` instead of assuming a raw PDF response.

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
