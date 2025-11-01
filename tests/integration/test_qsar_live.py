import asyncio
import os

import pytest

from src.config.settings import settings
from src.qsar.client import QsarClient, QsarClientError

_FLAG = os.getenv("QSAR_LIVE_TESTS", "").lower()
_ENABLED = _FLAG in {"1", "true", "yes", "on"}
_BASE_URL = settings.qsar.QSAR_TOOLBOX_API_URL.rstrip("/")


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _ENABLED,
        reason="Live QSAR Toolbox integration tests are disabled. "
        "Set QSAR_LIVE_TESTS=1 to enable.",
    ),
    pytest.mark.skipif(
        not _BASE_URL,
        reason="QSAR_TOOLBOX_API_URL is not configured.",
    ),
]


def _client() -> QsarClient:
    # Guard against misconfiguration that includes /api/v6 in the base URL.
    base_url = _BASE_URL
    if base_url.endswith("/api/v6") or "/api/v6/" in base_url:
        pytest.skip(
            "QSAR_TOOLBOX_API_URL should point at the host root (e.g. http://host:port)."
        )
    return QsarClient(base_url, timeout=15.0)


def _run(coro):
    try:
        return asyncio.run(coro)
    except QsarClientError as exc:
        pytest.fail(f"QSAR Toolbox request failed: {exc}")


def test_list_profilers_live():
    client = _client()
    profilers = _run(client.list_profilers())
    assert isinstance(profilers, list)
    assert profilers, "No profilers returned from live QSAR API."
    first = profilers[0]
    assert "Guid" in first
    assert "Caption" in first


def test_list_search_databases_live():
    client = _client()
    payload = _run(client.list_search_databases())
    assert isinstance(payload, list), "Search databases response was not a list."
    assert payload, "QSAR API returned no search databases."


def test_list_workflows_live():
    client = _client()
    workflows = _run(client.list_workflows())
    assert isinstance(workflows, list)
    assert workflows, "No workflows returned from live QSAR API."
