import asyncio

from src.tools.implementations import toolbox_discovery as discovery


def test_list_profilers(monkeypatch):
    async def fake_list_profilers():
        return [{"Guid": "abc", "Caption": "Profiler"}]

    monkeypatch.setattr(discovery.qsar_client, "list_profilers", fake_list_profilers)

    result = asyncio.run(discovery.list_profilers())
    assert result == {"profilers": [{"Guid": "abc", "Caption": "Profiler"}]}


def test_get_profiler_info(monkeypatch):
    async def fake_get_profiler_info(profiler_guid: str):
        return {"Guid": profiler_guid, "Caption": "Foo"}

    monkeypatch.setattr(
        discovery.qsar_client, "get_profiler_info", fake_get_profiler_info
    )

    result = asyncio.run(discovery.get_profiler_info("guid-123"))
    assert result["profiler"]["Guid"] == "guid-123"


def test_list_all_qsar_models(monkeypatch):
    async def fake_list_all_qsar_models():
        return [
            {"Guid": "model-1", "Caption": "Model 1", "RequestedPosition": "A"},
            {"Guid": "model-2", "Caption": "Model 2", "RequestedPosition": "B"},
        ]

    monkeypatch.setattr(
        discovery.qsar_client, "list_all_qsar_models", fake_list_all_qsar_models
    )

    result = asyncio.run(discovery.list_all_qsar_models())
    assert len(result["catalog"]) == 2
    assert {item["Guid"] for item in result["catalog"]} == {"model-1", "model-2"}
