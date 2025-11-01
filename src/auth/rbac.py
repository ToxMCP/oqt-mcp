import json
import logging
from pathlib import Path
from typing import Dict, List

from src.config.settings import settings

log = logging.getLogger(__name__)

# Define the Role-Based Access Control (RBAC) policy.
# (Section 2.2: Authorization must be at the individual tool level)

# Roles represent different user personas in the scientific environment
ROLES = {
    "GUEST": "GUEST",
    "RESEARCHER": "RESEARCHER",
    "LAB_ADMIN": "LAB_ADMIN",
    "SYSTEM_BYPASS": "SYSTEM_BYPASS", # Used only when BYPASS_AUTH is enabled
}

_DEFAULT_PERMISSIONS_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "tool_permissions.default.json"

def _load_permissions() -> Dict[str, List[str]]:
    custom_path = settings.security.TOOL_PERMISSIONS_FILE
    path = Path(custom_path).expanduser() if custom_path else _DEFAULT_PERMISSIONS_PATH
    try:
        log.info(f"Loading tool permissions from {path}")
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
            return {role: sorted(set(tools)) for role, tools in data.items()}
    except FileNotFoundError:
        log.error(f"Tool permissions file not found at {path}.")
        raise
    except json.JSONDecodeError as exc:
        log.error(f"Invalid JSON in tool permissions file: {exc}")
        raise

try:
    TOOL_PERMISSIONS = _load_permissions()
except Exception:
    TOOL_PERMISSIONS = {}
    log.error("Failed to load tool permissions. RBAC checks will fail until this is resolved.")

def _emit_metric(event: str, role: str, tool_name: str) -> None:
    # Placeholder for integration with metrics backend
    log.debug(f"RBAC_METRIC event={event} role={role} tool={tool_name}")


def check_permission(user_roles: list[str], tool_name: str) -> bool:
    """
    Checks if the user has the necessary permissions to execute a specific tool (Principle of Least Privilege).
    """
    log.debug(f"Checking permissions for roles {user_roles} on tool '{tool_name}'")

    for role in user_roles:
        allowed_tools = TOOL_PERMISSIONS.get(role)
        if allowed_tools and tool_name in allowed_tools:
            log.info(
                "Authorization granted",
                extra={"role": role, "tool": tool_name, "event": "rbac_allow"},
            )
            _emit_metric("allow", role, tool_name)
            return True

    log.warning(
        "Authorization denied",
        extra={"roles": user_roles, "tool": tool_name, "event": "rbac_deny"},
    )
    for role in user_roles:
        _emit_metric("deny", role, tool_name)
    return False
