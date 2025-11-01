# O-QT MCP Server

**Public MCP endpoint for the OECD QSAR Toolbox.**  
Run QSAR workflows, stream structured outputs, and download audit-ready PDF reports through any MCP-aware agent (Claude Code, Codex CLI, Gemini CLI, etc.).

## Why this project exists

Chemical safety work often relies on the proprietary OECD QSAR Toolbox desktop application. Scientists have to click through many screens to gather profilers, metabolism simulators, and QSAR predictions before writing regulatory reports.  

The O-QT MCP server turns that workflow into an **open, programmable interface**:

- **Single MCP tool (`run_qsar_workflow`)** orchestrates the same multi-agent pipeline used in the O-QT AI Assistant.
- **Structured JSON + Markdown + PDF** responses are returned in one call, ready for downstream automation.
- **Vendor-neutral** – any coding agent that speaks MCP can trigger analyses and capture outputs.

> Looking for the original assistant? The MCP server reuses the same core logic from [O-QT-OECD-QSAR-Toolbox-AI-assistant](https://github.com/VHP4Safety/O-QT-OECD-QSAR-Toolbox-AI-assistant) but wraps it in a secure, headless API designed for automation.

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
2. [Configuration](#configuration)
3. [Tool catalog](#tool-catalog)
4. [Running the server](#running-the-server)
5. [Integrating with coding agents](#integrating-with-coding-agents)
6. [Output artifacts](#output-artifacts)
7. [Security checklist](#security-checklist)
8. [Development notes](#development-notes)
9. [Roadmap](#roadmap)
10. [License](#license)

---

## Quick start

```bash
git clone https://github.com/senseibelbi/O_QT_MCP.git
cd o-qt-mcp-server
poetry install
cp .env.example .env
poetry run uvicorn src.api.server:app --reload
```

> **Important:** The server needs access to a running OECD QSAR Toolbox WebAPI instance (typically on a Windows host). Set `QSAR_TOOLBOX_API_URL` in `.env` to point to it.

Once running, your MCP host connects to `http://localhost:8000/mcp`.

---

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

See [docs/auth_testing.md](docs/auth_testing.md) for token generation tips and bypass mode safety.

---

## Tool catalog

| Tool | Description |
| --- | --- |
| `run_qsar_workflow` | Executes the full QSAR assistant pipeline, returning structured JSON results, Markdown narrative, and a PDF report. |

### `run_qsar_workflow` parameters

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
- `log_json` – comprehensive bundle (inputs, raw QSAR payloads, filtered data, agent outputs).
- `pdf_report_base64` – base64-encoded, publication-ready PDF.

---

## Running the server

### Local development (Poetry)

```bash
poetry install
poetry run uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --reload
```

### Docker

```bash
docker build -t o-qt-mcp-server .
docker run -d --name o-qt-mcp \
  --env-file .env \
  -p 8000:8000 \
  o-qt-mcp-server
```

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

---

## Roadmap

- Streaming progress updates over MCP notifications for long-running QSAR jobs.
- Additional tools for ad-hoc discovery (e.g., list profilers, fetch model metadata without running full pipeline).
- Optional job queue and persistence layer for asynchronous execution.

Community feedback and pull requests are welcome—see [CONTRIBUTING.md](CONTRIBUTING.md) for details.

---

## License

This project is released under the [MIT License](LICENSE).  

_OECD QSAR Toolbox is proprietary software. Users must supply their own licensed installations and comply with the OECD EULA._
