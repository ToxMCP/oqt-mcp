# Stable SDK2 migration and hosting

The unreleased v0.4.0 candidate uses `mcp==2.2.0`. Modern clients use protocol `2026-07-28` at the existing `/mcp` URL. Handshake-era clients retain protocol `2025-03-26`, initialization/notification behavior and `mcp/tool/list` / `mcp/tool/call` aliases. No deployment, package publication or live Toolbox qualification is implied by this candidate.

## Authentication and roles

Modern HTTP authenticates protected methods through the same OIDC implementation as legacy HTTP, including its configured JWT algorithm allowlist, required claims, JWKS caching and per-tool role policy. Missing/invalid credentials return HTTP 401. Discovery for each role retains the released tool names, schemas and descriptions. Catalog cache hints are private and zero-TTL; permissions are checked per request. Modern server discovery remains public, like the released initialization handshake.

Local stdio runs with `python -m src.mcp.sdk2`. Set `MCP_STDIO_BEARER_TOKEN` privately to a valid OIDC bearer token, alongside the existing issuer/audience settings. Stdio uses the same token and role checks, with privacy-filtered logs on stderr. The existing explicit development `BYPASS_AUTH` setting keeps its existing meaning; the adapter never enables it automatically.

## HTTP hosting

Set comma-separated `MCP_ALLOWED_HOSTS` and `MCP_ALLOWED_ORIGINS` for the gateway and browser origins before deployment. Empty defaults accept loopback authorities/origins with any port. Modern SDK Host/Origin guards operate independently of existing development CORS. Browser preflights allow `MCP-Protocol-Version`, `Mcp-Method` and `Mcp-Name`; SDK clients supply matching header/body routing information.

`MCP_MAX_REQUEST_BYTES` defaults to 4194304 and must be positive. Both protocol parsers bound the actual body before JSON parsing, including chunked requests, malformed lengths and understated lengths. Raise it explicitly if a trusted existing workflow needs larger log bundles.

## Scientific and review preservation

Both adapters use the existing registry and workflow functions. Applicability-domain status/warnings/recommendations, default name searches, provenance, LLM sanitization, privacy audit and fallback PDF warnings stay in those functions. Pending `chemical_identity`, `ad_assessment` and `final_report` checkpoints continue to return `review_required` and block PDF generation. SDK2 does not auto-approve them. Durable tasks, elicitation and Apps require separate implementation work.

The repository remains a source/container project with Poetry package mode disabled. Run `poetry install --no-root --with dev`; no wheel distribution is introduced. CI runs actual SDK1/SDK2 clients over stdio and HTTP outside the checkout, using only explicit test authentication and synthetic Toolbox responses through the real client. Fixed application clocks/UUIDs and durations are installed only by the test launcher. Production never imports it.

The real-client gate checks five workflows, including out-of-domain prediction and all three pending review checkpoints. It compares complete application text/JSON and eleven provider requests, excluding only validated SDK identity/result-envelope fields. Synthetic fixtures prove protocol and control preservation; they do not establish live Toolbox/model qualification.
