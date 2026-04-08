import asyncio
import base64
import io
import json
from pathlib import Path

import jsonschema
import pytest

from src.tools.implementations import toolbox_execution as execution

ROOT = Path(__file__).resolve().parents[2]


def _load_schema(name: str) -> dict:
    with (ROOT / "schemas" / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_run_qsar_model(monkeypatch):
    async def fake_apply(qsar_guid, chem_id):
        return {"Value": 1.23}

    async def fake_domain(qsar_guid, chem_id):
        return "In Domain"

    async def fake_model_metadata(qsar_guid):
        return {"Guid": qsar_guid, "Name": "Acute tox model", "Donator": "EPA"}

    monkeypatch.setattr(execution.qsar_client, "apply_qsar_model", fake_apply)
    monkeypatch.setattr(execution.qsar_client, "get_qsar_domain", fake_domain)
    monkeypatch.setattr(
        execution.qsar_client, "get_model_metadata", fake_model_metadata
    )

    result = asyncio.run(execution.run_qsar_model("model", "chem"))
    assert result["prediction"]["Value"] == 1.23
    assert result["domain"] == "In Domain"
    assert result["model_provenance"]["title"] == "Acute tox model"
    assert result["model_provenance"]["owner"] == "EPA"


def test_run_metabolism_simulator(monkeypatch):
    async def fake_sim(simulator_guid, chem_id):
        return ["metabolite"]

    async def fake_simulator_info(simulator_guid):
        return {"Guid": simulator_guid, "Caption": "Rat liver", "Donator": "OECD"}

    monkeypatch.setattr(
        execution.qsar_client, "simulate_metabolites_for_chem", fake_sim
    )
    monkeypatch.setattr(
        execution.qsar_client, "get_simulator_info", fake_simulator_info
    )

    params = execution.SimulatorExecuteParams(
        simulator_guid="sim", chem_id="chem", smiles=None
    )
    result = asyncio.run(
        execution.run_metabolism_simulator(
            params.simulator_guid, params.chem_id, params.smiles
        )
    )
    assert result["result"] == ["metabolite"]
    assert result["simulator_provenance"]["title"] == "Rat liver"
    assert result["simulator_provenance"]["owner"] == "OECD"


def test_canonicalize_structure(monkeypatch):
    async def fake_canon(smiles):
        return "C"  # canonical form

    monkeypatch.setattr(execution.qsar_client, "canonicalize_structure", fake_canon)

    result = asyncio.run(execution.canonicalize_structure("[CH3]"))
    assert result["canonical"] == "C"


def test_render_pdf_from_log(monkeypatch):
    fake_pdf = io.BytesIO(b"%PDF-1.4\n")

    monkeypatch.setattr(execution, "generate_pdf_report", lambda log: fake_pdf)

    result = asyncio.run(execution.render_pdf_from_log({"foo": "bar"}))
    assert result["size_bytes"] == len(b"%PDF-1.4\n")
    decoded = base64.b64decode(result["pdf_base64"])
    assert decoded == b"%PDF-1.4\n"


def test_build_portable_handoffs_from_workflow_log():
    log = {
        "identifier": "Benzene",
        "inputs": {
            "identifier": "Benzene",
            "search_type": "name",
            "context": "Publication-grade hazard assessment",
            "profiler_guids": ["prof-1"],
            "simulator_guids": ["sim-1"],
            "qsar_guids": ["qsar-1"],
        },
        "selected_chemical": {
            "ChemId": "chem-1",
            "Cas": "71-43-2",
            "Names": ["Benzene"],
            "Smiles": "c1ccccc1",
        },
        "profiler_results": [{"profiler_guid": "prof-1", "result": {"call": "ok"}}],
        "simulator_results": [{"simulator_guid": "sim-1", "result": [{"id": "m1"}]}],
        "qsar_results": [
            {
                "qsar_guid": "qsar-1",
                "prediction": {
                    "Value": "1.23",
                    "Unit": "mg/L",
                    "Endpoint": "LC50",
                    "DomainResult": "InDomain",
                },
                "domain": "InDomain",
            }
        ],
        "errors": [],
    }

    result = asyncio.run(execution.build_portable_handoffs_from_log(log))

    assert result["workflow_type"] == "workflow"
    workflow_record = result["portable_handoffs"]["oqtWorkflowRecord.v1"]
    jsonschema.validate(
        workflow_record,
        _load_schema("oqtWorkflowRecord.v1.json"),
    )
    jsonschema.validate(
        result["portable_handoffs"]["oqtHazardEvidenceSummary.v1"],
        _load_schema("oqtHazardEvidenceSummary.v1.json"),
    )
    assert workflow_record["packageSemantics"]["mode"] == "working_bundle"
    assert workflow_record["attachments"]
    assert result["portable_handoffs"]["oqtHazardEvidenceSummary.v1"][
        "requestMetadata"
    ]["requestedQsarModels"] == ["qsar-1"]
    assert (
        result["portable_handoffs"]["oqtHazardEvidenceSummary.v1"]["endpointSummaries"][
            0
        ]["endpoint"]
        == "LC50"
    )
    assert (
        result["portable_handoffs"]["oqtHazardEvidenceSummary.v1"]["decisionOwner"]
        == "downstream_expert_review"
    )
    assert (
        result["portable_handoffs"]["oqtHazardEvidenceSummary.v1"][
            "uncertaintyAssessment"
        ]["semanticCoverage"]["overallQuantificationStatus"]
        == "qualitative_only"
    )


def test_build_portable_handoffs_from_grouping_log():
    log = {
        "identifier": "Benzene",
        "inputs": {
            "identifier": "Benzene",
            "search_type": "name",
            "context": "Exploratory grouping dossier",
            "problem_formulation": "Assess exploratory repeated-dose toxicity read-across.",
            "decision_context": "hazard_identification",
            "route_of_exposure": "oral",
            "accepted_uncertainty_level": "medium",
            "profiler_guids": ["prof-1"],
            "simulator_guids": [],
            "qsar_guids": [],
        },
        "target_resolution": {"status": "resolved"},
        "profiler_results": [
            {
                "subject_role": "target",
                "subject_name": "Benzene",
                "chem_id": "chem-target",
                "profiler_guid": "prof-1",
                "result": {"call": "ok"},
            }
        ],
        "errors": [],
        "grouping_justification": {
            "report_context": {
                "identifier": "Benzene",
                "search_type": "name",
                "problem_formulation": "Assess exploratory repeated-dose toxicity read-across.",
                "decision_context": "hazard_identification",
                "grouping_hypothesis": "Simple aromatic hydrocarbons are expected to share relevant structural and mechanistic features.",
                "endpoints": ["Repeated dose toxicity"],
                "route_of_exposure": "oral",
                "accepted_uncertainty_level": "medium",
                "context": "Exploratory grouping dossier",
            },
            "target_substance": {
                "input_identifier": "Benzene",
                "preferred_name": "Benzene",
                "chem_id": "chem-target",
                "cas": "71-43-2",
                "smiles": "c1ccccc1",
            },
            "source_analogues": [
                {
                    "input_identifier": "Toluene",
                    "preferred_name": "Toluene",
                    "chem_id": "chem-source-1",
                }
            ],
            "excluded_analogues": [],
            "uncertainty_assessment": {
                "overall_level": "medium",
                "acceptable_for_context": True,
            },
            "endpoint_justifications": [
                {
                    "endpoint": "Repeated dose toxicity",
                    "conclusion": "Provisional analogue justification assembled for repeated dose toxicity.",
                    "confidence": "medium",
                    "residual_uncertainty": "medium",
                }
            ],
            "recommended_follow_ups": [],
        },
    }

    result = asyncio.run(execution.build_portable_handoffs_from_log(log))

    assert result["workflow_type"] == "grouping"
    read_across = result["portable_handoffs"]["oqtReadAcrossSummary.v1"]
    jsonschema.validate(
        result["portable_handoffs"]["oqtWorkflowRecord.v1"],
        _load_schema("oqtWorkflowRecord.v1.json"),
    )
    jsonschema.validate(
        read_across,
        _load_schema("oqtReadAcrossSummary.v1.json"),
    )
    assert read_across["dataMatrix"]["rowCount"] == 0
    assert read_across["uncertaintyTable"]["overallLevel"] == "medium"
    assert read_across["decisionOwner"] == "downstream_expert_review"
    assert read_across["supports"]["typedGroupingDossier"] is True


def test_run_profiler(monkeypatch):
    async def fake_profile(prof_guid, chem_id, simulator_guid=None):
        return {"result": "ok", "sim": simulator_guid}

    async def fake_profiler_info(prof_guid):
        return {"Guid": prof_guid, "_name": "Acute profiler", "_donator": "OECD"}

    monkeypatch.setattr(execution.qsar_client, "profile_with_profiler", fake_profile)
    monkeypatch.setattr(execution.qsar_client, "get_profiler_info", fake_profiler_info)

    result = asyncio.run(execution.run_profiler("prof", "chem"))
    assert result["profiler_guid"] == "prof"
    assert result["result"]["result"] == "ok"
    assert result["profiler_provenance"]["title"] == "Acute profiler"
    assert result["profiler_provenance"]["owner"] == "OECD"


def test_run_profiler_with_simulator(monkeypatch):
    async def fake_profile(prof_guid, chem_id, simulator_guid=None):
        return {"sim": simulator_guid}

    async def fake_profiler_info(prof_guid):
        return {"Guid": prof_guid, "_name": "Acute profiler", "_donator": "OECD"}

    monkeypatch.setattr(execution.qsar_client, "profile_with_profiler", fake_profile)
    monkeypatch.setattr(execution.qsar_client, "get_profiler_info", fake_profiler_info)

    result = asyncio.run(execution.run_profiler("prof", "chem", "sim"))
    assert result["simulator_guid"] == "sim"
    assert result["result"]["sim"] == "sim"


def test_run_metabolism_simulator_with_smiles(monkeypatch):
    async def fake_sim(simulator_guid, smiles):
        return ["metabolite"]

    async def fake_simulator_info(simulator_guid):
        return {"Guid": simulator_guid, "Caption": "Rat liver", "Donator": "OECD"}

    monkeypatch.setattr(
        execution.qsar_client,
        "simulate_metabolites_for_smiles",
        fake_sim,
    )
    monkeypatch.setattr(
        execution.qsar_client, "get_simulator_info", fake_simulator_info
    )

    params = execution.SimulatorExecuteParams(
        simulator_guid="sim", chem_id=None, smiles="CCO"
    )
    result = asyncio.run(
        execution.run_metabolism_simulator(
            params.simulator_guid, params.chem_id, params.smiles
        )
    )
    assert result["smiles"] == "CCO"
    assert result["simulator_provenance"]["title"] == "Rat liver"


def test_download_qmrf(monkeypatch):
    async def fake_qmrf(qsar_guid):
        return {"report": "qmrf"}

    async def fake_model_metadata(qsar_guid):
        return {"Guid": qsar_guid, "Name": "Acute tox model", "Donator": "EPA"}

    monkeypatch.setattr(execution.qsar_client, "generate_qmrf", fake_qmrf)
    monkeypatch.setattr(
        execution.qsar_client, "get_model_metadata", fake_model_metadata
    )

    result = asyncio.run(execution.download_qmrf("model", "chem"))
    decoded = base64.b64decode(result["qmrf_base64"]).decode("utf-8")
    payload = json.loads(decoded)
    assert payload["report"] == "qmrf"
    assert result["size_bytes"] > 0
    assert result["content_type"] == "application/octet-stream"
    assert result["model_provenance"]["title"] == "Acute tox model"


def test_download_qsar_report(monkeypatch):
    async def fake_report(chem_id, qsar_guid, comments):
        return {"report": True, "comments": comments}

    async def fake_model_metadata(qsar_guid):
        return {"Guid": qsar_guid, "Name": "Acute tox model", "Donator": "EPA"}

    monkeypatch.setattr(execution.qsar_client, "generate_qsar_report", fake_report)
    monkeypatch.setattr(
        execution.qsar_client, "get_model_metadata", fake_model_metadata
    )

    result = asyncio.run(execution.download_qsar_report("chem", "model", "note"))
    decoded = base64.b64decode(result["report_base64"]).decode("utf-8")
    payload = json.loads(decoded)
    assert payload["comments"] == "note"
    assert result["size_bytes"] > 0
    assert result["content_type"] == "application/octet-stream"
    assert result["model_provenance"]["title"] == "Acute tox model"


def test_execute_workflow(monkeypatch):
    async def fake_workflow(workflow_guid, chem_id):
        return {"workflow": workflow_guid, "chem": chem_id}

    monkeypatch.setattr(execution.qsar_client, "execute_workflow", fake_workflow)

    result = asyncio.run(execution.execute_workflow("wf", "chem"))
    assert result["result"]["workflow"] == "wf"


def test_download_workflow_report(monkeypatch):
    async def fake_workflow_report(chem_id, workflow_guid, comments):
        return {"report": True, "comments": comments}

    monkeypatch.setattr(execution.qsar_client, "workflow_report", fake_workflow_report)

    result = asyncio.run(execution.download_workflow_report("chem", "wf", "note"))
    decoded = base64.b64decode(result["report_base64"]).decode("utf-8")
    payload = json.loads(decoded)
    assert payload["comments"] == "note"
    assert result["size_bytes"] > 0


def test_group_chemicals(monkeypatch):
    async def fake_group(chem_id, profiler_guid):
        return ["chemA", "chemB"]

    async def fake_profiler_info(prof_guid):
        return {"Guid": prof_guid, "_name": "Grouping profiler", "_donator": "OECD"}

    monkeypatch.setattr(execution.qsar_client, "group_by_profiler", fake_group)
    monkeypatch.setattr(execution.qsar_client, "get_profiler_info", fake_profiler_info)

    result = asyncio.run(execution.group_chemicals("chem", "prof"))
    assert result["group"] == ["chemA", "chemB"]
    assert result["profiler_provenance"]["title"] == "Grouping profiler"


def test_structure_connectivity(monkeypatch):
    async def fake_conn(smiles):
        return "connect"

    monkeypatch.setattr(execution.qsar_client, "get_connectivity", fake_conn)

    result = asyncio.run(execution.structure_connectivity("CCO"))
    assert result["connectivity"] == "connect"
