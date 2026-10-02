from __future__ import annotations

import hashlib
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.security import OAuth2AuthorizationCodeBearer
from fastapi.testclient import TestClient

from src.api.server import app
from src.auth import config, service
from src.config.settings import settings
from src.tools.implementations import workflow_runner
from src.utils import audit

PROTOCOL = "2026-07-28"
ROOT = Path(__file__).resolve().parents[2]


def post(client, method, params=None, headers=None, token="fixture-researcher"):
    params = {
        **(params or {}),
        "_meta": {
            "io.modelcontextprotocol/protocolVersion": PROTOCOL,
            "io.modelcontextprotocol/clientCapabilities": {},
        },
    }
    request_headers = {
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": PROTOCOL,
        "Mcp-Method": method,
    }
    if token is not None:
        request_headers["Authorization"] = "Bearer " + token
    if method == "tools/call":
        request_headers["Mcp-Name"] = params["name"]
    request_headers.update(headers or {})
    return client.post(
        "/mcp",
        headers=request_headers,
        json={"jsonrpc": "2.0", "id": 7, "method": method, "params": params},
    )


@pytest.fixture
def client(monkeypatch):
    for module in [config, service]:
        monkeypatch.setattr(module, "BYPASS_AUTH", False)
        monkeypatch.setattr(module, "OIDC_ISSUER", "https://fixture-issuer.example")
        monkeypatch.setattr(module, "OIDC_AUDIENCE", "fixture-audience")
    monkeypatch.setattr(config, "JWKS_URI", "https://fixture-issuer.example/jwks")
    monkeypatch.setattr(settings.security, "BYPASS_AUTH", False)
    monkeypatch.setattr(settings.security, "MCP_STDIO_BEARER_TOKEN", None)
    monkeypatch.setattr(
        service,
        "_oauth2_scheme",
        OAuth2AuthorizationCodeBearer(
            authorizationUrl="https://fixture-issuer.example/authorize",
            tokenUrl="https://fixture-issuer.example/token",
        ),
    )
    spec = importlib.util.spec_from_file_location(
        "oqt_fixtures", ROOT / "scripts/compatibility_server.py"
    )
    fixtures = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixtures)
    fixtures.install_fixtures(monkeypatch.setattr)
    monkeypatch.setattr(workflow_runner.review_orchestrator, "_checkpoints", {})
    monkeypatch.setattr(workflow_runner.review_orchestrator, "_workflow_index", {})
    events = []
    monkeypatch.setattr(audit, "emit", events.append)
    with TestClient(app, base_url="http://localhost:8200") as value:
        yield value, events


