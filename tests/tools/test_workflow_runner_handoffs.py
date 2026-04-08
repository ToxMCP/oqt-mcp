import asyncio
import io
import json
from pathlib import Path

import jsonschema

from src.tools.implementations import workflow_runner

ROOT = Path(__file__).resolve().parents[2]


def _load_schema(name: str) -> dict:
    path = ROOT / "schemas" / name
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _stub_pdf(*_args, **_kwargs):
    return io.BytesIO(b"%PDF-1.4\n")


def test_run_oqt_multiagent_workflow_emits_portable_handoffs(monkeypatch):
    async def fake_search(identifier, search_type, with_meta=False):
        payload = [
            {
                "ChemId": "chem-1",
                "Cas": "71-43-2",
                "Names": ["Benzene"],
                "Smiles": "c1ccccc1",
            }
        ]
        meta = {"duration_ms": 12.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    async def fake_profile(
        profiler_guid, chem_id, simulator_guid=None, with_meta=False
    ):
        payload = {"classification": "baseline narcosis", "chem_id": chem_id}
        meta = {"duration_ms": 10.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    async def fake_simulator(simulator_guid, chem_id, with_meta=False):
        payload = [{"name": "Metabolite A", "chem_id": chem_id}]
        meta = {"duration_ms": 8.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    async def fake_qsar(qsar_guid, chem_id, with_meta=False):
        payload = {
            "Value": "1.23",
            "Unit": "mg/L",
            "Endpoint": "LC50",
            "DomainResult": "InDomain",
            "chem_id": chem_id,
        }
        meta = {"duration_ms": 14.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    async def fake_domain(qsar_guid, chem_id, with_meta=False):
        payload = {"status": "in_domain", "chem_id": chem_id}
        meta = {"duration_ms": 6.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    async def fake_profiler_info(profiler_guid, with_meta=False):
        payload = {"Guid": profiler_guid, "_name": "Acute profiler", "_donator": "OECD"}
        meta = {"duration_ms": 4.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    async def fake_simulator_info(simulator_guid, with_meta=False):
        payload = {"Guid": simulator_guid, "_name": "Rat liver", "_donator": "OECD"}
        meta = {"duration_ms": 4.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    async def fake_model_info(qsar_guid, with_meta=False):
        payload = {"Guid": qsar_guid, "Name": "Acute tox model", "Donator": "EPA"}
        meta = {"duration_ms": 4.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    monkeypatch.setattr(workflow_runner, "generate_pdf_report", _stub_pdf)
    monkeypatch.setattr(
        workflow_runner.oqt_assistant,
        "resolve_assistant_config",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(workflow_runner.qsar_client, "search_chemicals", fake_search)
    monkeypatch.setattr(
        workflow_runner.qsar_client, "profile_with_profiler", fake_profile
    )
    monkeypatch.setattr(
        workflow_runner.qsar_client,
        "simulate_metabolites_for_chem",
        fake_simulator,
    )
    monkeypatch.setattr(workflow_runner.qsar_client, "apply_qsar_model", fake_qsar)
    monkeypatch.setattr(workflow_runner.qsar_client, "get_qsar_domain", fake_domain)
    monkeypatch.setattr(
        workflow_runner.qsar_client, "get_profiler_info", fake_profiler_info
    )
    monkeypatch.setattr(
        workflow_runner.qsar_client, "get_simulator_info", fake_simulator_info
    )
    monkeypatch.setattr(
        workflow_runner.qsar_client, "get_model_metadata", fake_model_info
    )

    response = asyncio.run(
        workflow_runner.run_oqt_multiagent_workflow(
            identifier="Benzene",
            search_type="name",
            context="Publication-grade hazard assessment",
            profiler_guids=["prof-1"],
            qsar_mode="recommended",
            qsar_guids=["qsar-1"],
            simulator_guids=["sim-1"],
            llm_provider=None,
            llm_model=None,
            llm_api_key=None,
        )
    )

    handoffs = response["portable_handoffs"]
    workflow_record = handoffs["oqtWorkflowRecord.v1"]
    hazard_summary = handoffs["oqtHazardEvidenceSummary.v1"]

    jsonschema.validate(workflow_record, _load_schema("oqtWorkflowRecord.v1.json"))
    jsonschema.validate(
        hazard_summary, _load_schema("oqtHazardEvidenceSummary.v1.json")
    )

    assert (
        workflow_record["toolchain"]["primaryEntrypoint"]
        == "run_oqt_multiagent_workflow"
    )
    assert workflow_record["rootEntity"]["entityType"] == "workflow_execution"
    assert workflow_record["packageSemantics"]["mode"] == "working_bundle"
    assert len(workflow_record["attachments"]) == 3
    assert workflow_record["artifacts"]["json"]["checksumSha256"]
    assert workflow_record["artifacts"]["pdf"]["sizeBytes"] == len(b"%PDF-1.4\n")
    assert hazard_summary["chemicalIdentity"]["preferredName"] == "Benzene"
    assert hazard_summary["profilers"][0]["status"] == "ok"
    assert hazard_summary["profilers"][0]["source"]["owner"] == "OECD"
    assert hazard_summary["qsarFindings"][0]["endpoint"] == "LC50"
    assert hazard_summary["qsarFindings"][0]["domainStatus"] == "InDomain"
    assert hazard_summary["qsarFindings"][0]["source"]["owner"] == "EPA"
    assert hazard_summary["endpointSummaries"][0]["evidenceBasis"] == "qsar_prediction"
    assert hazard_summary["evidenceBlocks"]["qsar"]["status"] == "present"
    assert (
        hazard_summary["evidenceBlocks"]["qsar"]["references"][0]["referenceId"]
        == "qsar-1"
    )
    assert hazard_summary["requestMetadata"]["requestedQsarModels"] == ["qsar-1"]
    assert (
        hazard_summary["assessmentBoundary"]["scope"]
        == "module_scoped_toolbox_evidence_packaging"
    )
    assert hazard_summary["decisionBoundary"]["reviewRequired"] is True
    assert hazard_summary["decisionOwner"] == "downstream_expert_review"
    assert hazard_summary["supports"]["typedProfilerEvidence"] is True
    assert hazard_summary["supports"]["typedApplicabilityDomainReview"] is True
    assert hazard_summary["requiredExternalInputs"]
    assert (
        hazard_summary["uncertaintyAssessment"]["method"]
        == "qualitative_evidence_completeness"
    )
    assert hazard_summary["uncertaintyAssessment"]["coverage"]["qsar"] == "present"
    assert (
        hazard_summary["uncertaintyAssessment"]["semanticCoverage"][
            "overallQuantificationStatus"
        ]
        == "qualitative_only"
    )
    assert (
        hazard_summary["uncertaintyAssessment"]["semanticCoverage"][
            "typedApplicabilityDomainStatus"
        ]
        == "present"
    )
    assert hazard_summary["applicabilityDomain"]["overallStatus"] == "in_domain"
    assert (
        hazard_summary["applicabilityDomain"]["modelAssessments"][0]["domainStatusRaw"]
        == "InDomain"
    )
    assert "workflow/search" in hazard_summary["provenance"]["sourceTools"]
    assert (
        response["log_json"]["profiler_results"][0]["profiler_provenance"]["title"]
        == "Acute profiler"
    )
    assert (
        response["log_json"]["simulator_results"][0]["simulator_provenance"]["title"]
        == "Rat liver"
    )
    assert response["log_json"]["qsar_results"][0]["model_provenance"]["owner"] == "EPA"


def test_run_oqt_multiagent_workflow_accepts_direct_chem_id(monkeypatch):
    async def fake_search(*_args, **_kwargs):
        raise AssertionError("search_chemicals should not be called for a chemId input")

    async def fake_profile(
        profiler_guid, chem_id, simulator_guid=None, with_meta=False
    ):
        payload = {"classification": "baseline narcosis", "chem_id": chem_id}
        meta = {"duration_ms": 10.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    async def fake_simulator(simulator_guid, chem_id, with_meta=False):
        payload = [{"name": "Metabolite A", "chem_id": chem_id}]
        meta = {"duration_ms": 8.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    async def fake_qsar(qsar_guid, chem_id, with_meta=False):
        payload = {
            "Value": "1.23",
            "Unit": "mg/L",
            "Endpoint": "LC50",
            "DomainResult": "InDomain",
            "chem_id": chem_id,
        }
        meta = {"duration_ms": 14.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    async def fake_domain(qsar_guid, chem_id, with_meta=False):
        payload = {"status": "in_domain", "chem_id": chem_id}
        meta = {"duration_ms": 6.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    async def fake_profiler_info(profiler_guid, with_meta=False):
        payload = {"Guid": profiler_guid, "_name": "Acute profiler", "_donator": "OECD"}
        meta = {"duration_ms": 4.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    async def fake_simulator_info(simulator_guid, with_meta=False):
        payload = {"Guid": simulator_guid, "_name": "Rat liver", "_donator": "OECD"}
        meta = {"duration_ms": 4.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    async def fake_model_info(qsar_guid, with_meta=False):
        payload = {"Guid": qsar_guid, "Name": "Acute tox model", "Donator": "EPA"}
        meta = {"duration_ms": 4.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    monkeypatch.setattr(workflow_runner, "generate_pdf_report", _stub_pdf)
    monkeypatch.setattr(
        workflow_runner.oqt_assistant,
        "resolve_assistant_config",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(workflow_runner.qsar_client, "search_chemicals", fake_search)
    monkeypatch.setattr(
        workflow_runner.qsar_client, "profile_with_profiler", fake_profile
    )
    monkeypatch.setattr(
        workflow_runner.qsar_client,
        "simulate_metabolites_for_chem",
        fake_simulator,
    )
    monkeypatch.setattr(workflow_runner.qsar_client, "apply_qsar_model", fake_qsar)
    monkeypatch.setattr(workflow_runner.qsar_client, "get_qsar_domain", fake_domain)
    monkeypatch.setattr(
        workflow_runner.qsar_client, "get_profiler_info", fake_profiler_info
    )
    monkeypatch.setattr(
        workflow_runner.qsar_client, "get_simulator_info", fake_simulator_info
    )
    monkeypatch.setattr(
        workflow_runner.qsar_client, "get_model_metadata", fake_model_info
    )

    response = asyncio.run(
        workflow_runner.run_oqt_multiagent_workflow(
            identifier="25511866-347f-d9f9-d598-d23f9501a8cb",
            search_type="auto",
            context="Direct chemId workflow",
            profiler_guids=["prof-1"],
            qsar_mode="recommended",
            qsar_guids=["qsar-1"],
            simulator_guids=["sim-1"],
            llm_provider=None,
            llm_model=None,
            llm_api_key=None,
        )
    )

    assert response["status"] == "ok"
    assert (
        response["log_json"]["selected_chemical"]["ChemId"]
        == "25511866-347f-d9f9-d598-d23f9501a8cb"
    )


def test_build_grouping_justification_emits_portable_handoffs(monkeypatch):
    async def fake_search(identifier, search_type, with_meta=False):
        payload_map = {
            "Benzene": {
                "ChemId": "chem-target",
                "Cas": "71-43-2",
                "Names": ["Benzene"],
                "Smiles": "c1ccccc1",
            },
            "Toluene": {
                "ChemId": "chem-source-1",
                "Cas": "108-88-3",
                "Names": ["Toluene"],
                "Smiles": "Cc1ccccc1",
            },
            "Ethylbenzene": {
                "ChemId": "chem-source-2",
                "Cas": "100-41-4",
                "Names": ["Ethylbenzene"],
                "Smiles": "CCc1ccccc1",
            },
        }
        payload = [payload_map[identifier]]
        meta = {"duration_ms": 12.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    async def fake_canonicalize(smiles, with_meta=False):
        payload = smiles
        meta = {"duration_ms": 3.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    async def fake_connectivity(smiles, with_meta=False):
        payload = f"connectivity:{smiles}"
        meta = {"duration_ms": 4.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    async def fake_profile(
        profiler_guid, chem_id, simulator_guid=None, with_meta=False
    ):
        payload = {"classification": "aromatic hydrocarbon", "chem_id": chem_id}
        meta = {"duration_ms": 10.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    async def fake_group_by_profiler(chem_id, profiler_guid, with_meta=False):
        payload = {"members": [chem_id], "profiler_guid": profiler_guid}
        meta = {"duration_ms": 9.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    async def fake_simulator(simulator_guid, chem_id, with_meta=False):
        payload = [{"name": "Metabolite A", "chem_id": chem_id}]
        meta = {"duration_ms": 8.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    async def fake_qsar(qsar_guid, chem_id, with_meta=False):
        payload = {"value": 0.77, "chem_id": chem_id}
        meta = {"duration_ms": 11.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    async def fake_domain(qsar_guid, chem_id, with_meta=False):
        payload = {"status": "in_domain", "chem_id": chem_id}
        meta = {"duration_ms": 5.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    async def fake_profiler_info(profiler_guid, with_meta=False):
        payload = {
            "Guid": profiler_guid,
            "_name": "Grouping profiler",
            "_donator": "OECD",
        }
        meta = {"duration_ms": 4.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    async def fake_simulator_info(simulator_guid, with_meta=False):
        payload = {"Guid": simulator_guid, "_name": "Rat liver", "_donator": "OECD"}
        meta = {"duration_ms": 4.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    async def fake_model_info(qsar_guid, with_meta=False):
        payload = {"Guid": qsar_guid, "Name": "Repeated-dose model", "Donator": "EPA"}
        meta = {"duration_ms": 4.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    monkeypatch.setattr(workflow_runner, "generate_pdf_report", _stub_pdf)
    monkeypatch.setattr(workflow_runner.qsar_client, "search_chemicals", fake_search)
    monkeypatch.setattr(
        workflow_runner.qsar_client,
        "canonicalize_structure",
        fake_canonicalize,
    )
    monkeypatch.setattr(
        workflow_runner.qsar_client, "get_connectivity", fake_connectivity
    )
    monkeypatch.setattr(
        workflow_runner.qsar_client, "profile_with_profiler", fake_profile
    )
    monkeypatch.setattr(
        workflow_runner.qsar_client, "group_by_profiler", fake_group_by_profiler
    )
    monkeypatch.setattr(
        workflow_runner.qsar_client,
        "simulate_metabolites_for_chem",
        fake_simulator,
    )
    monkeypatch.setattr(workflow_runner.qsar_client, "apply_qsar_model", fake_qsar)
    monkeypatch.setattr(workflow_runner.qsar_client, "get_qsar_domain", fake_domain)
    monkeypatch.setattr(
        workflow_runner.qsar_client, "get_profiler_info", fake_profiler_info
    )
    monkeypatch.setattr(
        workflow_runner.qsar_client, "get_simulator_info", fake_simulator_info
    )
    monkeypatch.setattr(
        workflow_runner.qsar_client, "get_model_metadata", fake_model_info
    )

    response = asyncio.run(
        workflow_runner.build_grouping_justification(
            identifier="Benzene",
            search_type="name",
            problem_formulation="Assess exploratory repeated-dose toxicity read-across.",
            decision_context="hazard_identification",
            endpoints=["Repeated dose toxicity"],
            route_of_exposure="oral",
            grouping_hypothesis="Simple aromatic hydrocarbons are expected to share relevant structural and mechanistic features.",
            analogue_identifiers=["Toluene", "Ethylbenzene"],
            analogue_search_type="name",
            profiler_guids=["prof-1"],
            simulator_guids=["sim-1"],
            qsar_guids=["qsar-1"],
            accepted_uncertainty_level="medium",
            context="Exploratory grouping dossier",
        )
    )

    handoffs = response["portable_handoffs"]
    workflow_record = handoffs["oqtWorkflowRecord.v1"]
    read_across_summary = handoffs["oqtReadAcrossSummary.v1"]

    jsonschema.validate(workflow_record, _load_schema("oqtWorkflowRecord.v1.json"))
    jsonschema.validate(
        read_across_summary, _load_schema("oqtReadAcrossSummary.v1.json")
    )

    assert (
        workflow_record["toolchain"]["primaryEntrypoint"]
        == "build_grouping_justification"
    )
    assert workflow_record["rootEntity"]["entityType"] == "grouping_dossier"
    assert workflow_record["attachments"][0]["name"].startswith("grouping-dossier-")
    assert read_across_summary["chemicalIdentity"]["preferredName"] == "Benzene"
    assert len(read_across_summary["analogues"]) == 2
    assert (
        read_across_summary["assessmentBoundary"]["scope"]
        == "module_scoped_grouping_dossier_packaging"
    )
    assert read_across_summary["decisionBoundary"]["reviewRequired"] is True
    assert read_across_summary["decisionOwner"] == "downstream_expert_review"
    assert read_across_summary["supports"]["typedGroupingDossier"] is True
    assert read_across_summary["supports"]["finalReadAcrossAcceptance"] is False
    assert read_across_summary["requiredExternalInputs"]
    assert read_across_summary["applicabilityDomain"]["supportingSimilarityContexts"]
    assert read_across_summary["dataMatrix"]["rowCount"] >= 1
    assert read_across_summary["uncertaintyTable"]["overallLevel"] in {
        "low",
        "medium",
        "high",
    }
    assert "search_chemicals" not in read_across_summary["provenance"].get(
        "sourceTools", []
    )
    assert (
        response["log_json"]["profiler_results"][0]["profiler_provenance"]["title"]
        == "Grouping profiler"
    )
    assert (
        response["log_json"]["simulator_results"][0]["simulator_provenance"]["title"]
        == "Rat liver"
    )
    assert (
        response["log_json"]["qsar_results"][0]["model_provenance"]["title"]
        == "Repeated-dose model"
    )
