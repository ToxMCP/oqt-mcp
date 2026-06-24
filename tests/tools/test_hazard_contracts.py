"""Schema-validation tests for hazard contract builders."""

import json
from pathlib import Path

import jsonschema

from src.tools import hazard_contracts as hc
from src.tools.implementations import workflow_runner

ROOT = Path(__file__).resolve().parents[2]


def _load_schema(name: str) -> dict:
    path = ROOT / "schemas" / name
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_build_qsar_findings_skips_non_scalar_predicted_value():
    """predictedValue must be number|string|null; dicts/lists are stripped."""
    results = [
        {
            "qsar_guid": "q1",
            "prediction": {"Value": {"nested": 1}, "Endpoint": "LC50", "Unit": "mg/L"},
            "domain": {"DomainResult": "InDomain"},
        },
        {
            "qsar_guid": "q2",
            "prediction": {"Value": [1, 2], "Endpoint": "LC50"},
            "domain": {"DomainResult": "OutOfDomain"},
        },
        {
            "qsar_guid": "q3",
            "prediction": {"Value": "1.23", "Endpoint": "LC50"},
            "domain": {"DomainResult": "InDomain"},
        },
    ]
    findings = workflow_runner._build_qsar_findings(["q1", "q2", "q3"], results, [])
    assert "predictedValue" not in findings[0]
    assert "predictedValue" not in findings[1]
    assert findings[2]["predictedValue"] == "1.23"
    for f in findings:
        jsonschema.validate(f, _load_schema("oqtHazardEvidenceSummary.v1.json")["$defs"]["qsarFinding"])


def test_build_hazard_applicability_domain_empty_qsar():
    result = hc.build_hazard_applicability_domain([])
    assert result["overallStatus"] == "not_applicable"
    assert result["modelAssessments"] == []
    jsonschema.validate(result, _load_schema("oqtHazardEvidenceSummary.v1.json")["$defs"]["applicabilityDomain"])


def test_build_hazard_evidence_blocks_empty_inputs():
    result = hc.build_hazard_evidence_blocks()
    assert result["endpointData"]["status"] == "none"
    assert result["profiling"]["status"] == "none"
    assert result["metabolism"]["status"] == "none"
    assert result["qsar"]["status"] == "none"
    # Validate via minimal wrapper so $refs resolve
    stub = {
        "schemaName": "oqtHazardEvidenceSummary",
        "schemaVersion": "v1",
        "module": "oqt-mcp",
        "chemicalIdentity": {"inputIdentifier": "x", "preferredName": "X", "chemId": "c"},
        "profilers": [],
        "metabolismFindings": [],
        "qsarFindings": [],
        "endpointSummaries": [],
        "evidenceBlocks": result,
        "requestMetadata": {
            "requestedAt": "2026-01-01T00:00:00Z",
            "requestedEndpoints": [],
            "requestedProfilers": [],
            "requestedSimulators": [],
            "requestedQsarModels": [],
            "summaryOnly": True,
        },
        "assessmentBoundary": {"scope": "s", "includes": [], "excludes": []},
        "decisionBoundary": {"supportedDecisions": [], "prohibitedDecisions": [], "reviewRequired": False},
        "decisionOwner": "O-QT",
        "supports": {"typedStudyEvidence": False, "typedProfilerEvidence": False, "typedApplicabilityDomainReview": False, "crossModuleSynthesis": False, "finalDecisionRecommendation": False},
        "requiredExternalInputs": [],
        "uncertaintyAssessment": {
            "method": "m",
            "supportsQuantitativeMetrics": False,
            "overallLevel": "low",
            "coverage": {"endpointData": "none", "profiling": "none", "metabolism": "none", "qsar": "none"},
            "semanticCoverage": {
                "overallQuantificationStatus": "qualitative_only",
                "probabilisticConfidenceStatus": "not_supported",
                "typedStudyRecordStatus": "none",
                "typedApplicabilityDomainStatus": "not_applicable",
                "qualitativeComponents": [],
                "quantifiedComponents": [],
            },
            "dataGaps": [],
            "confidenceDrivers": [],
            "notes": [],
        },
        "applicabilityDomain": {"overallStatus": "not_applicable", "supportsQuantitativeConfidence": False, "confidenceLevel": "low", "modelAssessments": [], "notes": []},
        "applicabilityNotes": [],
        "provenance": {"workflowId": "w1", "sourceSystem": "S", "generatedBy": "test", "generatedAt": "2026-01-01T00:00:00Z"},
        "limitations": [],
    }
    jsonschema.validate(stub, _load_schema("oqtHazardEvidenceSummary.v1.json"))