@pytest.mark.parametrize(
    "role,token", [("GUEST", "fixture-guest"), ("RESEARCHER", "fixture-researcher")]
)
def test_modern_catalog_exactly_preserves_role_filtered_contracts(client, role, token):
    value, _ = client
    result = post(value, "tools/list", token=token).json()["result"]
    assert result["ttlMs"] == 0 and result["cacheScope"] == "private"
    expected = json.loads(
        (ROOT / "tests/compatibility/v0.3.2-catalog-sha256.json").read_text()
    )["roles"][role]
    assert len(result["tools"]) == expected["tools"]
    assert (
        hashlib.sha256(
            json.dumps(result["tools"], sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        == expected["sha256"]
    )
    assert post(value, "prompts/list", token=token).json()["result"]["prompts"] == []


def test_modern_auth_and_tool_permissions_cannot_be_bypassed(client):
    value, _ = client
    assert post(value, "tools/list", token=None).status_code == 401
    assert post(value, "tools/list", token="fixture-invalid").status_code == 401
    denied = post(
        value,
        "tools/call",
        {
            "name": "run_qsar_prediction",
            "arguments": {"smiles": "CCO", "model_id": "fixture-model"},
        },
        token="fixture-guest",
    )
    assert denied.json()["error"]["code"] == -32001
    assert post(value, "server/discover", token=None).status_code == 200


def test_modern_out_of_domain_prediction_retains_all_warning_fields(client):
    value, _ = client
    result = post(
        value,
        "tools/call",
        {
            "name": "run_qsar_prediction",
            "arguments": {"smiles": "CCO", "model_id": "fixture-model"},
        },
    ).json()["result"]
    application = json.loads(result["content"][0]["text"])
    assert (
        application["ad_status"] == "out_of_domain"
        and application["ad_warning"] is True
    )
    assert application["ad_recommendation"]
    assert application["toolbox"]["calls"]


def test_review_blocks_pdf_and_preserves_out_of_domain_checkpoint(client, monkeypatch):
    value, _ = client

    def unexpected_pdf(*args, **kwargs):
        raise AssertionError("Pending human review must never generate an artifact")

    monkeypatch.setattr(workflow_runner, "generate_pdf_report", unexpected_pdf)
    result = post(
        value,
        "tools/call",
        {
            "name": "run_oqt_multiagent_workflow",
            "arguments": {
                "identifier": "Ethanol",
                "qsar_guids": ["fixture-model"],
                "require_human_review": True,
                "workflow_id": "fixture-unit-review",
            },
        },
    ).json()["result"]
    application = json.loads(result["content"][0]["text"])
    assert application["status"] == "review_required"
    assert {checkpoint["step"] for checkpoint in application["review_checkpoints"]} == {
        "chemical_identity",
        "ad_assessment",
        "final_report",
    }
    assert "pdf_base64" not in application
    checkpoint = application["review_checkpoints"][0]["checkpoint_id"]
    approved = post(
        value,
        "tools/call",
        {
            "name": "approve_workflow_checkpoint",
            "arguments": {
                "checkpoint_id": checkpoint,
                "decision": "approved",
                "comments": "Fixture review",
            },
        },
    ).json()["result"]
    assert json.loads(approved["content"][0]["text"])["status"] == "ok"
    assert (
        len(
            workflow_runner.review_orchestrator.pending_checkpoints(
                "fixture-unit-review"
            )
        )
        == 2
    )


def test_modern_tool_audit_keeps_identifiers_scrubbed(client):
    value, events = client
    post(
        value,
        "tools/call",
        {
            "name": "search_chemicals",
            "arguments": {"query": "Ethanol", "search_type": "name"},
        },
    )
    execution = next(event for event in events if event["type"] == "tool_execution")
    assert execution["user_id"] == "fixture-user"
    assert "Ethanol" not in execution["params"]
    assert "fixture-researcher" not in json.dumps(events)
    assert any(
        event["type"] == "http_request" and event["user_id"] == "fixture-user"
        for event in events
    )


@pytest.mark.parametrize(
    "revision", ["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"]
)
def test_legacy_handshake_and_aliases_remain(client, revision):
    value, _ = client
    response = value.post(
        "/mcp",
        headers={"MCP-Protocol-Version": revision},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"capabilities": {}},
        },
    )
    assert response.json()["result"]["protocolVersion"] == "2025-03-26"
    listed = value.post(
        "/mcp",
        headers={"Authorization": "Bearer fixture-researcher"},
        json={"jsonrpc": "2.0", "id": 2, "method": "mcp/tool/list", "params": {}},
    )
    assert len(listed.json()["result"]["tools"]) == 32


@pytest.mark.parametrize(
    "headers",
    [
        {"Host": "attacker.example"},
        {"Origin": "https://attacker.example"},
        {"Mcp-Method": "tools/call"},
        {"MCP-Protocol-Version": "9999-01-01"},
    ],
)
def test_modern_invalid_authority_and_protocol(client, headers):
    value, _ = client
    assert post(value, "tools/list", headers=headers).status_code in {400, 403, 421}


def test_body_bounds_precede_both_protocol_parsers(client):
    value, _ = client
    assert (
        value.post(
            "/mcp", content=iter([b" " * 3_000_000, b" " * 3_000_000])
        ).status_code
        == 413
    )
    assert (
        value.post(
            "/mcp", content=b"{}", headers={"Content-Length": "invalid"}
        ).status_code
        == 400
    )


def test_parallel_modern_requests_keep_individual_results_and_audit_ids(client):
    value, events = client

    def call(index):
        result = post(
            value,
            "tools/call",
            {
                "name": "get_public_qsar_model_info",
                "arguments": {"model_id": f"fixture-model-{index}"},
            },
        )
        assert result.json()["id"] == 7 and "result" in result.json()

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(call, range(8)))
    ids = [
        event["correlation_id"] for event in events if event["type"] == "http_request"
    ]
    assert len(set(ids)) == len(ids) == 8
