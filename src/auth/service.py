import logging
from authlib.jose import jwt, JoseError
from fastapi import HTTPException, status, Request
from fastapi.security import OAuth2AuthorizationCodeBearer
import httpx
from functools import lru_cache
from datetime import datetime, timedelta
from threading import Lock
from typing import Any, Dict

from src.auth.config import (
    OIDC_ISSUER,
    OIDC_AUDIENCE,
    OIDC_ALGORITHMS,
    JWKS_URI,
    JWKS_CACHE_TTL_SECONDS,
    AUTHORIZATION_URL,
    TOKEN_URL,
    BYPASS_AUTH,
)
from src.auth.rbac import ROLES
from src.config.settings import settings

log = logging.getLogger(__name__)

# Define the OAuth2 scheme (Section 2.2: Use OAuth 2.0/OIDC)
# The actual FastAPI dependency usage is handled dynamically in get_current_user
_oauth2_scheme = None
if OIDC_ISSUER and OIDC_AUDIENCE and AUTHORIZATION_URL and TOKEN_URL:
    _oauth2_scheme = OAuth2AuthorizationCodeBearer(
        authorizationUrl=f"{AUTHORIZATION_URL}?audience={OIDC_AUDIENCE}" if AUTHORIZATION_URL else "",
        tokenUrl=TOKEN_URL or "",
        scopes={"openid": "OpenID Connect"},
        auto_error=False # We handle errors manually to provide better context
    )
elif not BYPASS_AUTH:
    log.warning("Incomplete OIDC configuration detected; authentication will fail until configured properly.")

class User(dict):
    """Represents an authenticated user with roles."""
    @property
    def id(self) -> str:
        return self.get("sub", "")

    @property
    def roles(self) -> list[str]:
        return self.get("roles", []) # Set during authentication

# JWKS cache state
_jwks_cache: dict[str, any] = {"data": None, "expires_at": None}
_jwks_lock = Lock()

@lru_cache()
def _cache_ttl() -> timedelta:
    return timedelta(seconds=JWKS_CACHE_TTL_SECONDS if JWKS_CACHE_TTL_SECONDS > 0 else 300)

def _cache_expired() -> bool:
    expires_at = _jwks_cache.get("expires_at")
    if not expires_at:
        return True
    return datetime.utcnow() >= expires_at

def _store_jwks(payload: dict) -> dict:
    _jwks_cache["data"] = payload
    _jwks_cache["expires_at"] = datetime.utcnow() + _cache_ttl()
    return payload

def get_jwks(force_refresh: bool = False) -> dict:
    """
    Fetches and caches the JSON Web Key Set (JWKS).
    Falls back to the last known keys if refresh fails.
    """
    if not JWKS_URI:
        raise RuntimeError("JWKS_URI is not configured.")
    with _jwks_lock:
        if not force_refresh and _jwks_cache["data"] and not _cache_expired():
            return _jwks_cache["data"]

        try:
            log.info(f"Fetching JWKS from {JWKS_URI}")
            response = httpx.get(JWKS_URI, timeout=10.0)
            response.raise_for_status()
            payload = response.json()
            return _store_jwks(payload)

        except httpx.HTTPStatusError as e:
            log.error(f"Failed to fetch JWKS: {e}")
        except Exception as e:
            log.error(f"An unexpected error occurred while fetching JWKS: {e}")

        if _jwks_cache["data"]:
            log.warning("Using cached JWKS due to fetch failure.")
            return _jwks_cache["data"]

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable (Unable to retrieve JWKS).",
        )


def _sanitize_error(err: Exception) -> str:
    message = str(err)
    return message[:200]


def _decode_token(token: str, force_refresh: bool = False) -> Dict[str, Any]:
    jwks = get_jwks(force_refresh=force_refresh)
    claims = jwt.decode(
        token,
        jwks,
        claims_options={
            "iss": {"essential": True, "value": OIDC_ISSUER},
            "aud": {"essential": True, "value": OIDC_AUDIENCE},
        },
    )
    if hasattr(claims, "validate"):
        claims.validate()
    return dict(claims)


async def get_current_user(request: Request) -> User:
    """
    Dynamically validates the JWT token from the request header and retrieves the current user.
    """
    # Development/Testing Bypass
    if BYPASS_AUTH:
        log.warning("AUTHENTICATION IS BYPASSED. Returning development user.")
        user = User({"sub": "dev|bypass", "roles": [ROLES["SYSTEM_BYPASS"]]})
        request.state.user = user
        return user

    if not _oauth2_scheme:
        log.error("OIDC configuration (Issuer/Audience) is missing but BYPASS_AUTH is False.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication system is not configured.",
        )

    # Extract token using the OAuth2 scheme handler (checks Authorization header)
    token = await _oauth2_scheme(request)

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated (Bearer token missing)",
            headers={"WWW-Authenticate": "Bearer"},
        )

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = _decode_token(token)
    except JoseError as e:
        # Attempt a single refresh if key rotation likely
        if "Unable to find a key" in str(e) or "No matching key" in str(e):
            try:
                payload = _decode_token(token, force_refresh=True)
            except JoseError as refreshed_error:
                log.error(f"JWT validation error after refresh: {_sanitize_error(refreshed_error)}")
                raise credentials_exception
        else:
            message = _sanitize_error(e)
            if "expired" in message.lower():
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token expired",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            log.error(f"JWT validation error: {message}")
            raise credentials_exception
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"An unexpected error occurred during authentication: {_sanitize_error(e)}")
        raise credentials_exception

    user_roles = _extract_roles(payload)
    user = User(payload | {"roles": user_roles})
    if not user.roles:
        log.warning(f"User {user.id} authenticated but has no roles assigned.")

    request.state.user = user
    return user


def _extract_roles(claims: Dict[str, Any]) -> list[str]:
    path = settings.security.AUTH_ROLE_CLAIM_PATH
    if not path:
        return claims.get("roles", [])

    keys = path.split(".")
    current: Any = claims
    try:
        for key in keys:
            if isinstance(current, dict):
                current = current[key]
            else:
                raise KeyError
    except KeyError:
        log.warning(f"Role claim path '{path}' not found in token.")
        return []

    if isinstance(current, list):
        return [str(item) for item in current]
    if isinstance(current, str):
        return [current]

    log.warning(f"Role claim path '{path}' did not resolve to list or string.")
    return []