def test_build_hazard_uncertainty_assessment_schema_compliance():
    result = hc.build_hazard_uncertainty_assessment(
        endpoint_record_count=0,
        endpoint_requested=True,
        profiling_record_count=2,
        profiling_requested_total=2,
        metabolism_record_count=1,
        metabolism_requested_total=2,
        qsar_record_count=0,
        qsar_requested_total=1,
    )
    assert result["overallLevel"] == "medium"
    stub = {
        "schemaName": "oqtHazardEvidenceSummary",
        "schemaVersion": "v1",
        "module": "oqt-mcp",
        "chemicalIdentity": {"inputIdentifier": "x", "preferredName": "X", "chemId": "c"},
        "profilers": [],
        "metabolismFindings": [],
        "qsarFindings": [],
        "endpointSummaries": [],
        "evidenceBlocks": {
            "endpointData": {"summary": None, "status": "none", "basis": "b", "keyEvidence": [], "references": [], "provenanceRecords": []},
            "profiling": {"summary": None, "status": "none", "basis": "b", "keyEvidence": [], "references": [], "provenanceRecords": []},
            "metabolism": {"summary": None, "status": "none", "basis": "b", "keyEvidence": [], "references": [], "provenanceRecords": []},
            "qsar": {"summary": None, "status": "none", "basis": "b", "keyEvidence": [], "references": [], "provenanceRecords": []},
        },
        "requestMetadata": {
            "requestedAt": "2026-01-01T00:00:00Z",
            "requestedEndpoints": [],
            "requestedProfilers": [],
            "requestedSimulators": [],
            "requestedQsarModels": [],
            "summaryOnly": True,
        },
        "assessmentBoundary": {"scope": "s", "includes": [], "excludes": []},
        "decisionBoundary": {"supportedDecisions": [], "prohibitedDecisions": [], "reviewRequired": False},
        "decisionOwner": "O-QT",
        "supports": {"typedStudyEvidence": False, "typedProfilerEvidence": False, "typedApplicabilityDomainReview": False, "crossModuleSynthesis": False, "finalDecisionRecommendation": False},
        "requiredExternalInputs": [],
        "uncertaintyAssessment": {
            **result,
            "semanticCoverage": {
                "overallQuantificationStatus": "qualitative_only",
                "probabilisticConfidenceStatus": "not_supported",
                "typedStudyRecordStatus": "none",
                "typedApplicabilityDomainStatus": "not_applicable",
                "qualitativeComponents": [],
                "quantifiedComponents": [],
            },
        },
        "applicabilityDomain": {"overallStatus": "not_applicable", "supportsQuantitativeConfidence": False, "confidenceLevel": "low", "modelAssessments": [], "notes": []},
        "applicabilityNotes": [],
        "provenance": {"workflowId": "w1", "sourceSystem": "S", "generatedBy": "test", "generatedAt": "2026-01-01T00:00:00Z"},
        "limitations": [],
    }
    jsonschema.validate(stub, _load_schema("oqtHazardEvidenceSummary.v1.json"))


def test_build_hazard_supports_and_boundary_schema_compliance():
    supports = hc.build_hazard_supports()
    jsonschema.validate(supports, _load_schema("oqtHazardEvidenceSummary.v1.json")["$defs"]["supports"])

    boundary = hc.build_hazard_decision_boundary()
    jsonschema.validate(boundary, _load_schema("oqtHazardEvidenceSummary.v1.json")["$defs"]["decisionBoundary"])

    assessment = hc.build_hazard_assessment_boundary()
    jsonschema.validate(assessment, _load_schema("oqtHazardEvidenceSummary.v1.json")["$defs"]["assessmentBoundary"])


def test_build_endpoint_summaries_from_qsar_results_schema_compliance():
    results = [
        {
            "qsar_guid": "q1",
            "prediction": {"Value": "0.77", "Unit": "mg/L", "Endpoint": "LC50"},
            "domain": "InDomain",
        }
    ]
    summaries = hc.build_endpoint_summaries_from_qsar_results(results)
    assert len(summaries) == 1
    jsonschema.validate(summaries[0], _load_schema("oqtHazardEvidenceSummary.v1.json")["$defs"]["endpointSummary"])


