import json
import logging
from importlib import metadata
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import ValidationError

from src.auth.service import User, get_current_user
from src.mcp.protocol import (
    FORBIDDEN,
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    TOOL_EXECUTION_ERROR,
    UNAUTHORIZED,
    FeatureSupport,
    InitializeParams,
    InitializeResult,
    JSONRPCError,
    JSONRPCRequest,
    JSONRPCResponse,
    ListToolsResult,
    ServerInfo,
)
from src.tools.registry import InputValidationError, ToolNotFoundError, tool_registry

log = logging.getLogger(__name__)

router = APIRouter()

# Define the server features (Section 1.3)
SERVER_CAPABILITIES = {
    "tools": FeatureSupport(enabled=True),
    "resources": FeatureSupport(enabled=False),  # Not implemented in this boilerplate
    "prompts": FeatureSupport(enabled=True),
    # Sampling is disabled by default due to security risks (Section 2.1 - Puppet Attacks)
    "sampling": FeatureSupport(enabled=False),
}

try:
    _server_version = metadata.version("o-qt-mcp-server")
except metadata.PackageNotFoundError:
    _server_version = "0.1.0"

SERVER_INFO = ServerInfo(name="O-QT MCP Server", version=_server_version)

# MCP Specification Version implemented by this server
MCP_VERSION = "2025-03-26"


@router.post(
    "/mcp",
    responses={204: {"description": "Notification (no response)"}},
)
async def mcp_endpoint(request: Request, response: Response):
    """
    The main MCP endpoint handling JSON-RPC requests over HTTP (Section 1.2).
    """
    body = None
    try:
        # 1. Parse JSON
        try:
            body = await request.json()
            if isinstance(body, list):
                raise ValueError("Batch requests are not supported by this MCP server.")
            if not isinstance(body, dict):
                raise ValueError("Request body must be a JSON object.")
        except Exception as e:
            log.error(f"Invalid JSON received: {e}")
            response.status_code = status.HTTP_400_BAD_REQUEST
            error_code = PARSE_ERROR if not isinstance(body, list) else INVALID_REQUEST
            error_message = (
                "Batch requests are not supported."
                if isinstance(body, list)
                else "Parse error: Invalid JSON received."
            )
            return create_error_response(error_code, error_message, None)

        # 2. Validate JSON-RPC Structure
        try:
            json_rpc_request = JSONRPCRequest.model_validate(body)
        except ValidationError as e:
            log.error(f"Invalid JSON-RPC Request structure: {e}")
            response.status_code = status.HTTP_400_BAD_REQUEST
            return create_error_response(
                INVALID_REQUEST, f"Invalid Request: {e}", body.get("id")
            )

        # 3. Dispatch the request
        result = await dispatch_request(json_rpc_request, request)

        # 4. Handle Notifications (Requests without an ID)
        if json_rpc_request.id is None:
            response.status_code = status.HTTP_204_NO_CONTENT
            return None

        # 5. Return Success Response
        return create_success_response(result, json_rpc_request.id)

    except JSONRPCDispatchError as exc:
        # Handle expected JSON-RPC errors during dispatch
        # Set the HTTP status based on the error type, although JSON-RPC often uses 200 OK
        if exc.code in [UNAUTHORIZED, FORBIDDEN]:
            response.status_code = (
                status.HTTP_403_FORBIDDEN
                if exc.code == FORBIDDEN
                else status.HTTP_401_UNAUTHORIZED
            )
        elif exc.code == METHOD_NOT_FOUND:
            response.status_code = status.HTTP_404_NOT_FOUND
        elif exc.code in [INVALID_PARAMS, INVALID_REQUEST]:
            response.status_code = status.HTTP_400_BAD_REQUEST

        return handle_dispatch_error(exc, body)

    except HTTPException as exc:
        # Handle FastAPI authentication exceptions and convert them to JSON-RPC errors
        log.warning(f"Authentication/Authorization HTTP error: {exc.detail}")
        code = (
            UNAUTHORIZED
            if exc.status_code == status.HTTP_401_UNAUTHORIZED
            else FORBIDDEN
        )
        request_id = body.get("id") if isinstance(body, dict) else None
        response.status_code = exc.status_code
        return create_error_response(code, exc.detail, request_id)

    except Exception as e:
        # Handle unexpected internal errors
        log.exception("An unexpected internal error occurred.")
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        request_id = body.get("id") if isinstance(body, dict) else None
        return create_error_response(
            INTERNAL_ERROR,
            f"Internal server error: {type(e).__name__}",
            request_id,
            data=str(e),
        )


