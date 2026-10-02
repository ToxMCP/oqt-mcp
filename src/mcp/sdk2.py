"""Stable SDK adapter retaining OQT's authentication, RBAC and workflow handlers."""

from __future__ import annotations

import sys
from typing import Any, Awaitable, Callable

import anyio
from fastapi import HTTPException
from mcp_types import (
    PROTOCOL_VERSION_META_KEY,
    CallToolRequestParams,
    CallToolResult,
    GetPromptRequestParams,
    ListPromptsResult,
    ListToolsResult,
    PaginatedRequestParams,
    Tool,
)
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from mcp.server.caching import CacheHint
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.server.transport_security import TransportSecuritySettings
from mcp.shared.exceptions import MCPError
from src.config.settings import settings

LEGACY_REVISIONS = {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"}


def is_modern_request(request: Request, payload: dict[str, Any]) -> bool:
    revision = request.headers.get("mcp-protocol-version")
    if revision and revision not in LEGACY_REVISIONS:
        return True
    params = payload.get("params")
    metadata = params.get("_meta") if isinstance(params, dict) else None
    return isinstance(metadata, dict) and PROTOCOL_VERSION_META_KEY in metadata


async def authenticated(context: ServerRequestContext):
    from src.mcp import router as legacy

    request = context.request
    if request is None:
        token = settings.security.MCP_STDIO_BEARER_TOKEN
        headers = (
            []
            if token is None
            else [(b"authorization", ("Bearer " + token.get_secret_value()).encode())]
        )
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/mcp",
                "headers": headers,
                "state": {},
                "query_string": b"",
            }
        )
    verified = getattr(request.state, "sdk2_user", None)
    return verified if verified is not None else await legacy.get_current_user(request)


async def expected_errors(operation: Callable[[], Awaitable[Any]]):
    from src.mcp.router import JSONRPCDispatchError

    try:
        return await operation()
    except HTTPException as error:
        raise MCPError(
            -32000 if error.status_code == 401 else -32001,
            (
                "Authentication required."
                if error.status_code == 401
                else "Access denied."
            ),
        ) from error
    except JSONRPCDispatchError as error:
        # Keep expected error codes, without propagating provider/input details.
        messages = {
            -32601: "Method or tool not found.",
            -32602: "Invalid method parameters.",
            -32001: "Access denied.",
            -32002: "Tool execution failed.",
        }
        raise MCPError(
            error.code, messages.get(error.code, "Request failed.")
        ) from error


def create_sdk_server() -> Server:
    from src.mcp import router as legacy

    async def list_tools(
        context: ServerRequestContext, params: PaginatedRequestParams | None
    ) -> ListToolsResult:
        async def operation():
            user = await authenticated(context)
            result = legacy.handle_list_tools(user)
            return ListToolsResult(
                tools=[
                    Tool.model_validate(item.model_dump(by_alias=True))
                    for item in result.tools
                ]
            )

        return await expected_errors(operation)

    async def call_tool(
        context: ServerRequestContext, params: CallToolRequestParams
    ) -> CallToolResult:
        async def operation():
            user = await authenticated(context)
            result = await legacy.handle_call_tool(
                {"name": params.name, "arguments": params.arguments or {}}, user
            )
            return CallToolResult.model_validate(result)

        return await expected_errors(operation)

    async def prompts(
        context: ServerRequestContext, params: PaginatedRequestParams | None
    ) -> ListPromptsResult:
        async def operation():
            await authenticated(context)
            return ListPromptsResult.model_validate(legacy.handle_list_prompts())

        return await expected_errors(operation)

    async def get_prompt(context: ServerRequestContext, params: GetPromptRequestParams):
        async def operation():
            await authenticated(context)
            return legacy.handle_get_prompt({"name": params.name})

        return await expected_errors(operation)

    return Server(
        legacy.SERVER_INFO.name,
        version=legacy.SERVER_INFO.version,
        on_list_tools=list_tools,
        on_call_tool=call_tool,
        on_list_prompts=prompts,
        on_get_prompt=get_prompt,
        cache_hints={
            method: CacheHint(ttl_ms=0, scope="private")
            for method in ["tools/list", "prompts/list"]
        },
    )


def create_sdk_http_app():
    def split(value):
        return [part.strip() for part in (value or "").split(",") if part.strip()]

    return create_sdk_server().streamable_http_app(
        json_response=True,
        stateless_http=True,
        max_request_body_size=settings.security.MCP_MAX_REQUEST_BYTES,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=split(settings.security.MCP_ALLOWED_HOSTS)
            or ["localhost:*", "127.0.0.1:*", "[::1]:*"],
            allowed_origins=split(settings.security.MCP_ALLOWED_ORIGINS)
            or ["http://localhost:*", "http://127.0.0.1:*", "http://[::1]:*"],
        ),
    )


class SDKResponse(Response):
    def __init__(self, application: ASGIApp, body: bytes):
        super().__init__()
        self.application = application
        self.body = body

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        supplied = False

        async def replay():
            nonlocal supplied
            if not supplied:
                supplied = True
                return {"type": "http.request", "body": self.body, "more_body": False}
            return await receive()

        await self.application(scope, replay, send)


async def serve_stdio():
    # Import registers the same production tools and privacy-aware logging filters.
    from src.api import server as application
    from src.utils.logging import setup_logging

    setup_logging(stream=sys.stderr)
    async with application.lifespan(application.app):
        server = create_sdk_server()
        async with stdio_server() as (reader, writer):
            await server.run(reader, writer, server.create_initialization_options())


def main():
    # Move import-time registration logs off the protocol stdout stream too.
    protocol_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        from src.api import server as application
        from src.utils.logging import setup_logging

        setup_logging(stream=sys.stderr)
    finally:
        sys.stdout = protocol_stdout
    anyio.run(serve_stdio)


if __name__ == "__main__":
    main()
