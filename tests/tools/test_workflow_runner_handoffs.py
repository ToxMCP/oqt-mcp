import asyncio
import hashlib
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


def test_build_attachment_manifest_packaged_dossier_manifest_lists_pdf():
    artifacts = {
        "json": workflow_runner._build_artifact_entry(
            field_name="log_json",
            delivery="inline",
            media_type="application/json",
            description="Comprehensive workflow log bundle.",
            payload={"status": "ok"},
        ),
        "markdown": workflow_runner._build_artifact_entry(
            field_name="summary_markdown",
            delivery="inline",
            media_type="text/markdown",
            description="Human-readable workflow narrative.",
            payload="# Summary",
        ),
        "pdf": workflow_runner._build_artifact_entry(
            field_name="pdf_report_base64",
            delivery="inline",
            media_type="application/pdf",
            description="Base64-encoded PDF report.",
            payload=b"%PDF-1.4\n",
            encoding="base64",
        ),
    }

    attachments = workflow_runner._build_attachment_manifest(
        "grouping_dossier",
        artifacts,
        package_mode="packaged_dossier",
    )

    manifest_payload = {
        "version": "1.0",
        "package_mode": "packaged_dossier",
        "root_entity_type": "grouping_dossier",
        "artifacts": {
            key: {
                k: v
                for k, v in artifact.items()
                if k
                not in {"fieldName", "delivery", "mediaType", "description", "source"}
                or k in {"fieldName", "mediaType", "sizeBytes", "checksumSha256"}
            }
            for key, artifact in artifacts.items()
        },
        "attachments": [
            {"name": item["name"], "role": item["role"], "mediaType": item["mediaType"]}
            for item in attachments[:-1]
        ],
    }

    manifest_entry = attachments[-1]
    assert [item["name"] for item in manifest_payload["attachments"]] == [
        "grouping-dossier-log.json",
        "grouping-dossier-summary.md",
        "grouping-dossier-report.pdf",
    ]
    assert manifest_entry["name"] == "grouping-dossier-manifest.json"
    assert manifest_entry["checksumSha256"] == hashlib.sha256(
        workflow_runner._canonical_json_bytes(manifest_payload)
    ).hexdigest()


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

    async def fake_endpoint_data(chem_id, with_meta=False, **kwargs):
        payload = {
            "Endpoint": "LC50",
            "Value": "2.5",
            "Unit": "mg/L",
            "MetaData": [
                {"Label": "Test type", "Value": "Acute toxicity"},
                {"Label": "Test organisms (species)", "Value": "Pimephales promelas"},
                {"Label": "OVERALL", "Value": "Toxic"},
            ],
        }
        meta = {"duration_ms": 7.0, "status_code": 200}
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
    monkeypatch.setattr(
        workflow_runner.qsar_client, "get_endpoint_data", fake_endpoint_data
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
    # Endpoint summaries now include both experimental and QSAR data
    endpoint_summary = hazard_summary["endpointSummaries"][0]
    assert endpoint_summary["evidenceBasis"] == "mixed"
    assert endpoint_summary["recordCount"] >= 1
    assert any(sr.get("overallResult") == "Toxic" for sr in endpoint_summary["studyRecords"])
    assert endpoint_summary["keyValues"][0]["value"] == "2.5"
    assert endpoint_summary["keyValues"][0]["unit"] == "mg/L"
    assert endpoint_summary.get("classificationRationale")
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

    async def fake_endpoint_data(chem_id, with_meta=False, **kwargs):
        payload = None
        meta = {"duration_ms": 5.0, "status_code": 200}
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
    monkeypatch.setattr(
        workflow_runner.qsar_client, "get_endpoint_data", fake_endpoint_data
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
    hazard_summary = response["portable_handoffs"]["oqtHazardEvidenceSummary.v1"]
    assert hazard_summary["endpointSummaries"][0]["evidenceBasis"] == "qsar_prediction"
    assert hazard_summary["evidenceBlocks"]["endpointData"]["status"] == "none"
    assert (
        hazard_summary["uncertaintyAssessment"]["coverage"]["endpointData"] == "none"
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


# --- Schema edge-case tests (Phase 1.1) ---

def test_build_grouping_portable_handoffs_clamps_invalid_uncertainty_levels():
    """Invalid accepted_uncertainty_level and residualUncertainty must be clamped."""
    grouping_justification = {
        "report_context": {
            "problem_formulation": "pf",
            "decision_context": "dc",
            "accepted_uncertainty_level": "invalid",
            "grouping_hypothesis": "h",
        },
        "target_substance": {
            "input_identifier": "ethanol",
            "preferred_name": "Ethanol",
            "chem_id": "abc",
        },
        "source_analogues": [],
        "uncertainty_assessment": {
            "overall_level": "banana",
            "acceptable_for_context": False,
            "what_is_not_addressed": [],
            "assessment_table": [],
        },
        "endpoint_justifications": [
            {
                "endpoint": "e1",
                "conclusion": "c",
                "confidence": "super",
                "residual_uncertainty": "unknown",
            }
        ],
        "data_matrix": [],
        "excluded_analogues": [],
        "recommended_follow_ups": [],
    }
    handoffs = workflow_runner._build_grouping_portable_handoffs(
        status="ok",
        identifier="ethanol",
        log_bundle={"inputs": {}, "errors": []},
        grouping_justification=grouping_justification,
        toolbox_meta={},
    )
    ra = handoffs["oqtReadAcrossSummary.v1"]
    assert ra["groupingMethod"]["acceptedUncertaintyLevel"] == "medium"
    assert ra["justification"]["residualUncertainty"] == "high"
    ec = ra["justification"]["endpointConclusions"][0]
    assert ec["confidence"] == "low"
    assert ec["residualUncertainty"] == "high"
    jsonschema.validate(ra, _load_schema("oqtReadAcrossSummary.v1.json"))


def test_build_grouping_portable_handoffs_review_required_status():
    """oqtWorkflowRecord must accept review_required status after schema update."""
    grouping_justification = {
        "report_context": {
            "problem_formulation": "pf",
            "decision_context": "dc",
            "accepted_uncertainty_level": "medium",
            "grouping_hypothesis": "h",
        },
        "target_substance": {
            "input_identifier": "ethanol",
            "preferred_name": "Ethanol",
            "chem_id": "abc",
        },
        "source_analogues": [],
        "uncertainty_assessment": {
            "overall_level": "high",
            "acceptable_for_context": False,
            "what_is_not_addressed": [],
            "assessment_table": [],
        },
        "endpoint_justifications": [],
        "data_matrix": [],
        "excluded_analogues": [],
        "recommended_follow_ups": [],
    }
    handoffs = workflow_runner._build_grouping_portable_handoffs(
        status="review_required",
        identifier="ethanol",
        log_bundle={"inputs": {}, "errors": []},
        grouping_justification=grouping_justification,
        toolbox_meta={},
    )
    wf = handoffs["oqtWorkflowRecord.v1"]
    assert wf["executionMetadata"]["status"] == "review_required"
    jsonschema.validate(wf, _load_schema("oqtWorkflowRecord.v1.json"))


def test_build_grouping_portable_handoffs_data_matrix_not_found_mapped():
    """dataMatrixRow.status must map 'not_found' to 'error' (not in schema enum)."""
    grouping_justification = {
        "report_context": {
            "problem_formulation": "pf",
            "decision_context": "dc",
            "accepted_uncertainty_level": "medium",
            "grouping_hypothesis": "h",
        },
        "target_substance": {
            "input_identifier": "ethanol",
            "preferred_name": "Ethanol",
            "chem_id": "abc",
        },
        "source_analogues": [],
        "uncertainty_assessment": {
            "overall_level": "high",
            "acceptable_for_context": False,
            "what_is_not_addressed": [],
            "assessment_table": [],
        },
        "endpoint_justifications": [],
        "data_matrix": [
            {
                "subject_role": "target",
                "subject_name": "Ethanol",
                "evidence_type": "identity",
                "tool": "search_chemicals",
                "status": "not_found",
                "summary": "No record",
            }
        ],
        "excluded_analogues": [],
        "recommended_follow_ups": [],
    }
    handoffs = workflow_runner._build_grouping_portable_handoffs(
        status="ok",
        identifier="ethanol",
        log_bundle={"inputs": {}, "errors": []},
        grouping_justification=grouping_justification,
        toolbox_meta={},
    )
    ra = handoffs["oqtReadAcrossSummary.v1"]
    assert ra["dataMatrix"]["rows"][0]["status"] == "error"
    jsonschema.validate(ra, _load_schema("oqtReadAcrossSummary.v1.json"))


def test_portable_uncertainty_table_clamps_enum_values():
    """Row fields must be clamped to low/medium/high."""
    assessment = {
        "accepted_level": "extreme",
        "overall_level": "unknown",
        "acceptable_for_context": True,
        "what_is_not_addressed": [],
        "assessment_table": [
            {
                "aspect": "a",
                "data_quality": "terrible",
                "strength_of_evidence": "weak",
                "uncertainty": "massive",
                "comments": "c",
            }
        ],
    }
    result = workflow_runner._build_portable_uncertainty_table(assessment, "dc", ["do more"])
    assert result["acceptedLevel"] == "medium"
    assert result["overallLevel"] == "high"
    row = result["rows"][0]
    assert row["dataQuality"] == "low"
    assert row["strengthOfEvidence"] == "low"
    assert row["uncertainty"] == "high"
    # Validate via a minimal oqtReadAcrossSummary wrapper so $refs resolve
    stub = {
        "schemaName": "oqtReadAcrossSummary",
        "schemaVersion": "v1",
        "module": "oqt-mcp",
        "chemicalIdentity": {"inputIdentifier": "x", "preferredName": "X", "chemId": "c"},
        "groupingMethod": {"type": "t", "problemFormulation": "p", "decisionContext": "d", "acceptedUncertaintyLevel": "medium"},
        "analogues": [],
        "assessmentBoundary": {"scope": "s", "includes": [], "excludes": []},
        "decisionBoundary": {"supportedDecisions": [], "prohibitedDecisions": [], "reviewRequired": False},
        "decisionOwner": "O-QT",
        "supports": {"typedGroupingDossier": True, "typedApplicabilityDomain": True, "typedUncertaintyTable": True, "finalReadAcrossAcceptance": False, "finalDecisionRecommendation": False},
        "requiredExternalInputs": [],
        "applicabilityDomain": {"inclusionCriteria": [], "exclusionCriteria": [], "allowedDifferences": [], "boundaryNotes": [], "supportingSimilarityContexts": [], "subcategoryNotes": []},
        "dataMatrix": {"rowCount": 0, "rows": []},
        "uncertaintyTable": result,
        "supportingProfiler": [],
        "justification": {"hypothesis": "h", "summary": "s", "residualUncertainty": "high", "acceptableForContext": False, "endpointConclusions": []},
        "provenance": {"recordId": "r1", "sourceSystem": "S", "generatedBy": "test", "generatedAt": "2026-01-01T00:00:00Z"},
        "limitations": [],
    }
    jsonschema.validate(stub, _load_schema("oqtReadAcrossSummary.v1.json"))


# --- Phase 1.2: Workflow record edge-case tests ---

def test_build_workflow_portable_handoffs_review_required_status():
    """oqtWorkflowRecord must accept review_required status."""
    log_bundle = {
        "inputs": {"identifier": "Benzene", "search_type": "name"},
        "selected_chemical": {
            "ChemId": "chem-1",
            "Names": ["Benzene"],
        },
        "errors": [],
    }
    handoffs = workflow_runner._build_workflow_portable_handoffs(
        status="review_required",
        log_bundle=log_bundle,
        toolbox_meta={},
    )
    wf = handoffs["oqtWorkflowRecord.v1"]
    assert wf["executionMetadata"]["status"] == "review_required"
    jsonschema.validate(wf, _load_schema("oqtWorkflowRecord.v1.json"))


def test_build_workflow_portable_handoffs_not_found_status():
    """oqtWorkflowRecord must accept not_found status when chemical missing."""
    log_bundle = {
        "inputs": {"identifier": "unknown_xyz", "search_type": "name"},
        "errors": ["No Toolbox records found"],
    }
    toolbox_meta = {
        "calls": [
            {
                "endpoint": "workflow/search",
                "api_versions": "6.0",
                "server_date": "Mon, 16 Apr 2026 10:00:00 GMT",
            }
        ]
    }
    handoffs = workflow_runner._build_workflow_portable_handoffs(
        status="not_found",
        log_bundle=log_bundle,
        toolbox_meta=toolbox_meta,
    )
    wf = handoffs["oqtWorkflowRecord.v1"]
    assert wf["executionMetadata"]["status"] == "not_found"
    assert wf["executionMetadata"]["errors"] == ["No Toolbox records found"]
    assert wf["reproducibility"]["upstreamVersions"]["apiVersions"] == "6.0"
    assert (
        wf["reproducibility"]["upstreamVersions"]["serverDate"]
        == "Mon, 16 Apr 2026 10:00:00 GMT"
    )
    jsonschema.validate(wf, _load_schema("oqtWorkflowRecord.v1.json"))


def test_build_workflow_portable_handoffs_hazard_with_qsar_dict_predicted_value():
    """Hazard handoff must survive a QSAR result with a dict predictedValue."""
    log_bundle = {
        "inputs": {
            "identifier": "Benzene",
            "search_type": "name",
            "profiler_guids": ["p1"],
            "simulator_guids": ["s1"],
            "qsar_guids": ["q1"],
        },
        "selected_chemical": {
            "ChemId": "chem-1",
            "Names": ["Benzene"],
        },
        "profiler_results": [
            {"profiler_guid": "p1", "subject_role": "target", "result": {"class": "A"}, "profiler_provenance": {"title": "P"}}
        ],
        "simulator_results": [
            {"simulator_guid": "s1", "subject_role": "target", "result": [{"name": "M1"}], "simulator_provenance": {"title": "S"}}
        ],
        "qsar_results": [
            {
                "qsar_guid": "q1",
                "prediction": {"Value": {"complex": 123}, "Endpoint": "LC50"},
                "domain": {"DomainResult": "InDomain"},
                "model_provenance": {"title": "Q"},
            }
        ],
        "errors": [],
    }
    handoffs = workflow_runner._build_workflow_portable_handoffs(
        status="ok",
        log_bundle=log_bundle,
        toolbox_meta={},
    )
    haz = handoffs["oqtHazardEvidenceSummary.v1"]
    qsar = haz["qsarFindings"][0]
    assert "predictedValue" not in qsar
    jsonschema.validate(haz, _load_schema("oqtHazardEvidenceSummary.v1.json"))
