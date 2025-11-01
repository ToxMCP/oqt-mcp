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


def test_list_simulators(monkeypatch):
    async def fake_list_simulators():
        return [{"Guid": "sim", "Caption": "Sim"}]

    monkeypatch.setattr(discovery.qsar_client, "list_simulators", fake_list_simulators)

    result = asyncio.run(discovery.list_simulators())
    assert result == {"simulators": [{"Guid": "sim", "Caption": "Sim"}]}


def test_get_simulator_info(monkeypatch):
    async def fake_get_simulator_info(simulator_guid: str):
        return {"Guid": simulator_guid, "Caption": "Sim"}

    monkeypatch.setattr(
        discovery.qsar_client, "get_simulator_info", fake_get_simulator_info
    )

    result = asyncio.run(discovery.get_simulator_info("sim-guid"))
    assert result["simulator"]["Guid"] == "sim-guid"


def test_list_calculators(monkeypatch):
    async def fake_list_calculators():
        return [{"Guid": "calc", "Caption": "Calculator"}]

    monkeypatch.setattr(discovery.qsar_client, "list_calculators", fake_list_calculators)

    result = asyncio.run(discovery.list_calculators())
    assert result == {"calculators": [{"Guid": "calc", "Caption": "Calculator"}]}


def test_get_calculator_info(monkeypatch):
    async def fake_get_calculator_info(calculator_guid: str):
        return {"Guid": calculator_guid, "Caption": "Calc"}

    monkeypatch.setattr(
        discovery.qsar_client, "get_calculator_info", fake_get_calculator_info
    )

    result = asyncio.run(discovery.get_calculator_info("calc-guid"))
    assert result["calculator"]["Guid"] == "calc-guid"


def test_get_endpoint_tree(monkeypatch):
    async def fake_get_endpoint_tree():
        return ["A", "B"]

    monkeypatch.setattr(discovery.qsar_client, "get_endpoint_tree", fake_get_endpoint_tree)

    result = asyncio.run(discovery.get_endpoint_tree())
    assert result == {"endpoint_tree": ["A", "B"]}


def test_get_metadata_hierarchy(monkeypatch):
    async def fake_get_meta():
        return [{"RigidPath": "X"}]

    monkeypatch.setattr(
        discovery.qsar_client, "get_metadata_hierarchy", fake_get_meta
    )

    result = asyncio.run(discovery.get_metadata_hierarchy())
    assert result == {"metadata_hierarchy": [{"RigidPath": "X"}]}


def test_list_qsar_models(monkeypatch):
    async def fake_list_models(position: str):
        return [{"Guid": "model", "Position": position}]

    monkeypatch.setattr(discovery.qsar_client, "list_qsar_models", fake_list_models)

    result = asyncio.run(discovery.list_qsar_models("ECOTOX"))
    assert result == {"position": "ECOTOX", "models": [{"Guid": "model", "Position": "ECOTOX"}]}


def test_list_search_databases(monkeypatch):
    async def fake_list_databases():
        return ["DB1", "DB2"]

    monkeypatch.setattr(
        discovery.qsar_client, "list_search_databases", fake_list_databases
    )

    result = asyncio.run(discovery.list_search_databases())
    assert result == {"databases": ["DB1", "DB2"]}
