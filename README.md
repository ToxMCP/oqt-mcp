[![CI](https://github.com/ToxMCP/oqt-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/ToxMCP/oqt-mcp/actions/workflows/ci.yml)

## Architecture

![O-QT MCP architecture](./assets/oqt-mcp-architecture.jpg)

[![DOI](https://img.shields.io/badge/DOI-10.64898%2F2026.02.06.703989-blue)](https://doi.org/10.64898/2026.02.06.703989)
[![License](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](./LICENSE)
[![Release](https://img.shields.io/github/v/release/ToxMCP/oqt-mcp?sort=semver)](https://github.com/ToxMCP/oqt-mcp/releases)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)

# O-QT MCP Server

> Part of **ToxMCP** Suite → https://github.com/ToxMCP/toxmcp


**Public MCP endpoint for the OECD QSAR Toolbox.**  
Run QSAR workflows, stream structured outputs, and download audit-ready PDF reports through any MCP-aware agent (Claude Code, Codex CLI, Gemini CLI, etc.).

## Why this project exists

Chemical safety work often relies on the proprietary OECD QSAR Toolbox desktop application. Scientists have to click through many screens to gather profilers, metabolism simulators, and QSAR predictions before writing regulatory reports.  

The O-QT MCP server turns that workflow into an **open, programmable interface**:

- **Single MCP tool (`run_oqt_multiagent_workflow`, formerly `run_qsar_workflow`)** orchestrates the same multi-agent pipeline used in the O-QT AI Assistant.
- **Structured JSON + Markdown + PDF** responses are returned in one call, ready for downstream automation.
- **Vendor-neutral** – any coding agent that speaks MCP can trigger analyses and capture outputs.

> Looking for the original assistant UI? See [O-QT-OECD-QSAR-Toolbox-AI-assistant](https://github.com/VHP4Safety/O-QT-OECD-QSAR-Toolbox-AI-assistant). The MCP server reuses the same core logic but wraps it in a secure, headless API designed for automation.
>
> Related publication: [Artificial intelligence for integrated chemical safety assessment using OECD QSAR Toolbox](https://doi.org/10.1016/j.comtox.2025.100395).

---

## Feature snapshot

| Capability | Description |
| --- | --- |
| 🧬 **QSAR Workflow Automation** | Calls the OECD QSAR Toolbox WebAPI to run searches, profilers, metabolism simulators, and curated QSAR models. |
| 🧾 **Regulatory-Ready Reporting** | Generates a comprehensive PDF (ReportLab), Markdown narrative, and JSON provenance bundle. |
| 🔐 **Enterprise Security** | OAuth2/OIDC token validation, RBAC per tool, audit logging, Docker hardening. |
| ⚙️ **MCP Native** | Full JSON‑RPC 2.0 compliance with `initialize`, `listTools`, `callTool`, `shutdown`. |
| 🤖 **Agent Friendly** | Tested with Claude Code, Codex CLI, and Gemini CLI (see [integration guide](docs/integration_guides/mcp_integration.md)). |

---

## Table of contents

1. [Quick start](#quick-start)
2. [Related resources](#related-resources)
3. [Configuration](#configuration)
4. [Tool catalog](#tool-catalog)
5. [Running the server](#running-the-server)
6. [Integrating with coding agents](#integrating-with-coding-agents)
7. [Output artifacts](#output-artifacts)
8. [Security checklist](#security-checklist)
9. [Development notes](#development-notes)
10. [Roadmap](#roadmap)
11. [License](#license)

---

## Quick start

```bash
git clone https://github.com/senseibelbi/O_QT_MCP.git
cd O_QT_MCP/o-qt-mcp-server
poetry install
cp .env.example .env
poetry run uvicorn src.api.server:app --reload
```

> **Important:** The server needs access to a running OECD QSAR Toolbox WebAPI instance (typically on a Windows host). Set `QSAR_TOOLBOX_API_URL` in `.env` to point to it.

Once running, your MCP host connects to `http://localhost:8001/mcp`.

---

## Related resources

- **Original interactive UI (Streamlit app):** [VHP4Safety/O-QT-OECD-QSAR-Toolbox-AI-assistant](https://github.com/VHP4Safety/O-QT-OECD-QSAR-Toolbox-AI-assistant)
- **Peer-reviewed publication:** [Artificial intelligence for integrated chemical safety assessment using OECD QSAR Toolbox](https://doi.org/10.1016/j.comtox.2025.100395)

---

## Verification (smoke test)

Once the server is running:

```bash
# health
curl -s http://localhost:8001/health | jq .

# list MCP tools
curl -s http://localhost:8001/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | jq .
```

## Configuration

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `QSAR_TOOLBOX_API_URL` | ✅ | `http://localhost:5000` | Base URL to the OECD QSAR Toolbox WebAPI. |
| `AUTH_OIDC_ISSUER` | ✅ (prod) | – | OIDC issuer URL (Auth0, Keycloak, etc.). |
| `AUTH_OIDC_AUDIENCE` | ✅ (prod) | – | Expected audience in access tokens. |
| `AUTH_OIDC_ALGORITHMS` | ✅ (prod) | `["RS256"]` | Allowed JWT algorithms. |
| `AUTH_ROLE_CLAIM_PATH` | Optional | `roles` | Dot path to extract role claims from the JWT. |
| `BYPASS_AUTH` | Dev only | `false` | When `true`, skips auth and injects a `SYSTEM_BYPASS` role. |
| `AUTH_JWKS_CACHE_TTL_SECONDS` | Optional | `300` | TTL for JWKS cache. |
| `LOG_LEVEL` | Optional | `INFO` | Log verbosity. |
| `ENVIRONMENT` | Optional | `development` | Included in logs and `/health` response. |
| `ASSISTANT_PROVIDER` | Optional | – | Set to `OpenAI` or `OpenRouter` to enable the legacy O-QT multi-agent workflow. |
| `ASSISTANT_MODEL` | Optional | `gpt-4.1-nano` | LLM identifier to use when the assistant path is enabled. |
| `ASSISTANT_API_KEY` | Optional | – | API key for the selected provider. Falls back to `OPENAI_API_KEY` / `OPENROUTER_API_KEY` if absent. |

See [docs/auth_testing.md](docs/auth_testing.md) for token generation tips and bypass mode safety.

---

## Tool catalog

| Tool | Description |
| --- | --- |
| `run_oqt_multiagent_workflow` | Executes the full O-QT multi-agent pipeline (search + profiling + optional QSAR) and returns structured JSON results, Markdown narrative, and a PDF report. |
| `list_profilers` | Lists profilers configured inside the OECD QSAR Toolbox. |
| `get_profiler_info` | Provides metadata, categories, and literature links for a specific profiler. |
| `list_simulators` | Lists metabolism simulators (e.g., liver, skin, microbial). |
| `get_simulator_info` | Provides detailed information for a simulator GUID. |
| `list_calculators` | Lists calculator modules for physicochemical property estimation. |
| `get_calculator_info` | Returns description, units, and notes for a calculator. |
| `get_endpoint_tree` | Returns the endpoint taxonomy used to organise profilers and models. |
| `get_metadata_hierarchy` | Returns the metadata hierarchy useful for filtering experimental data. |
| `list_qsar_models` | Lists QSAR models for a specific endpoint tree position. |
| `list_all_qsar_models` | Enumerates the full QSAR catalog across the endpoint tree (deduplicated). |
| `list_search_databases` | Enumerates searchable inventories in the QSAR Toolbox. |
| `run_qsar_model` | Runs a specific QSAR model for a chemId and reports applicability domain status. |
| `run_profiler` | Executes a profiler for a chemId (optionally providing a simulator). |
| `run_metabolism_simulator` | Runs a metabolism simulator using either a chemId or SMILES. |
| `download_qmrf` | Retrieves the QMRF report for a QSAR model. |
| `download_qsar_report` | Retrieves the QSAR prediction report produced by the Toolbox. |
| `execute_workflow` | Runs a Toolbox workflow for a chemId. |
| `download_workflow_report` | Retrieves a workflow execution report. |
| `group_chemicals_by_profiler` | Builds read-across groups for a chemId using a profiler GUID. |
| `canonicalize_structure` | Returns the canonical SMILES for a structure. |
| `structure_connectivity` | Returns the connectivity string for the supplied SMILES. |
| `render_pdf_from_log` | Generates the regulatory PDF from a stored comprehensive log (no rerun). |

### `run_oqt_multiagent_workflow` parameters

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `identifier` | string | ✅ | Chemical identifier (name, CAS, or SMILES). |
| `search_type` | enum(`name`, `cas`, `smiles`) | ✅ | How to interpret `identifier`. |
| `context` | string | – | Free-form text describing the analysis context. |
| `profiler_guids` | array[string] | – | Explicit profilers to run. |
| `qsar_mode` | enum(`recommended`,`all`,`none`) | – | QSAR preset (defaults to curated `recommended`). |
| `qsar_guids` | array[string] | – | Exact QSAR model GUIDs. |
| `simulator_guids` | array[string] | – | Metabolism simulators to execute. |
| `llm_provider` | string | – | Override LLM provider (e.g., `openai`, `openrouter`). |
| `llm_model` | string | – | LLM model identifier. |
| `llm_api_key` | string | – | API key when not provided via environment. |

### Response payload

```jsonc
{
  "status": "ok",
  "identifier": "Acetone",
  "summary_markdown": "...",
  "log_json": { "...": "..." },
  "pdf_report_base64": "JVBERi0xLjcKJ..."
}
```

- `summary_markdown` – same narrative presented in the assistant UI.
- `log_json` – comprehensive bundle. When the assistant workflow runs, the payload includes:  
  - `assistant_session` (provider/model, duration, specialist outputs)  
  - `mcp_workflow` (deterministic fallback summary and Toolbox metadata)  
  - `analysis`, `data_retrieval`, and other sections reused by the original app.
- `pdf_report_base64` – base64-encoded, publication-ready PDF.

---

## Running the server

### Local development (Poetry)

```bash
poetry install
poetry run uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --reload
```

### Quick MCP smoke test

Once the server is running on `http://localhost:8001/mcp` (and your `.env` points to a reachable Toolbox WebAPI), the following curl invocations exercise the main tools with Benzene as an example:

```bash
# 1. Handshake and tool discovery
curl -s http://localhost:8001/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"capabilities":{}}}'

curl -s http://localhost:8001/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"mcp/tool/list","params":{}}' | jq '.result.tools | length'

# 2. Resolve Benzene and pull discovery metadata
curl -s http://localhost:8001/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":3,"method":"mcp/tool/call","params":{"name":"search_chemicals","parameters":{"query":"Benzene","search_type":"name"}}}' | jq '.result[0]'

curl -s http://localhost:8001/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":4,"method":"mcp/tool/call","params":{"name":"list_profilers","parameters":{}}}' | jq '.result.profilers[:5]'

# 3. Execute profilers / QSAR workflow (uses chemId from the first search hit)
BENZENE_CHEMID="019a0835-99ea-7828-a2a1-2821354f4753"
PROFILER_GUID="a06271f5-944e-4892-b0ad-fa5f7217ec14"

curl -s http://localhost:8001/mcp \
  -H 'Content-Type: application/json' \
  -d "{\"jsonrpc\":\"2.0\",\"id\":5,\"method\":\"mcp/tool/call\",\"params\":{\"name\":\"run_profiler\",\"parameters\":{\"profiler_guid\":\"$PROFILER_GUID\",\"chem_id\":\"$BENZENE_CHEMID\"}}}" | jq '.result.result'

curl -s http://localhost:8001/mcp \
  -H 'Content-Type: application/json' \
  -d "{\"jsonrpc\":\"2.0\",\"id\":6,\"method\":\"mcp/tool/call\",\"params\":{\"name\":\"run_oqt_multiagent_workflow\",\"parameters\":{\"identifier\":\"Benzene\",\"search_type\":\"name\",\"profiler_guids\":[\"$PROFILER_GUID\"]}}}" | jq '{status: .result.status, summary: .result.summary_markdown, pdf_bytes: (.result.pdf_report_base64 | length)}'

# 4. Optional helpers
curl -s http://localhost:8001/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":7,"method":"mcp/tool/call","params":{"name":"canonicalize_structure","parameters":{"smiles":"c1ccccc1"}}}'
```

You should see:

- Tool listing reporting 27 tools.
- `search_chemicals` resolving Benzene to a Toolbox `chemId`.
- Profiler execution returning the “Class 1 (narcosis or baseline toxicity)” call.
- `run_oqt_multiagent_workflow` producing a Markdown summary along with a non-empty Base64 PDF payload (written to disk automatically when invoked via Codex, Claude, or Gemini CLIs).

### Docker

```bash
docker build -t o-qt-mcp-server .
docker run -d --name o-qt-mcp \
  --env-file .env \
  -p 8000:8000 \
  o-qt-mcp-server
```

### Optional: Enable the legacy O-QT assistant workflow

The MCP can reuse the multi-agent prompts and PDF template from the original O-QT assistant. Configure the following before starting the server:

```bash
export ASSISTANT_PROVIDER=OpenAI               # or OpenRouter
export ASSISTANT_MODEL=gpt-4.1-nano            # any model supported by the provider
export ASSISTANT_API_KEY=sk-...                # falls back to OPENAI_API_KEY/OPENROUTER_API_KEY
```

With these variables set, `run_oqt_multiagent_workflow` will call the same specialist agents used by the Streamlit app, return the full assistant transcript inside `log_json.assistant_session`, and embed the assistant-generated PDF in `pdf_report_base64`. If the assistant cannot run (missing key, upstream error, etc.) the MCP automatically falls back to the deterministic summary.

### Docker Compose (with Toolbox stub)

```bash
docker compose up --build
```

This launches:

| Service | Purpose | Port |
| --- | --- | --- |
| `mcp-server` | The MCP server | 8000 |
| `toolbox-stub` | Mock Toolbox WebAPI for demos | 5000 |

Update `.env` to point at a real Toolbox instance before production use.

---

## Integrating with coding agents

Follow [docs/integration_guides/mcp_integration.md](docs/integration_guides/mcp_integration.md) for step-by-step instructions covering:

- Claude Code / Cursor
- Codex CLI
- Gemini CLI
- Generic MCP hosts

Each guide includes JSON snippets for provider configuration and tips for handling OAuth tokens.

---

## Output artifacts

Every successful run returns three artifacts:

1. **JSON log** – Raw payloads from the QSAR Toolbox plus the specialist agent outputs.
2. **Markdown narrative** – Human-readable synthesis suitable for reports or version control.
3. **PDF report** – Built with ReportLab; includes provenance tables, key study badges, and optional logo.

Consumers can store the PDF by decoding `pdf_report_base64` from the tool response.

---

## Security checklist

- ✅ Use OAuth2/OIDC in production (`BYPASS_AUTH=false`).
- ✅ Terminate TLS at a reverse proxy.
- ✅ Configure RBAC in `config/tool_permissions.default.json`.
- ✅ Enable audit log shipping (see [docs/observability.md](docs/observability.md)).
- ✅ Rotate secrets via platform-specific secret stores.
- ✅ Regularly update the Docker base image (see [Dockerfile](Dockerfile)).

---

## Development notes

| Command | Purpose |
| --- | --- |
| `poetry run pytest` | Run the full test suite. |
| `poetry run pytest tests/auth -q` | Focus on authentication tests. |
| `poetry run black . && poetry run isort .` | Format code. |
| `docker compose up --build` | Local stack with Toolbox stub. |

Additional documentation:

- [docs/testing.md](docs/testing.md) – local tooling and CI details.
- [docs/release_process.md](docs/release_process.md) – versioning and release checklist.
- [docs/toolbox_webapi_overview.md](docs/toolbox_webapi_overview.md) – mapping MCP tools to Toolbox endpoints.
- [SECURITY.md](SECURITY.md) – vulnerability reporting policy.

---

## Roadmap

- Streaming progress updates over MCP notifications for long-running QSAR jobs.
- Additional tools for ad-hoc discovery (e.g., list profilers, fetch model metadata without running full pipeline).
- Optional job queue and persistence layer for asynchronous execution.

Community feedback and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for details.

---

## License

This project is released under the [Apache License 2.0](LICENSE).  

_OECD QSAR Toolbox is proprietary software. Users must supply their own licensed installations and comply with the OECD EULA._
## Acknowledgements / Origins

ToxMCP was developed in the context of the **VHP4Safety** project (see: https://github.com/VHP4Safety) and related research/engineering efforts.

Funding: Dutch Research Council (NWO) — NWA.1292.19.272 (NWA programme)

This suite integrates with third-party data sources and services (e.g., EPA CompTox, ADMETlab, AOP resources, OECD QSAR Toolbox, Open Systems Pharmacology). Those upstream resources are owned and governed by their respective providers; users are responsible for meeting any access, API key, rate limit, and license/EULA requirements described in each module.

## ✅ Citation

Djidrovski, I. **ToxMCP: Guardrailed, Auditable Agentic Workflows for Computational Toxicology via the Model Context Protocol.** bioRxiv (2026). https://doi.org/10.64898/2026.02.06.703989

```bibtex
@article{djidrovski2026toxmcp,
  title   = {ToxMCP: Guardrailed, Auditable Agentic Workflows for Computational Toxicology via the Model Context Protocol},
  author  = {Djidrovski, Ivo},
  journal = {bioRxiv},
  year    = {2026},
  doi     = {10.64898/2026.02.06.703989},
  url     = {https://doi.org/10.64898/2026.02.06.703989}
}
```

Citation metadata: [`CITATION.cff`](./CITATION.cff)

