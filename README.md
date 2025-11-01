# O-QT OECD QSAR Toolbox - MCP Server

This repository contains the boilerplate implementation of a Model Context Protocol (MCP) server for the O-QT OECD QSAR Toolbox. It is designed based on the principles outlined in "Architecting the Future of Agent-Driven Science," focusing on security, interoperability, and robustness.

## Features

*   **MCP Compliance:** Implements the JSON-RPC 2.0 specification for MCP communication over HTTP.
*   **Security First (Zero Trust Architecture):**
    *   **Authentication (Section 2.2):** Boilerplate for OAuth 2.0/OIDC integration (Auth0/Keycloak).
    *   **Authorization (Section 2.2):** Fine-grained Role-Based Access Control (RBAC) at the tool level.
    *   **Sandboxing (Section 2.4):** Dockerized using a multi-stage build, running as a non-root user.
*   **Interoperability (Section 3.1):** Uses FastAPI which supports OpenAPI Specification (OAS) principles.
*   **Robustness (Section 3.3):** Structured JSON logging, comprehensive error handling.

## Prerequisites

*   Python 3.10+
*   Poetry (for dependency management)
*   Docker
*   A running instance of the OECD QSAR Toolbox Web API (for the O-QT connection)

## Setup

1.  **Clone the repository:**
    ```bash
    git clone <your-repo-url>
    cd o-qt-mcp-server
    ```

2.  **Install dependencies:**
    ```bash
    poetry install
    ```

3.  **Configure Environment Variables:**
    Copy `.env.example` to `.env` and fill in the required configurations.

    ```bash
    cp .env.example .env
    ```
    **Crucial:** Configure the OIDC settings for security and the `QSAR_TOOLBOX_API_URL`.

4.  **Run the server (Development):**
    ```bash
    poetry run uvicorn src.api.server:app --reload
    ```

## Running with Docker (Production/Sandboxed)

1.  **Build the Docker image:**
    ```bash
    docker build -t o-qt-mcp-server .
    ```

2.  **Run the container:**
    ```bash
    docker run -d --name o-qt-mcp -p 8000:8000 --env-file .env o-qt-mcp-server
    ```

## Local Stack with Docker Compose

For end-to-end testing without a live OECD QSAR Toolbox instance, the repository includes a `docker-compose.yml` that pairs the MCP server with a lightweight Toolbox API stub.

```bash
docker compose up --build
```

* `mcp-server` is built from the local Dockerfile and exposes port `8000`.
* `toolbox-stub` is a placeholder service (ghcr.io/senseibelbi/qsar-toolbox-stub) listening on port `5000`.
* The MCP container overrides `QSAR_TOOLBOX_API_URL` to reference the stub and sets `BYPASS_AUTH=true` for local development convenience. Adjust or remove these overrides when integrating with real infrastructure.

To point at a real Toolbox deployment, update `QSAR_TOOLBOX_API_URL` in `.env` or via compose overrides, and disable authentication bypass.

## Architecture Overview

The server is built using FastAPI and Pydantic.

*   `src/config/settings.py`: Centralized configuration management (Pydantic Settings).
*   `src/mcp/`: Core MCP protocol handling (JSON-RPC router, protocol models).
*   `src/auth/`: Authentication (OIDC) and Authorization (RBAC) services.
*   `src/tools/`: Tool definitions, registry, and implementations.

### MCP Capability Negotiation

The `/mcp` endpoint follows the JSON-RPC 2.0 transport used by MCP hosts:

* `initialize` – Clients send capabilities; the server returns `protocolVersion` (current value `2025-03-26`) and the features it supports. Tooling is enabled; resources, prompts, and sampling are disabled.
* `initialized` – Notification acknowledged; no response body (HTTP 204).
* `shutdown` / `exit` – Clean shutdown semantics. `exit` is treated as a no-op acknowledgement (HTTP 204).

Additional notes:

* **Batch requests are not supported.** If the server receives a JSON array payload it responds with error code `-32600 (Invalid Request)`.
* Notification requests (no `id`) return HTTP 204 with no body.
* Successful calls that produce no payload return a JSON-RPC success response with `result: null`.

## Next Steps

1.  **Implement QSAR Logic:** Implement the actual QSAR analysis logic within `src/tools/implementations/o_qt_qsar_tools.py`, connecting to the QSAR Toolbox Web API.
2.  **Configure Security:** Define the precise RBAC roles in `src/auth/rbac.py` and ensure OIDC details in `.env` are correct. Set `BYPASS_AUTH=False` for production.
3.  **Audit Logging:** Enhance the audit logging middleware in `src/api/server.py` to ensure immutable traceability (Section 2.3).

Refer to:
- `docs/auth_testing.md` for detailed OIDC configuration, token generation tips, and test utilities.
- `docs/observability.md` for audit/correlation-id behaviour and guidance on wiring custom sinks.
- `docs/testing.md` for local tooling, pytest commands, and CI details.
