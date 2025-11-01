import asyncio
from datetime import datetime, timedelta

import httpx
import pytest
from authlib.jose import JoseError, JsonWebKey, jwt
from fastapi import HTTPException

from src.auth import service as auth_service


@pytest.fixture(autouse=True)
def reset_cache(monkeypatch):
    monkeypatch.setattr(auth_service, "_jwks_cache", {"data": None, "expires_at": None})
    monkeypatch.setattr(
        auth_service, "JWKS_URI", "https://issuer.example.com/.well-known/jwks.json"
    )
    yield


@pytest.fixture
def dummy_request():
    class _Req:
        headers = {}
        state = type("State", (), {})()

    return _Req()


def _httpx_request() -> httpx.Request:
    return httpx.Request("GET", "https://issuer.example.com/.well-known/jwks.json")


def test_get_jwks_uses_cache(monkeypatch):
    calls = {"count": 0}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"keys": [{"kid": "1"}]}

    def fake_get(url, timeout):
        calls["count"] += 1
        return _Response()

    monkeypatch.setattr(auth_service.httpx, "get", fake_get)

    first = auth_service.get_jwks(force_refresh=True)
    second = auth_service.get_jwks()

    assert calls["count"] == 1
    assert second == first


def test_get_jwks_returns_stale_on_failure(monkeypatch):
    cached = {"keys": [{"kid": "stale"}]}
    auth_service._jwks_cache["data"] = cached
    auth_service._jwks_cache["expires_at"] = datetime.utcnow() - timedelta(seconds=1)

    def failing_get(url, timeout):
        raise httpx.ConnectError("boom", request=_httpx_request())

    monkeypatch.setattr(auth_service.httpx, "get", failing_get)

    result = auth_service.get_jwks(force_refresh=True)
    assert result == cached


def test_get_jwks_raises_when_no_cache(monkeypatch):
    def failing_get(url, timeout):
        raise httpx.ConnectError("boom", request=_httpx_request())

    monkeypatch.setattr(auth_service.httpx, "get", failing_get)

    with pytest.raises(HTTPException) as exc:
        auth_service.get_jwks(force_refresh=True)

    assert exc.value.status_code == 503


# --- get_current_user tests ---


@pytest.fixture
def configure_auth(monkeypatch):
    original_bypass = auth_service.BYPASS_AUTH
    monkeypatch.setattr(auth_service, "BYPASS_AUTH", False)

    async def fake_scheme(request):
        return "token"

    monkeypatch.setattr(auth_service, "_oauth2_scheme", fake_scheme)
    yield
    monkeypatch.setattr(auth_service, "BYPASS_AUTH", original_bypass)


def _run_async(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def test_get_current_user_success(monkeypatch, dummy_request, configure_auth):
    dummy_payload = {"sub": "user|123", "roles": ["RESEARCHER"]}

    def fake_decode(token, force_refresh=False):
        return dummy_payload

    monkeypatch.setattr(auth_service, "_decode_token", fake_decode)

    user = _run_async(auth_service.get_current_user(dummy_request))
    assert user.id == "user|123"
    assert user.roles == ["RESEARCHER"]


def test_get_current_user_handles_missing_token(
    monkeypatch, dummy_request, configure_auth
):
    async def no_token(request):
        return None

    monkeypatch.setattr(auth_service, "_oauth2_scheme", no_token)

    with pytest.raises(HTTPException) as exc:
        _run_async(auth_service.get_current_user(dummy_request))

    assert exc.value.status_code == 401


def test_get_current_user_refreshes_keys(monkeypatch, dummy_request, configure_auth):
    attempts = {"count": 0}

    def fake_decode(token, force_refresh=False):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise JoseError("Unable to find a key")
        return {"sub": "user|123", "roles": ["LAB_ADMIN"]}

    monkeypatch.setattr(auth_service, "_decode_token", fake_decode)

    user = _run_async(auth_service.get_current_user(dummy_request))
    assert attempts["count"] == 2
    assert user.roles == ["LAB_ADMIN"]


def test_get_current_user_expired_token(monkeypatch, dummy_request, configure_auth):
    def fake_decode(token, force_refresh=False):
        raise JoseError("Token expired")

    monkeypatch.setattr(auth_service, "_decode_token", fake_decode)

    with pytest.raises(HTTPException) as exc:
        _run_async(auth_service.get_current_user(dummy_request))

    assert exc.value.status_code == 401
    assert exc.value.detail == "Token expired"


def test_decode_token_with_real_jwks(monkeypatch):
    key = JsonWebKey.generate_key(
        "RSA", 2048, is_private=True, options={"kid": "dev-key"}
    )
    monkeypatch.setattr(auth_service, "OIDC_ISSUER", "https://issuer.example.com")
    monkeypatch.setattr(auth_service, "OIDC_AUDIENCE", "aud")
    monkeypatch.setattr(auth_service, "OIDC_ALGORITHMS", ["RS256"])
    monkeypatch.setattr(
        auth_service.settings.security, "AUTH_ROLE_CLAIM_PATH", "custom.claim.roles"
    )
    public_jwk = key.as_dict(is_private=False)
    claims = {
        "sub": "user|42",
        "roles": ["IGNORED"],
        "custom": {"claim": {"roles": ["RESEARCHER"]}},
        "iss": "https://issuer.example.com",
        "aud": "aud",
    }
    token = jwt.encode({"alg": "RS256", "kid": "dev-key"}, claims, key).decode("utf-8")
    monkeypatch.setattr(
        auth_service, "get_jwks", lambda force_refresh=False: {"keys": [public_jwk]}
    )

    decoded = auth_service._decode_token(token)
    assert decoded["sub"] == "user|42"
    assert auth_service._extract_roles(decoded) == ["RESEARCHER"]
