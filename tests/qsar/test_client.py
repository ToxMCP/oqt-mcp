import asyncio
import json

import httpx
import pytest

from src.qsar.client import QsarClient, QsarClientError


def run(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def test_get_model_metadata_path():
    async def handler(request: httpx.Request):
        assert request.url.path == "/api/v6/about/object/model-123"
        return httpx.Response(200, json={"model": "data"})

    client = QsarClient("https://example.com", transport=httpx.MockTransport(handler))
    result = run(client.get_model_metadata("model-123"))
    assert result == {"model": "data"}


def test_search_cas_path():
    async def handler(request: httpx.Request):
        assert request.url.path == "/api/v6/search/cas/64-17-5/false"
        return httpx.Response(200, json={"results": []})

    client = QsarClient("https://example.com", transport=httpx.MockTransport(handler))
    run(client.search_chemicals("64-17-5", "cas"))


def test_run_prediction_posts_payload():
    async def handler(request: httpx.Request):
        assert request.method == "POST"
        assert request.url.path == "/api/v6/qsar/apply"
        payload = json.loads(request.content.decode())
        assert payload == {"smiles": "CCO", "modelId": "model-1"}
        return httpx.Response(200, json={"prediction": "Positive"})

    client = QsarClient("https://example.com", transport=httpx.MockTransport(handler))
    response = run(client.run_prediction("CCO", "model-1"))
    assert response["prediction"] == "Positive"


def test_error_response_raises_client_error():
    async def handler(request: httpx.Request):
        return httpx.Response(500, json={"error": "boom"})

    client = QsarClient("https://example.com", transport=httpx.MockTransport(handler))
    with pytest.raises(QsarClientError):
        run(client.get_model_metadata("bad"))
