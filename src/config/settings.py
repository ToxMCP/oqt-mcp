import os
from functools import lru_cache
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


class SecuritySettings(BaseSettings):
    # OAuth 2.0 / OIDC Configuration (Section 2.2)
    AUTH_OIDC_ISSUER: Optional[str] = None
    AUTH_OIDC_AUDIENCE: Optional[str] = None
    AUTH_OIDC_ALGORITHMS: List[str] = ["RS256"]
    AUTH_JWKS_CACHE_TTL_SECONDS: int = 300
    AUTH_ROLE_CLAIM_PATH: str = "roles"  # dot-separated path to roles in the JWT claims

    # Development bypass
    BYPASS_AUTH: bool = False

    # RBAC
    TOOL_PERMISSIONS_FILE: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


class QSARSettings(BaseSettings):
    # Connection details for the QSAR Toolbox WebAPI
    QSAR_TOOLBOX_API_URL: str = os.getenv(
        "QSAR_TOOLBOX_API_URL", "http://localhost:5000"
    )  # Default if not set
    QSAR_LIGHT_TIMEOUT_SECONDS: float = 30.0
    QSAR_HEAVY_TIMEOUT_SECONDS: float = 300.0
    QSAR_LIGHT_MAX_ATTEMPTS: int = 2
    QSAR_HEAVY_MAX_ATTEMPTS: int = 3
    QSAR_HEAVY_CONCURRENCY: int = 3
    QSAR_HAZARD_PROFILING_WALLCLOCK_TIMEOUT_SECONDS: float = 25.0
    QSAR_DISCOVERY_LIST_ALL_TOTAL_WALLCLOCK_TIMEOUT_SECONDS: float = 45.0
    QSAR_DISCOVERY_LIST_ALL_PER_POSITION_TIMEOUT_SECONDS: float = 6.0
    QSAR_DISCOVERY_SEARCH_DATABASES_WALLCLOCK_TIMEOUT_SECONDS: float = 20.0

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


class Settings(BaseSettings):
    app: AppSettings = AppSettings()
    security: SecuritySettings = SecuritySettings()
    qsar: QSARSettings = QSARSettings()


@lru_cache()
def get_settings() -> Settings:
    # We instantiate the nested settings explicitly to ensure .env variables are loaded
    return Settings(app=AppSettings(), security=SecuritySettings(), qsar=QSARSettings())


settings = get_settings()
