from fastapi.testclient import TestClient

from src.api.server import app
from src.utils import audit


def test_audit_middleware_generates_correlation_id():
    events = []
    audit.clear_sinks()
    audit.register_sink(events.append)

    client = TestClient(app)
    response = client.post(
        "/mcp", json={"jsonrpc": "2.0", "method": "initialize", "id": 1}
    )

    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    assert any(event.get("type") == "http_request" for event in events)

    audit.clear_sinks()
