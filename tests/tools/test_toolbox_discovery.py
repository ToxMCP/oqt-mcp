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
        return {
            "_name": "Foo",
            "_authors": "Jane Doe",
            "_donator": "OECD",
            "_url": "https://example.test/profiler",
            "_helpFile": "/tmp/profiler.pdf",
            "_additional": [{"_label": "Version", "_value": "1.2"}],
        }

    monkeypatch.setattr(
        discovery.qsar_client, "get_profiler_info", fake_get_profiler_info
    )

    result = asyncio.run(discovery.get_profiler_info("guid-123"))
    assert result["profiler"]["_name"] == "Foo"
    assert result["provenance"]["title"] == "Foo"
    assert result["provenance"]["authors"] == "Jane Doe"
    assert result["provenance"]["owner"] == "OECD"
    assert result["provenance"]["source_url"] == "https://example.test/profiler"
    assert result["provenance"]["help_file"] == "/tmp/profiler.pdf"
    assert result["provenance"]["additional_info"]["Version"] == "1.2"


def test_list_all_qsar_models(monkeypatch):
    async def fake_get_endpoint_tree():
        return ["A", "B"]

    async def fake_list_qsar_models(position: str):
        if position == "A":
            return [{"Guid": "model-1", "Caption": "Model 1", "Donator": "EPA"}]
        return [{"Guid": "model-2", "Caption": "Model 2", "Donator": "OECD"}]

    monkeypatch.setattr(
        discovery.qsar_client, "get_endpoint_tree", fake_get_endpoint_tree
    )
    monkeypatch.setattr(
        discovery.qsar_client, "list_qsar_models", fake_list_qsar_models
    )

    result = asyncio.run(discovery.list_all_qsar_models())
    assert len(result["catalog"]) == 2
    assert {item["Guid"] for item in result["catalog"]} == {"model-1", "model-2"}
    assert result["catalog"][0]["provenance_summary"]["owner"] == "EPA"
    assert result["status"] == "ok"
    assert result["catalog_metadata"]["positionsScanned"] == 2
    assert result["catalog_metadata"]["partial"] is False


def test_list_all_qsar_models_returns_partial_catalog_on_timeout(monkeypatch):
    async def fake_get_endpoint_tree():
        return ["A", "B"]

    async def fake_list_qsar_models(position: str):
        if position == "A":
            await asyncio.sleep(0.05)
            return [{"Guid": "model-1", "Caption": "Model 1", "Donator": "EPA"}]
        return [{"Guid": "model-2", "Caption": "Model 2", "Donator": "OECD"}]

    monkeypatch.setattr(
        discovery.qsar_client, "get_endpoint_tree", fake_get_endpoint_tree
    )
    monkeypatch.setattr(
        discovery.qsar_client, "list_qsar_models", fake_list_qsar_models
    )
    monkeypatch.setattr(
        discovery.settings.qsar,
        "QSAR_DISCOVERY_LIST_ALL_PER_POSITION_TIMEOUT_SECONDS",
        0.01,
    )

    result = asyncio.run(discovery.list_all_qsar_models())
    assert result["status"] == "partial"
    assert [item["Guid"] for item in result["catalog"]] == ["model-2"]
    assert result["catalog_metadata"]["timedOutPositions"] == ["A"]
    assert result["catalog_metadata"]["partial"] is True
    assert result["warnings"]


def test_list_simulators(monkeypatch):
    async def fake_list_simulators():
        return [{"Guid": "sim", "Caption": "Sim"}]

    monkeypatch.setattr(discovery.qsar_client, "list_simulators", fake_list_simulators)

    result = asyncio.run(discovery.list_simulators())
    assert result == {"simulators": [{"Guid": "sim", "Caption": "Sim"}]}