def test_build_endpoint_summaries_from_payload_schema_compliance():
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
    summaries = hc.build_endpoint_summaries_from_payload(payload)
    assert len(summaries) == 1
    summary = summaries[0]
    assert summary["recordCount"] == 1
    assert summary["keyValues"][0]["value"] == "2.5"
    assert summary["keyValues"][0]["unit"] == "mg/L"
    assert summary.get("classificationRationale")
    # Validate via minimal wrapper against full hazard schema so $refs resolve
    stub = {
        "schemaName": "oqtHazardEvidenceSummary",
        "schemaVersion": "v1",
        "module": "oqt-mcp",
        "chemicalIdentity": {"inputIdentifier": "x", "preferredName": "X", "chemId": "c"},
        "profilers": [],
        "metabolismFindings": [],
        "qsarFindings": [],
        "endpointSummaries": [summary],
        "evidenceBlocks": {
            "endpointData": {"summary": None, "status": "present", "basis": "b", "keyEvidence": [], "references": [], "provenanceRecords": []},
            "profiling": {"summary": None, "status": "none", "basis": "b", "keyEvidence": [], "references": [], "provenanceRecords": []},
            "metabolism": {"summary": None, "status": "none", "basis": "b", "keyEvidence": [], "references": [], "provenanceRecords": []},
            "qsar": {"summary": None, "status": "none", "basis": "b", "keyEvidence": [], "references": [], "provenanceRecords": []},
        },
        "requestMetadata": {
            "requestedAt": "2026-01-01T00:00:00Z",
            "requestedEndpoints": [],
            "requestedProfilers": [],
            "requestedSimulators": [],
            "requestedQsarModels": [],
            "summaryOnly": True,
        },
        "assessmentBoundary": {"scope": "s", "includes": [], "excludes": []},
        "decisionBoundary": {"supportedDecisions": [], "prohibitedDecisions": [], "reviewRequired": False},
        "decisionOwner": "O-QT",
        "supports": {"typedStudyEvidence": True, "typedProfilerEvidence": False, "typedApplicabilityDomainReview": False, "crossModuleSynthesis": False, "finalDecisionRecommendation": False},
        "requiredExternalInputs": [],
        "uncertaintyAssessment": {
            "method": "m",
            "supportsQuantitativeMetrics": False,
            "overallLevel": "low",
            "coverage": {"endpointData": "present", "profiling": "none", "metabolism": "none", "qsar": "none"},
            "semanticCoverage": {
                "overallQuantificationStatus": "qualitative_only",
                "probabilisticConfidenceStatus": "not_supported",
                "typedStudyRecordStatus": "present",
                "typedApplicabilityDomainStatus": "not_applicable",
                "qualitativeComponents": [],
                "quantifiedComponents": [],
            },
            "dataGaps": [],
            "confidenceDrivers": [],
            "notes": [],
        },
        "applicabilityDomain": {"overallStatus": "not_applicable", "supportsQuantitativeConfidence": False, "confidenceLevel": "low", "modelAssessments": [], "notes": []},
        "applicabilityNotes": [],
        "provenance": {"workflowId": "w1", "sourceSystem": "S", "generatedBy": "test", "generatedAt": "2026-01-01T00:00:00Z"},
        "limitations": [],
    }
    jsonschema.validate(stub, _load_schema("oqtHazardEvidenceSummary.v1.json"))
    # Wrap with envelope fields to validate against the standalone endpoint summary schema
    standalone_summary = {
        "schemaName": "oqtEndpointSummary",
        "schemaVersion": "v1",
        "module": "oqt-mcp",
        **summary,
    }
    jsonschema.validate(standalone_summary, _load_schema("oqtEndpointSummary.v1.json"))


def test_build_request_metadata_schema_compliance():
    meta = hc.build_request_metadata(
        requested_at="2026-01-01T00:00:00Z",
        requested_endpoints=["LC50"],
        requested_profilers=["p1"],
        requested_simulators=[],
        requested_qsar_models=["q1"],
        summary_only=False,
    )
    jsonschema.validate(meta, _load_schema("oqtHazardEvidenceSummary.v1.json")["$defs"]["requestMetadata"])
