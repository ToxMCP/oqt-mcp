import asyncio
import json
from pathlib import Path

import jsonschema

from src.tools.implementations import o_qt_qsar_tools as qsar_tools

ROOT = Path(__file__).resolve().parents[2]


def _load_schema(name: str) -> dict:
    with (ROOT / "schemas" / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_get_public_qsar_model_info(monkeypatch):
    async def fake_get_model_metadata(model_id: str):
        return {
            "Guid": model_id,
            "Name": "Model",
            "Donator": "EPA",
            "Authors": "Jane Doe",
            "Url": "https://example.test/model",
            "AdditionalInfo": {"Version": "1.0"},
        }

    monkeypatch.setattr(
        qsar_tools.qsar_client, "get_model_metadata", fake_get_model_metadata
    )

    result = asyncio.run(qsar_tools.get_public_qsar_model_info("model-guid"))
    assert result["Guid"] == "model-guid"
    assert result["provenance"]["title"] == "Model"
    assert result["provenance"]["owner"] == "EPA"
    assert result["provenance"]["authors"] == "Jane Doe"
    assert result["provenance"]["source_url"] == "https://example.test/model"
    assert result["provenance"]["additional_info"]["Version"] == "1.0"


def test_search_chemicals(monkeypatch):
    async def fake_search(query: str, search_type: str):
        return {"items": [{"Name": query, "SearchType": search_type}]}

    monkeypatch.setattr(qsar_tools.qsar_client, "search_chemicals", fake_search)

    result = asyncio.run(qsar_tools.search_chemicals("benzene", "name"))
    assert result["items"][0]["Name"] == "benzene"
    assert result["items"][0]["SearchType"] == "name"


def test_run_qsar_prediction(monkeypatch):
    async def fake_search_chemicals(smiles: str, search_type: str):
        raise qsar_tools.QsarClientError("search unavailable in unit test")

    async def fake_prediction(smiles: str, model_id: str):
        return {"SMILES": smiles, "Model": model_id, "Value": 1.23}

    async def fake_model_metadata(model_id: str):
        return {"Guid": model_id, "Name": "Aquatic model", "Donator": "EPA"}

    monkeypatch.setattr(
        qsar_tools.qsar_client, "search_chemicals", fake_search_chemicals
    )
    monkeypatch.setattr(qsar_tools.qsar_client, "run_prediction", fake_prediction)
    monkeypatch.setattr(
        qsar_tools.qsar_client, "get_model_metadata", fake_model_metadata
    )

    result = asyncio.run(qsar_tools.run_qsar_prediction("CCO", "model-123"))
    assert result["Model"] == "model-123"
    assert result["SMILES"] == "CCO"
    assert result["model_provenance"]["title"] == "Aquatic model"
    assert result["model_provenance"]["owner"] == "EPA"


def test_run_qsar_prediction_ad_warning_out_of_domain(monkeypatch):
    async def fake_search_chemicals(smiles: str, search_type: str):
        return [{"ChemId": "chem-123"}]

    async def fake_apply_qsar_model(model_id: str, chem_id: str):
        return {"Value": 0.5}

    async def fake_get_qsar_domain(model_id: str, chem_id: str):
        return "OutOfDomain"

    async def fake_model_metadata(model_id: str):
        return {"Guid": model_id, "Name": "Test model", "Donator": "EPA"}

    monkeypatch.setattr(
        qsar_tools.qsar_client, "search_chemicals", fake_search_chemicals
    )
    monkeypatch.setattr(
        qsar_tools.qsar_client, "apply_qsar_model", fake_apply_qsar_model
    )
    monkeypatch.setattr(
        qsar_tools.qsar_client, "get_qsar_domain", fake_get_qsar_domain
    )
    monkeypatch.setattr(
        qsar_tools.qsar_client, "get_model_metadata", fake_model_metadata
    )

    result = asyncio.run(qsar_tools.run_qsar_prediction("CCO", "model-123"))
    assert result["ad_status"] == "out_of_domain"
    assert result["ad_warning"] is True
    assert "ad_recommendation" in result


def test_analyze_chemical_hazard(monkeypatch):
    calls: dict[str, tuple | None] = {}

    async def fake_endpoint_data(
        chemical_identifier: str,
        endpoint: str | None = None,
        position: str | None = None,
        include_metadata: bool = False,
    ):
        calls["endpoint"] = (chemical_identifier, endpoint)
        calls["position"] = (chemical_identifier, position, include_metadata)
        return {
            "Guid": "endpoint-guid",
            "Endpoint": endpoint or "Gene mutation",
            "Study": "Ames assay",
            "Citation": "Doe et al. 2024",
            "Owner": "Curated DB",
        }

    async def fake_profile(chemical_identifier: str):
        calls["profile"] = (chemical_identifier,)
        return {"Profile": ["alert"]}

    async def fake_get_endpoint_tree():
        return [
            "Human Health Hazards#Genetic Toxicity",
            "Human Health Hazards#Sensitisation",
        ]

    monkeypatch.setattr(qsar_tools.qsar_client, "get_endpoint_data", fake_endpoint_data)
    monkeypatch.setattr(qsar_tools.qsar_client, "profile_chemical", fake_profile)
    monkeypatch.setattr(
        qsar_tools.qsar_client, "get_endpoint_tree", fake_get_endpoint_tree
    )

    result = asyncio.run(qsar_tools.analyze_chemical_hazard("50-00-0", "Mutagenicity"))
    portable_summary = result["portable_handoffs"]["oqtHazardEvidenceSummary.v1"]

    jsonschema.validate(
        portable_summary, _load_schema("oqtHazardEvidenceSummary.v1.json")
    )

    assert result["chemical_identifier"] == "50-00-0"
    assert result["endpoint"] == "Mutagenicity"
    assert (
        result["resolved_endpoint_position"] == "Human Health Hazards#Genetic Toxicity"
    )
    assert result["endpoint_resolution"]["strategy"] == "alias"
    assert result["endpoint_data"]["Endpoint"] == "Gene mutation"
    assert result["profiling"]["Profile"] == ["alert"]
    assert result["endpoint_study_records"][0]["study"] == "Ames assay"
    assert result["endpoint_summaries"][0]["recordCount"] == 1
    assert result["evidence_blocks"]["endpointData"]["status"] == "present"
    assert result["evidence_blocks"]["profiling"]["status"] == "present"
    assert result["applicability_domain"]["overallStatus"] == "not_applicable"
    assert result["uncertainty_assessment"]["coverage"]["endpointData"] == "present"
    assert portable_summary["endpointSummaries"][0]["endpoint"] == "Gene mutation"
    assert (
        portable_summary["evidenceBlocks"]["endpointData"]["references"][0]["study"]
        == "Ames assay"
    )
    assert portable_summary["applicabilityDomain"]["overallStatus"] == "not_applicable"
    assert portable_summary["requestMetadata"]["requestedEndpoints"] == ["Mutagenicity"]
    assert (
        portable_summary["assessmentBoundary"]["scope"]
        == "module_scoped_toolbox_evidence_packaging"
    )
    assert portable_summary["decisionBoundary"]["reviewRequired"] is True
    assert portable_summary["decisionOwner"] == "downstream_expert_review"
    assert portable_summary["supports"]["typedStudyEvidence"] is True
    assert portable_summary["supports"]["typedProfilerEvidence"] is False
    assert portable_summary["requiredExternalInputs"]
    assert (
        portable_summary["uncertaintyAssessment"]["semanticCoverage"][
            "overallQuantificationStatus"
        ]
        == "qualitative_only"
    )
    assert (
        portable_summary["uncertaintyAssessment"]["semanticCoverage"][
            "typedStudyRecordStatus"
        ]
        == "present"
    )
    assert (
        portable_summary["uncertaintyAssessment"]["semanticCoverage"][
            "typedApplicabilityDomainStatus"
        ]
        == "not_applicable"
    )
    assert result["endpoint_data_provenance"][0]["study"] == "Ames assay"
    assert result["endpoint_data_provenance"][0]["citation"] == "Doe et al. 2024"
    assert result["endpoint_data_provenance"][0]["owner"] == "Curated DB"
    assert calls["position"] == (
        "50-00-0",
        "Human Health Hazards#Genetic Toxicity",
        True,
    )
    assert calls["endpoint"] == ("50-00-0", None)
    assert calls["profile"] == ("50-00-0",)


def test_analyze_chemical_hazard_falls_back_to_raw_endpoint(monkeypatch):
    calls: dict[str, tuple | None] = {}

    async def fake_get_endpoint_tree():
        return []

    async def fake_endpoint_data(
        chemical_identifier: str,
        endpoint: str | None = None,
        position: str | None = None,
        include_metadata: bool = False,
    ):
        calls["endpoint"] = (chemical_identifier, endpoint, position, include_metadata)
        return {"Endpoint": endpoint, "Study": "Study"}

    async def fake_profile(chemical_identifier: str):
        calls["profile"] = (chemical_identifier,)
        return {"Profile": []}

    monkeypatch.setattr(
        qsar_tools.qsar_client, "get_endpoint_tree", fake_get_endpoint_tree
    )
    monkeypatch.setattr(qsar_tools.qsar_client, "get_endpoint_data", fake_endpoint_data)
    monkeypatch.setattr(qsar_tools.qsar_client, "profile_chemical", fake_profile)

    result = asyncio.run(
        qsar_tools.analyze_chemical_hazard("50-00-0", "Custom Endpoint")
    )

    assert result["endpoint_resolution"]["strategy"] == "raw-endpoint"
    assert "resolved_endpoint_position" not in result
    assert calls["endpoint"] == ("50-00-0", "Custom Endpoint", None, True)


def test_analyze_chemical_hazard_with_direct_chem_id_populates_identity(monkeypatch):
    async def fake_get_endpoint_tree():
        return ["Human Health Hazards#Genetic Toxicity"]

    async def fake_endpoint_data(
        chemical_identifier: str,
        endpoint: str | None = None,
        position: str | None = None,
        include_metadata: bool = False,
    ):
        return {"Endpoint": endpoint or position}

    async def fake_profile(chemical_identifier: str):
        return {"Profile": []}

    monkeypatch.setattr(
        qsar_tools.qsar_client, "get_endpoint_tree", fake_get_endpoint_tree
    )
    monkeypatch.setattr(qsar_tools.qsar_client, "get_endpoint_data", fake_endpoint_data)
    monkeypatch.setattr(qsar_tools.qsar_client, "profile_chemical", fake_profile)

    chem_id = "25511866-347f-d9f9-d598-d23f9501a8cb"
    result = asyncio.run(qsar_tools.analyze_chemical_hazard(chem_id, "Mutagenicity"))

    assert result["chemical_identity"]["chem_id"] == chem_id
    assert result["chemical_identity"]["preferred_name"] == chem_id
    assert (
        result["portable_handoffs"]["oqtHazardEvidenceSummary.v1"]["chemicalIdentity"][
            "chemId"
        ]
        == chem_id
    )


def test_generate_metabolites(monkeypatch):
    async def fake_generate(smiles: str, simulator: str):
        return {"Simulated": True, "Simulator": simulator, "SMILES": smiles}

    async def fake_list_simulators():
        return []

    async def fake_simulator_info(simulator_guid: str):
        return {"Guid": simulator_guid, "Caption": "Rat liver", "Donator": "OECD"}

    monkeypatch.setattr(qsar_tools.qsar_client, "generate_metabolites", fake_generate)
    monkeypatch.setattr(qsar_tools.qsar_client, "list_simulators", fake_list_simulators)
    monkeypatch.setattr(
        qsar_tools.qsar_client, "get_simulator_info", fake_simulator_info
    )

    result = asyncio.run(qsar_tools.generate_metabolites("CCO", "Liver"))
    assert result["smiles"] == "CCO"
    assert result["simulator_guid"] == "Liver"
    assert result["metabolites"]["Simulated"] is True
    assert result["metabolites"]["Simulator"] == "Liver"
    assert result["metabolites"]["SMILES"] == "CCO"
    assert result["simulator_provenance"]["title"] == "Rat liver"
    assert result["simulator_provenance"]["owner"] == "OECD"


def test_analyze_chemical_hazard_times_out_profiling_but_returns_endpoint_data(
    monkeypatch,
):
    async def fake_get_endpoint_tree():
        return ["Human Health Hazards#Genetic Toxicity"]

    async def fake_endpoint_data(
        chemical_identifier: str,
        endpoint: str | None = None,
        position: str | None = None,
        include_metadata: bool = False,
    ):
        return {
            "Endpoint": "Gene mutation",
            "Study": "Ames assay",
            "Citation": "Doe et al. 2024",
            "Owner": "Curated DB",
        }

    async def fake_profile(chemical_identifier: str):
        await asyncio.sleep(0.05)
        return {"Profile": ["alert"]}

    monkeypatch.setattr(
        qsar_tools.qsar_client, "get_endpoint_tree", fake_get_endpoint_tree
    )
    monkeypatch.setattr(qsar_tools.qsar_client, "get_endpoint_data", fake_endpoint_data)
    monkeypatch.setattr(qsar_tools.qsar_client, "profile_chemical", fake_profile)
    monkeypatch.setattr(
        qsar_tools.settings.qsar,
        "QSAR_HAZARD_PROFILING_WALLCLOCK_TIMEOUT_SECONDS",
        0.01,
    )

    result = asyncio.run(qsar_tools.analyze_chemical_hazard("50-00-0", "Mutagenicity"))

    assert result["data_availability"]["endpoint_data_available"] is True
    assert result["data_availability"]["profiling_data_available"] is False
    assert "Timed out after" in result["profiling_error"]
    assert result["endpoint_summaries"][0]["recordCount"] == 1
    assert result["uncertainty_assessment"]["coverage"]["profiling"] == "none"
