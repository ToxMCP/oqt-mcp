import asyncio

from src.tools.implementations import o_qt_qsar_tools as qsar_tools


def test_get_public_qsar_model_info(monkeypatch):
    async def fake_get_model_metadata(model_id: str):
        return {"Guid": model_id, "Caption": "Model"}

    monkeypatch.setattr(
        qsar_tools.qsar_client, "get_model_metadata", fake_get_model_metadata
    )

    result = asyncio.run(qsar_tools.get_public_qsar_model_info("model-guid"))
    assert result == {"Guid": "model-guid", "Caption": "Model"}


def test_search_chemicals(monkeypatch):
    async def fake_search(query: str, search_type: str):
        return {"items": [{"Name": query, "SearchType": search_type}]}

    monkeypatch.setattr(qsar_tools.qsar_client, "search_chemicals", fake_search)

    result = asyncio.run(qsar_tools.search_chemicals("benzene", "name"))
    assert result["items"][0]["Name"] == "benzene"
    assert result["items"][0]["SearchType"] == "name"


def test_run_qsar_prediction(monkeypatch):
    async def fake_prediction(smiles: str, model_id: str):
        return {"SMILES": smiles, "Model": model_id, "Value": 1.23}

    monkeypatch.setattr(qsar_tools.qsar_client, "run_prediction", fake_prediction)

    result = asyncio.run(
        qsar_tools.run_qsar_prediction("CCO", "model-123")
    )
    assert result["Model"] == "model-123"
    assert result["SMILES"] == "CCO"


def test_analyze_chemical_hazard(monkeypatch):
    calls: dict[str, tuple] = {}

    async def fake_endpoint_data(chemical_identifier: str, endpoint: str):
        calls["endpoint"] = (chemical_identifier, endpoint)
        return {"Guid": "endpoint-guid", "Endpoint": endpoint}

    async def fake_profile(chemical_identifier: str):
        calls["profile"] = (chemical_identifier,)
        return {"Profile": ["alert"]}

    monkeypatch.setattr(
        qsar_tools.qsar_client, "get_endpoint_data", fake_endpoint_data
    )
    monkeypatch.setattr(
        qsar_tools.qsar_client, "profile_chemical", fake_profile
    )

    result = asyncio.run(
        qsar_tools.analyze_chemical_hazard("50-00-0", "Mutagenicity")
    )

    assert result["chemical_identifier"] == "50-00-0"
    assert result["endpoint"] == "Mutagenicity"
    assert result["endpoint_data"]["Endpoint"] == "Mutagenicity"
    assert result["profiling"]["Profile"] == ["alert"]
    assert calls["endpoint"] == ("50-00-0", "Mutagenicity")
    assert calls["profile"] == ("50-00-0",)


def test_generate_metabolites(monkeypatch):
    async def fake_generate(smiles: str, simulator: str):
        return {"Simulated": True, "Simulator": simulator, "SMILES": smiles}

    monkeypatch.setattr(
        qsar_tools.qsar_client, "generate_metabolites", fake_generate
    )

    result = asyncio.run(
        qsar_tools.generate_metabolites("CCO", "Liver")
    )
    assert result["Simulated"] is True
    assert result["Simulator"] == "Liver"
    assert result["SMILES"] == "CCO"
