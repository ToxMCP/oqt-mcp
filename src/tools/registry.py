import logging
from typing import Callable, Dict, Any
from pydantic import BaseModel, ValidationError
from src.mcp.protocol import ToolDefinition
from src.auth.rbac import check_permission
from src.auth.service import User
from src.utils import audit
import inspect
import json

log = logging.getLogger(__name__)

class ToolRegistry:
    """
    Manages the registration, discovery, and execution of tools.
    """
    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}

    def register(self, name: str, description: str, parameters_model: type[BaseModel], implementation: Callable):
        """Registers a new tool in the registry."""
        # Enforce snake_case convention (Section 3.3)
        if not name.islower() or " " in name or "." in name:
            raise ValueError(f"Tool name '{name}' must be in snake_case.")

        if name in self._tools:
            raise ValueError(f"Tool '{name}' is already registered.")

        # Generate JSON schema from Pydantic model for standardized definitions (Section 3.1)
        # This provides the machine-readable manual for the AI agent.
        parameters_schema = parameters_model.model_json_schema()

        self._tools[name] = {
            "definition": ToolDefinition(name=name, description=description, parameters=parameters_schema),
            "implementation": implementation,
            "parameters_model": parameters_model,
        }
        log.info(f"Registered tool: {name}")

    def get_definition(self, name: str) -> ToolDefinition:
        tool = self._tools.get(name)
        if not tool:
            raise ToolNotFoundError(f"Tool '{name}' not found.")
        return tool["definition"]

    def list_definitions(self, user: User | None = None) -> list[ToolDefinition]:
        """
        Lists all available tool definitions, filtered by user permissions.
        This addresses the tension between discoverability and security (Section 2.4).
        """
        definitions = []
        for name, tool in self._tools.items():
            # If a user is provided, check permissions before exposing the tool
            if user:
                if check_permission(user.roles, name):
                    definitions.append(tool["definition"])
            else:
                # If no user context (e.g. during initialization if needed), we cannot determine permissions.
                # Secure default is to list nothing if the user is unknown.
                pass
        return definitions

    async def execute(self, name: str, params: Dict[str, Any], user: User):
        """
        Executes a tool after performing authorization checks and input validation.
        """
        tool = self._tools.get(name)
        if not tool:
            raise ToolNotFoundError(f"Tool '{name}' not found.")

        # 1. Authorization Check (RBAC) (Section 2.2)
        if not check_permission(user.roles, name):
            audit.emit(
                {
                    "type": "tool_execution",
                    "tool": name,
                    "user_id": user.id,
                    "status": "forbidden",
                }
            )
            raise PermissionError(f"User is not authorized to execute tool '{name}'.")

        log.info(f"Executing tool '{name}' for user {user.id}")

        # 2. Input Validation (Schema Enforcement) (Section 2.3)
        try:
            # Validate incoming parameters against the Pydantic model
            validated_params = tool["parameters_model"].model_validate(params)
        except ValidationError as e:
            # Pydantic provides detailed validation errors
            raise InputValidationError(f"Invalid parameters for tool '{name}': {e.json()}")
        except Exception as e:
            raise InputValidationError(f"Parameter validation failed unexpectedly: {e}")

        # 3. Execute the implementation
        implementation = tool["implementation"]
        
        # Check if the implementation is async, otherwise run in a threadpool (if needed for blocking IO)
        try:
            if inspect.iscoroutinefunction(implementation):
                 # Pass validated parameters as keyword arguments
                result = await implementation(**validated_params.model_dump())
            else:
                # Handle synchronous functions (less ideal for FastAPI/Uvicorn)
                log.warning(f"Tool '{name}' implementation is synchronous. Consider making it async.")
                result = implementation(**validated_params.model_dump())
        except Exception as exc:
            audit.emit(
                {
                    "type": "tool_execution",
                    "tool": name,
                    "user_id": user.id,
                    "status": "error",
                    "error": str(exc),
                }
            )
            raise

        # 4. Audit Logging (Section 2.3) - Placeholder
        # CRITICAL: This should be handled by a dedicated, immutable audit service in production
        # Ensure PII/Sensitive data in params is sanitized before logging if necessary.
        try:
            # Attempt a safe serialization for logging
            logged_params = json.dumps(params, default=str, indent=2)[:500]
        except Exception:
            logged_params = "Params serialization failed"
            
        audit.emit(
            {
                "type": "tool_execution",
                "tool": name,
                "user_id": user.id,
                "status": "success",
                "params": logged_params,
            }
        )

        # 5. Output Sanitization/DLP (Section 2.3) - Placeholder
        # Implement checks here to ensure sensitive data is not leaked in the result before returning

        return result

class ToolNotFoundError(Exception):
    pass

class InputValidationError(Exception):
    pass

# Global registry instance
tool_registry = ToolRegistry()
