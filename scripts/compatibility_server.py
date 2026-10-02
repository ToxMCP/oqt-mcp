"""Test-only authentication and Toolbox fixtures, below the actual domain handlers."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import httpx


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 10, 1, 12, tzinfo=timezone.utc)
        return value.astimezone(tz) if tz else value.replace(tzinfo=None)


def install_fixtures(patch=setattr):
    from authlib.jose import JoseError

    from src.auth import service
    from src.qsar import client
    from src.tools.implementations import workflow_runner
    from src.utils import review

    def decode(token, force_refresh=False):
        if token not in {"fixture-researcher", "fixture-guest"}:
            raise JoseError("Synthetic invalid token")
        return {
            "sub": "fixture-user",
            "roles": ["GUEST" if token.endswith("guest") else "RESEARCHER"],
        }

    patch(service, "_decode_token", decode)
    patch(client, "time", SimpleNamespace(perf_counter=lambda: 1.0))
    patch(workflow_runner, "datetime", FixedDatetime)
    patch(review, "datetime", FixedDatetime)
    counter = iter(range(1, 100_000))
    patch(workflow_runner, "uuid4", lambda: UUID(int=next(counter)))
    patch(review, "uuid4", lambda: UUID(int=next(counter)))
    patch(
        workflow_runner.oqt_assistant, "resolve_assistant_config", lambda **kwargs: None
    )

    async def provider(request):
        record = {
            "method": request.method,
            "path": request.url.path,
            "query": request.url.query.decode(),
            "body": json.loads(request.content) if request.content else None,
        }
        path = request.url.path
        captured = os.environ.get("OQT_COMPATIBILITY_REQUEST_LOG")
        if captured:
            with Path(captured).open("a") as stream:
                stream.write(json.dumps(record, sort_keys=True) + "\n")
        if path.startswith("/api/v6/search/"):
            payload = [
                {
                    "ChemId": "fixture-chemical",
                    "Cas": "64-17-5",
                    "Names": ["Ethanol"],
                    "Smiles": "CCO",
                }
            ]
        elif path.startswith("/api/v6/about/object/"):
            payload = {
                "Guid": "fixture-model",
                "Name": "Synthetic acute endpoint model",
                "Donator": "OECD",
            }
        elif path.startswith("/api/v6/qsar/apply/"):
            payload = {
                "Value": "1.23",
                "Unit": "mg/L",
                "Endpoint": "LC50",
                "DomainResult": "OutOfDomain",
            }
        elif path.startswith("/api/v6/qsar/domain/"):
            payload = "OutOfDomain"
        elif path == "/api/v6/data/endpointtree":
            payload = ["Ecotoxicological information|Aquatic toxicity|LC50"]
        else:
            raise AssertionError(f"Unexpected synthetic Toolbox path: {path}")
        return httpx.Response(
            200,
            request=request,
            json=payload,
            headers={
                "api-supported-versions": "6.0",
                "date": "Thu, 01 Oct 2026 12:00:00 GMT",
            },
        )

    patch(client.qsar_client, "transport", httpx.MockTransport(provider))
    patch(client.qsar_client, "_max_attempts", {"light": 1, "heavy": 1})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["http", "stdio"], required=True)
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    os.environ.update(
        AUTH_OIDC_ISSUER="https://fixture-issuer.example",
        AUTH_OIDC_AUDIENCE="fixture-audience",
        BYPASS_AUTH="false",
        LOG_LEVEL="WARNING",
        MCP_STDIO_BEARER_TOKEN="fixture-researcher",
    )
    protocol_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        from src.api.server import app

        install_fixtures()
    finally:
        sys.stdout = protocol_stdout
    if args.transport == "http":
        import uvicorn

        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    else:
        from src.mcp.sdk2 import main as serve

        serve()


if __name__ == "__main__":
    main()
