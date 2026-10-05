import json

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.mcp.protocol import INVALID_REQUEST, JSONRPCRequest, JSONRPCResponse


def test_legacy_initialize_omits_unimplemented_capabilities():
    client = TestClient(app)
    response = client.post("/mcp", json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                   "clientInfo": {"name": "legacy-discovery-regression", "version": "1.0"}},
    })
    assert response.status_code == 200
    assert set(response.json()["result"]["capabilities"]) == {"tools", "prompts"}


def test_jsonrpc_request_rejects_boolean_id():
    with pytest.raises(ValueError):
        JSONRPCRequest(method="initialize", id=True)


def test_jsonrpc_request_converts_integral_float_id():
    request = JSONRPCRequest(method="initialize", id=2.0)
    assert request.id == 2


def test_jsonrpc_request_rejects_fractional_float_id():
    with pytest.raises(ValueError):
        JSONRPCRequest(method="initialize", id=1.5)


def test_jsonrpc_response_allows_null_result():
    response = JSONRPCResponse(id=1, result=None)
    assert response.result is None
    assert response.error is None


def test_batch_requests_rejected():
    client = TestClient(app)
    payload = [
        {"jsonrpc": "2.0", "method": "initialize", "id": 1},
        {"jsonrpc": "2.0", "method": "initialized"},
    ]

    res = client.post("/mcp", content=json.dumps(payload))
    assert res.status_code == 400
    body = res.json()
    assert body["error"]["code"] == INVALID_REQUEST
    assert "Batch requests are not supported" in body["error"]["message"]