async def dispatch_request(request: JSONRPCRequest, http_request: Request) -> Any:
    """Dispatches the JSON-RPC request to the appropriate method handler."""
    method = request.method
    params = request.params or {}

    # Ensure params is a dictionary for standardization
    if isinstance(params, list):
        raise JSONRPCDispatchError(
            INVALID_PARAMS,
            "Positional parameters (arrays) are not supported by this server.",
        )

    log.debug(f"Dispatching method: {method}")

    # --- MCP Lifecycle Methods (No Auth Required) ---
    if method == "initialize":
        return handle_initialize(params)
    elif method in {"initialized", "notifications/initialized"}:
        return handle_initialized()
    elif method == "shutdown":
        return handle_shutdown()
    elif method == "exit":
        # Exit is often handled by the transport layer, but we acknowledge it
        log.info("Exit notification received.")
        return None

    # --- Authentication Required Methods ---
    # Methods beyond this point require authentication. We resolve the user here.
    # This leverages the FastAPI dependency injection system implicitly via the Request object.
    user = await get_current_user(http_request)

    # --- Tool Methods ---
    if method in {"mcp/tool/list", "tools/list"}:
        return handle_list_tools(user)
    elif method in {"mcp/tool/call", "tools/call"}:
        return await handle_call_tool(params, user)
    elif method == "prompts/list":
        return handle_list_prompts()
    elif method == "prompts/get":
        return handle_get_prompt(params)

    # Method not found
    raise JSONRPCDispatchError(METHOD_NOT_FOUND, f"Method not found: {method}")


# --- Method Handlers ---


def handle_initialize(params: dict) -> InitializeResult:
    """Handles the 'initialize' request (Capability Negotiation - Section 1.3)."""
    try:
        init_params = InitializeParams.model_validate(params)
    except ValidationError as e:
        raise JSONRPCDispatchError(
            INVALID_PARAMS, f"Invalid initialize parameters: {e}"
        )

    log.info(f"Initializing session. Client capabilities: {init_params.capabilities}")
    # In a real implementation, you might adjust server features based on client capabilities.

    return InitializeResult(
        protocolVersion=MCP_VERSION,
        serverInfo=SERVER_INFO,
        capabilities=SERVER_CAPABILITIES,
    )


def handle_initialized():
    """Handles the 'initialized' notification."""
    log.info("Session initialized successfully.")
    # Some MCP clients (Codex CLI, Gemini CLI) send `initialized` as a request with
    # an `id` and expect a JSON-RPC result. Returning an explicit payload keeps them
    # satisfied while still being safe for clients that treat it as a notification.
    return {"status": "ok"}


def handle_shutdown():
    """Handles the 'shutdown' request."""
    log.info("Shutdown requested. Performing cleanup.")
    # Perform cleanup if necessary
    return None


def handle_list_tools(user: User) -> ListToolsResult:
    """Handles 'mcp/tool/list' request."""
    # List tools filtered by the user's permissions (Section 2.4)
    definitions = tool_registry.list_definitions(user)
    log.info(f"Listing {len(definitions)} tools available for user {user.id}")
    return ListToolsResult(tools=definitions)


def _looks_like_mcp_content(result: Any) -> bool:
    try:
        return (
            isinstance(result, dict)
            and isinstance(result.get("content"), list)
            and all(isinstance(item, dict) and "type" in item for item in result["content"])
        )
    except Exception:
        return False


