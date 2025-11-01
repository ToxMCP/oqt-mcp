# Authentication Configuration & Testing Guide

This guide explains how to configure OIDC for the O-QT MCP server, how to use the development bypass safely, and how to generate test tokens for automated suites.

## Required Environment Variables

Configure these values in `.env` (or your deployment secrets):

| Variable | Description |
| --- | --- |
| `AUTH_OIDC_ISSUER` | Base URL of the OIDC issuer (e.g. `https://tenant.auth0.com/`) |
| `AUTH_OIDC_AUDIENCE` | Audience / API identifier expected in JWTs |
| `AUTH_OIDC_ALGORITHMS` | JSON array of algorithms (default `["RS256"]`) |
| `AUTH_JWKS_CACHE_TTL_SECONDS` | Optional cache TTL for JWKS fetches (default 300) |
| `BYPASS_AUTH` | `true` to disable auth in development; **must be `false` in production** |

During server startup, `validate_oidc_configuration()` ensures issuer, audience, and JWKS URI are present when `BYPASS_AUTH=false`. Missing values will halt the application to prevent an insecure deployment.

## Development Bypass

Setting `BYPASS_AUTH=true` returns a synthetic user (`sub=dev|bypass`, role `SYSTEM_BYPASS`). Use this only for local development. The startup log emits a warning whenever bypass mode is active.

## Generating Test Tokens

The test suite includes helpers that create RSA keys and tokens using Authlib:

```python
from authlib.jose import JsonWebKey, jwt

key = JsonWebKey.generate_key("RSA", 2048, is_private=True, kid="dev-key")
claims = {
    "sub": "user|123",
    "roles": ["RESEARCHER"],
    "iss": "https://issuer.example.com",
    "aud": "aud",
}
token = jwt.encode({"alg": "RS256", "kid": "dev-key"}, claims, key)
```

In tests you can patch `src.auth.service.get_jwks` to return the public portion of the generated key:

```python
public_jwk = key.as_dict(is_private=False)
monkeypatch.setattr(auth_service, "get_jwks", lambda force_refresh=False: {"keys": [public_jwk]})
```

This pattern is demonstrated in `tests/auth/test_service.py::test_decode_token_with_real_jwks`.

## Useful Fixtures

* `configure_auth` fixture in `tests/auth/test_service.py` wires an async OAuth2 scheme stub and disables bypass mode.
* `_run_async` helper allows synchronous tests to await `get_current_user`.

## Manual Token Verification

To exercise auth endpoints manually:

1. Generate a token using the snippet above (or your IdP).
2. Call an MCP endpoint with header `Authorization: Bearer <token>`.
3. Inspect structured logs to confirm sanitized error messages for invalid tokens (`Token expired`, `Could not validate credentials`, etc.).

For expiring token scenarios, Authlib raises `JoseError("Token expired")`, which the server translates into an HTTP 401 with detail `Token expired`. Duplicate or malformed tokens produce `Could not validate credentials`.