def test_get_simulator_info(monkeypatch):
    async def fake_get_simulator_info(simulator_guid: str):
        return {
            "_name": "Sim",
            "_authors": "LMC",
            "_donator": "LMC",
            "_url": "https://example.test/simulator",
        }

    monkeypatch.setattr(
        discovery.qsar_client, "get_simulator_info", fake_get_simulator_info
    )

    result = asyncio.run(discovery.get_simulator_info("sim-guid"))
    assert result["simulator"]["_name"] == "Sim"
    assert result["provenance"]["title"] == "Sim"
    assert result["provenance"]["authors"] == "LMC"
    assert result["provenance"]["owner"] == "LMC"


def test_list_calculators(monkeypatch):
    async def fake_list_calculators():
        return [{"Guid": "calc", "Caption": "Calculator"}]

    monkeypatch.setattr(
        discovery.qsar_client, "list_calculators", fake_list_calculators
    )

    result = asyncio.run(discovery.list_calculators())
    assert result == {"calculators": [{"Guid": "calc", "Caption": "Calculator"}]}


def test_get_calculator_info(monkeypatch):
    async def fake_get_calculator_info(calculator_guid: str):
        return {
            "Guid": calculator_guid,
            "Caption": "Calc",
            "Donator": "OECD",
            "Url": "https://example.test/calculator",
        }

    monkeypatch.setattr(
        discovery.qsar_client, "get_calculator_info", fake_get_calculator_info
    )

    result = asyncio.run(discovery.get_calculator_info("calc-guid"))
    assert result["calculator"]["Guid"] == "calc-guid"
    assert result["provenance"]["title"] == "Calc"
    assert result["provenance"]["owner"] == "OECD"
    assert result["provenance"]["source_url"] == "https://example.test/calculator"


def test_get_endpoint_tree(monkeypatch):
    async def fake_get_endpoint_tree():
        return ["A", "B"]

    monkeypatch.setattr(
        discovery.qsar_client, "get_endpoint_tree", fake_get_endpoint_tree
    )

    result = asyncio.run(discovery.get_endpoint_tree())
    assert result == {"endpoint_tree": ["A", "B"]}


def test_get_metadata_hierarchy(monkeypatch):
    async def fake_get_meta():
        return [{"RigidPath": "X"}]

    monkeypatch.setattr(discovery.qsar_client, "get_metadata_hierarchy", fake_get_meta)

    result = asyncio.run(discovery.get_metadata_hierarchy())
    assert result == {"metadata_hierarchy": [{"RigidPath": "X"}]}


def test_list_qsar_models(monkeypatch):
    async def fake_list_models(position: str):
        return [
            {
                "Guid": "model",
                "Position": position,
                "Caption": "Model",
                "Donator": "EPA",
            }
        ]

    monkeypatch.setattr(discovery.qsar_client, "list_qsar_models", fake_list_models)

    result = asyncio.run(discovery.list_qsar_models("ECOTOX"))
    assert result["position"] == "ECOTOX"
    assert result["models"][0]["Guid"] == "model"
    assert result["models"][0]["provenance_summary"]["title"] == "Model"
    assert result["models"][0]["provenance_summary"]["owner"] == "EPA"


def test_list_search_databases(monkeypatch):
    async def fake_list_databases():
        return ["DB1", "DB2"]

    monkeypatch.setattr(
        discovery.qsar_client, "list_search_databases", fake_list_databases
    )

    result = asyncio.run(discovery.list_search_databases())
    assert result == {"databases": ["DB1", "DB2"]}


def test_list_search_databases_fails_fast_on_timeout(monkeypatch):
    async def fake_list_databases():
        await asyncio.sleep(0.05)
        return ["DB1", "DB2"]

    monkeypatch.setattr(
        discovery.qsar_client, "list_search_databases", fake_list_databases
    )
    monkeypatch.setattr(
        discovery.settings.qsar,
        "QSAR_DISCOVERY_SEARCH_DATABASES_WALLCLOCK_TIMEOUT_SECONDS",
        0.01,
    )

    try:
        asyncio.run(discovery.list_search_databases())
    except discovery.QsarClientError as exc:
        assert "Timed out after" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected list_search_databases to time out")