async def handle_call_tool(params: dict, user: User) -> Any:
    """Handles 'mcp/tool/call' requests."""
    tool_name = params.get("name")
    tool_params = params.get("parameters", {})
    
    # Log the incoming request for debugging
    log.debug(f"Tool call request - name: {tool_name}, params keys: {list(params.keys())}, parameters: {tool_params}")

    if not tool_name or not isinstance(tool_name, str):
        raise JSONRPCDispatchError(
            INVALID_PARAMS, "Tool 'name' is missing or invalid in the request."
        )
    
    # Handle different parameter formats from various MCP clients
    if not tool_params or tool_params == {}:
        # Check for 'arguments' key (used by some MCP clients like Gemini CLI)
        if 'arguments' in params and isinstance(params['arguments'], dict):
            log.debug(f"Using 'arguments' key for tool '{tool_name}': {params['arguments']}")
            tool_params = params['arguments']
        else:
            # Check if there are other keys besides 'name', 'parameters', 'arguments' that could be the actual parameters
            potential_params = {k: v for k, v in params.items() if k not in ['name', 'parameters', 'arguments']}
            if potential_params:
                log.debug(f"Using top-level parameters for tool '{tool_name}': {potential_params}")
                tool_params = potential_params

    try:
        result = await tool_registry.execute(tool_name, tool_params, user)
        # Normalize tool output to MCP "content" shape for broad client compatibility.
        # If the tool already returned MCP content, pass through unchanged.
        if _looks_like_mcp_content(result):
            return result

        # Otherwise, wrap the returned JSON-compatible payload as text content.
        # Use "text" type instead of "json" for compatibility with Codex and Gemini CLI.
        # These clients expect standard MCP content types (text, image, resource, resource_link).
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2, ensure_ascii=False),
                }
            ]
        }
    except ToolNotFoundError:
        raise JSONRPCDispatchError(METHOD_NOT_FOUND, f"Tool not found: {tool_name}")
    except InputValidationError as e:
        # Pydantic validation failure (Section 2.3)
        raise JSONRPCDispatchError(
            INVALID_PARAMS, "Invalid tool parameters.", data=str(e)
        )
    except PermissionError as e:
        # RBAC failure (Section 2.2)
        log.warning(
            f"Permission denied for user {user.id} attempting to call tool '{tool_name}'"
        )
        raise JSONRPCDispatchError(FORBIDDEN, str(e))
    except Exception as e:
        # Catch-all for errors during tool execution (Section 3.3)
        log.exception(f"Error executing tool '{tool_name}'")
        # Provide a generic error message but include details in the data field for debugging
        raise JSONRPCDispatchError(
            TOOL_EXECUTION_ERROR,
            f"Error during execution of tool '{tool_name}'.",
            data=str(e),
        )


def handle_list_prompts() -> dict:
    """Handles 'prompts/list' by returning an empty catalog."""
    log.info("Prompts requested; none are configured for this server.")
    return {"prompts": []}


def handle_get_prompt(params: dict) -> dict:
    """Handles 'prompts/get' requests when no prompts exist."""
    name = params.get("name") if isinstance(params, dict) else None
    if not name:
        raise JSONRPCDispatchError(INVALID_PARAMS, "Prompt 'name' is required.")

    raise JSONRPCDispatchError(
        METHOD_NOT_FOUND,
        f"Prompt not found: {name}",
    )


# --- Helper Functions ---


class JSONRPCDispatchError(Exception):
    """Custom exception for errors during request dispatching."""

    def __init__(self, code: int, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)


def create_error_response(
    code: int, message: str, id: str | int | None, data: Any = None
) -> dict:
    """Creates a standardized JSON-RPC error response."""
    # Ensure the response adheres to the protocol
    response = JSONRPCResponse(
        id=id,
        error=JSONRPCError(code=code, message=message, data=data),
        result=None,
    )
    return response.model_dump(exclude_none=True)


def create_success_response(result: Any, id: str | int | None) -> dict:
    """Creates a standardized JSON-RPC success response."""
    response = JSONRPCResponse(id=id, result=result)
    return response.model_dump(exclude_none=True)


def handle_dispatch_error(exc: JSONRPCDispatchError, body: dict | None):
    """Handles JSONRPCDispatchError exceptions."""
    request_id = body.get("id") if isinstance(body, dict) else None
    return create_error_response(exc.code, exc.message, request_id, exc.data)
