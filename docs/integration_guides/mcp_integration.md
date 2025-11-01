# Integrating the O-QT MCP Server with Coding Agents

The O-QT MCP server implements the Model Context Protocol (MCP) over HTTP, so any MCP-compatible IDE agent can connect and issue tool calls. This guide covers integration with popular environments.

## Prerequisites

1. Deploy the MCP server (Docker or bare-metal) and expose the `/mcp` JSON-RPC endpoint.
2. Configure authentication:
   - In development, `BYPASS_AUTH=true` is acceptable.
   - For production, set the OIDC issuer/audience and provide an API gateway or reverse proxy with TLS and authentication headers.
3. Ensure the server can reach the OECD QSAR Toolbox WebAPI and that the MCP host has network access to the MCP server.

Typical server address:

```
https://mcp.example.org/mcp
```

Replace with `http://localhost:8000/mcp` if running locally.

## Claude Code (Cursor / VS Code with Claude MCP)

1. Open your Claude MCP settings (e.g., `~/.config/claude/mcp.json` for CLI or the MCP panel in Cursor).
2. Add a new HTTP provider entry:

```json
{
  "name": "oqt-mcp",
  "type": "http",
  "url": "https://mcp.example.org/mcp",
  "headers": {
    "Authorization": "Bearer <YOUR_OIDC_ACCESS_TOKEN>"
  },
  "capabilities": {}
}
```

3. Reload the MCP session; Claude Code should list the “O-QT MCP Server” toolset. Invoke tools such as `run_qsar_workflow` directly from the chat sidebar and download any returned PDF attachments.

### Local Development Tip

When running both Claude and the MCP server locally, use `http://localhost:8000/mcp`. If Claude runs inside a container, expose the host port and update the URL accordingly.

## Codex CLI (OpenAI MCP client)

1. Edit `~/.config/openai/mcp.json` (or the path reported by `codex --show-config`):

```json
{
  "providers": [
    {
      "name": "oqt-mcp",
      "type": "http",
      "url": "https://mcp.example.org/mcp",
      "headers": {
        "Authorization": "Bearer <YOUR_OIDC_ACCESS_TOKEN>"
      }
    }
  ]
}
```

2. Restart the CLI. You can now run:

```bash
codex tools list
codex tools call oqt-mcp run_qsar_workflow --identifier "Acetone" --search-type name
```

If the tool returns binary payloads (PDF), Codex CLI stores them in the outputs directory (displayed in the command response).

## Gemini CLI (Workspace agents)

1. Update Gemini’s MCP providers configuration (normally `~/.config/gemini/mcp.json`):

```json
{
  "providers": {
    "oqt-mcp": {
      "transport": "http",
      "endpoint": "https://mcp.example.org/mcp",
      "headers": {
        "Authorization": "Bearer <YOUR_OIDC_ACCESS_TOKEN>"
      }
    }
  }
}
```

2. Restart the Gemini CLI; the O-QT tools should appear when you list providers:

```bash
gemini mcp providers
gemini mcp call oqt-mcp run_qsar_workflow --identifier "Acetone"
```

## Other MCP Hosts

- Most MCP implementations use a similar JSON config with `name`, `type`/`transport`, `url`/`endpoint`, and optional headers.
- Include the `Authorization` header only if the server requires OAuth access tokens. For development with `BYPASS_AUTH=true`, omit the header.
- If your host trusts environment variables, you can set `MCP_OQT_MCP_URL` (or similar) and reference it in the JSON configuration.

## Testing the Connection

1. After adding the provider, list tools (`tools.list` call).
2. Invoke `server.ping` or `server.getStatus` (depending on host implementation) to confirm connectivity.
3. Run discovery calls such as `list_profilers`, `list_simulators`, or `list_qsar_models` to verify Toolbox connectivity.
4. Trigger the full workflow (`run_qsar_workflow`) with a simple identifier and verify the JSON response plus generated PDF.

## Frequently Asked Questions

**Why do I need an access token?**  
The MCP server enforces OAuth/OIDC in production. Obtain a confidential client token (or configure BYPASS_AUTH for local development).

**Where are PDFs saved?**  
Hosts usually return binary files as base64 strings. Agents like Claude or Codex will offer a download link, or write the file into their working directory.

**Can multiple agents share the same MCP server?**  
Yes. Each tool call is stateless except for the underlying QSAR Toolbox request. For multi-tenant deployments, ensure RBAC roles and rate limits are configured per agent.
