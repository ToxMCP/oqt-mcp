from pydantic import BaseModel, Field, model_validator, field_validator
from typing import Any, Optional, Dict, List, Literal

# --- JSON-RPC 2.0 Base Models ---
# (Section 1.2)

class JSONRPCRequest(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    method: str
    params: Optional[Dict[str, Any] | List[Any]] = None
    id: Optional[str | int | None] = None

    @field_validator("id", mode="before")
    @classmethod
    def validate_id(cls, request_id):
        if isinstance(request_id, bool):
            raise ValueError("JSON-RPC id must not be boolean.")

        if isinstance(request_id, float):
            # JSON-RPC expects integers or strings – floats introduce ambiguity for transports.
            if not request_id.is_integer():
                raise ValueError("JSON-RPC id must not be fractional.")
            return int(request_id)

        return request_id

class JSONRPCError(BaseModel):
    code: int
    message: str
    data: Optional[Any] = None

class JSONRPCResponse(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    result: Optional[Any] = None
    error: Optional[JSONRPCError] = None
    id: str | int | None = None

    @model_validator(mode='before')
    def check_consistency(cls, values):
        # Must not have both result and error
        if 'error' in values and values['error'] is not None and 'result' in values and values['result'] is not None:
            raise ValueError('JSON-RPC response cannot have both result and error.')
        
        # If an ID is present, it must have either result or error (it's a response, not a notification)
        if 'id' in values and values['id'] is not None:
            if ('error' not in values or values['error'] is None) and ('result' not in values):
                raise ValueError('JSON-RPC response must include result or error when id is present.')
        return values

# --- MCP Specific Models ---

# Capability Negotiation (Section 1.3)
class FeatureSupport(BaseModel):
    enabled: bool

class InitializeParams(BaseModel):
    # Flexible structure as per MCP specification
    capabilities: Dict[str, Any] = Field(default_factory=dict)

class InitializeResult(BaseModel):
    protocolVersion: str = Field(..., alias="protocolVersion")
    features: Dict[str, FeatureSupport]

# Tools and Resources (Section 1.3, Section 3.1)

# We use a flexible dictionary structure for parameters to align with JSON Schema/OpenAPI (Section 3.1)
class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any] # JSON Schema object definition

class ListToolsResult(BaseModel):
    tools: List[ToolDefinition]

# Standard MCP Error Codes
# (Section 3.3)
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# Custom Application Errors (e.g., Security)
# (Section 2)
UNAUTHORIZED = -32000
FORBIDDEN = -32001
TOOL_EXECUTION_ERROR = -32002
