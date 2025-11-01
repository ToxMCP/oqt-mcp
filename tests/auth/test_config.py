import pytest

from src.auth import config as auth_config


@pytest.fixture(autouse=True)
def restore_config(monkeypatch):
    original_values = {
        "BYPASS_AUTH": auth_config.BYPASS_AUTH,
        "OIDC_ISSUER": auth_config.OIDC_ISSUER,
        "OIDC_AUDIENCE": auth_config.OIDC_AUDIENCE,
        "OIDC_ALGORITHMS": auth_config.OIDC_ALGORITHMS,
        "JWKS_URI": auth_config.JWKS_URI,
    }
    yield
    for key, value in original_values.items():
        monkeypatch.setattr(auth_config, key, value, raising=False)


def test_validate_oidc_configuration_allows_bypass(monkeypatch):
    monkeypatch.setattr(auth_config, "BYPASS_AUTH", True)
    monkeypatch.setattr(auth_config, "OIDC_ISSUER", None)
    # Should not raise
    auth_config.validate_oidc_configuration()


def test_validate_oidc_configuration_requires_fields(monkeypatch):
    monkeypatch.setattr(auth_config, "BYPASS_AUTH", False)
    monkeypatch.setattr(auth_config, "OIDC_ISSUER", None)
    monkeypatch.setattr(auth_config, "OIDC_AUDIENCE", None)
    with pytest.raises(RuntimeError):
        auth_config.validate_oidc_configuration()


def test_validate_oidc_configuration_success(monkeypatch):
    monkeypatch.setattr(auth_config, "BYPASS_AUTH", False)
    monkeypatch.setattr(auth_config, "OIDC_ISSUER", "https://issuer.example.com")
    monkeypatch.setattr(auth_config, "OIDC_AUDIENCE", "aud")
    monkeypatch.setattr(auth_config, "OIDC_ALGORITHMS", ["RS256"])
    monkeypatch.setattr(
        auth_config, "JWKS_URI", "https://issuer.example.com/.well-known/jwks.json"
    )
    # Should not raise
    auth_config.validate_oidc_configuration()
