import logging
from typing import List, Optional

from src.config.settings import settings

log = logging.getLogger(__name__)

# This configuration is derived directly from the environment variables

OIDC_ISSUER: Optional[str] = settings.security.AUTH_OIDC_ISSUER
OIDC_AUDIENCE: Optional[str] = settings.security.AUTH_OIDC_AUDIENCE
OIDC_ALGORITHMS: List[str] = settings.security.AUTH_OIDC_ALGORITHMS
JWKS_CACHE_TTL_SECONDS: int = settings.security.AUTH_JWKS_CACHE_TTL_SECONDS
BYPASS_AUTH: bool = settings.security.BYPASS_AUTH


def _join_url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


AUTHORIZATION_URL: Optional[str] = None
TOKEN_URL: Optional[str] = None
JWKS_URI: Optional[str] = None

if OIDC_ISSUER:
    AUTHORIZATION_URL = _join_url(OIDC_ISSUER, "authorize")
    TOKEN_URL = _join_url(OIDC_ISSUER, "oauth/token")
    JWKS_URI = _join_url(OIDC_ISSUER, ".well-known/jwks.json")


def validate_oidc_configuration() -> None:
    """
    Validates issuer/audience configuration. Raises RuntimeError when required settings are missing.
    Called during startup to fail fast when BYPASS_AUTH is disabled but credentials are absent.
    """
    if BYPASS_AUTH:
        log.warning("Authentication bypass enabled; OIDC configuration is optional.")
        return

    missing = []
    if not OIDC_ISSUER:
        missing.append("AUTH_OIDC_ISSUER")
    if not OIDC_AUDIENCE:
        missing.append("AUTH_OIDC_AUDIENCE")
    if not OIDC_ALGORITHMS:
        missing.append("AUTH_OIDC_ALGORITHMS")

    if missing:
        raise RuntimeError(
            "Missing required OIDC configuration values: "
            + ", ".join(missing)
            + ". Set these in your .env file or environment variables."
        )

    if not JWKS_URI:
        raise RuntimeError(
            "Could not derive JWKS URI from AUTH_OIDC_ISSUER. "
            "Ensure the issuer is a valid URL."
        )

    log.info("OIDC configuration validated successfully.")
