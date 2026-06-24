import base64
import io
import json
import zipfile

import pytest

from src.tools.implementations.export_adapters import (
    export_grouping_bundle,
    export_hazard_summary,
)


@pytest.fixture
def sample_grouping_response():
    return {
        "status": "ok",
        "identifier": "acetone",
        "summary_markdown": "# Grouping Justification\n\nAcetone is grouped with similar ketones.",
        "grouping_justification": {"chemicalIdentity": {"preferredName": "Acetone"}},
        "log_json": {"steps": [{"tool": "search", "status": "ok"}]},
        "pdf_report_base64": base64.b64encode(b"%PDF-1.4 fake pdf content").decode("utf-8"),
        "portable_handoffs": {
            "oqtWorkflowRecord.v1": {"workflowId": "wf-123"},
            "oqtReadAcrossSummary.v1": {
                "schemaName": "oqtReadAcrossSummary",
                "schemaVersion": "v1",
                "chemicalIdentity": {"preferredName": "Acetone"},
            },
        },
    }


@pytest.fixture
def sample_hazard_response():
    return {
        "chemical_identifier": "acetone",
        "endpoint": "toxicity",
        "portable_handoffs": {
            "oqtHazardEvidenceSummary.v1": {
                "schemaName": "oqtHazardEvidenceSummary",
                "schemaVersion": "v1",
                "chemicalIdentity": {"preferredName": "Acetone"},
            }
        },
    }


@pytest.mark.asyncio
async def test_export_grouping_bundle_returns_expected_keys(sample_grouping_response):
    result = await export_grouping_bundle(sample_grouping_response, filename="acetone_grouping")
    assert "zip_base64" in result
    assert result["filename"] == "acetone_grouping.zip"
    assert result["size_bytes"] > 0
    assert "manifest" in result
    assert "files" in result["manifest"]


@pytest.mark.asyncio
async def test_export_grouping_bundle_zip_contents(sample_grouping_response):
    result = await export_grouping_bundle(sample_grouping_response)
    zip_bytes = base64.b64decode(result["zip_base64"])
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        assert "readAcrossSummary.json" in names
        assert "log.json" in names
        assert "summary.md" in names
        assert "report.pdf" in names
        assert "manifest.json" in names

        # Validate manifest content
        manifest_data = json.loads(zf.read("manifest.json"))
        assert "files" in manifest_data
        file_names = {entry["fileName"] for entry in manifest_data["files"]}
        assert "readAcrossSummary.json" in file_names
        assert "report.pdf" in file_names

        # Validate every manifest entry has required fields
        for entry in manifest_data["files"]:
            assert "fileName" in entry
            assert "mediaType" in entry
            assert "sizeBytes" in entry
            assert "checksumSha256" in entry
            assert isinstance(entry["sizeBytes"], int)
            assert len(entry["checksumSha256"]) == 64


@pytest.mark.asyncio
async def test_export_grouping_bundle_omits_pdf_when_include_pdf_false(sample_grouping_response):
    result = await export_grouping_bundle(sample_grouping_response, include_pdf=False)
    zip_bytes = base64.b64decode(result["zip_base64"])
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        assert "report.pdf" not in names
        manifest_data = json.loads(zf.read("manifest.json"))
        file_names = {entry["fileName"] for entry in manifest_data["files"]}
        assert "report.pdf" not in file_names


@pytest.mark.asyncio
async def test_export_grouping_bundle_omits_pdf_when_missing():
    response = {
        "status": "ok",
        "identifier": "acetone",
        "summary_markdown": "# Summary",
        "portable_handoffs": {
            "oqtReadAcrossSummary.v1": {"schemaName": "oqtReadAcrossSummary", "schemaVersion": "v1"},
        },
    }
    result = await export_grouping_bundle(response)
    zip_bytes = base64.b64decode(result["zip_base64"])
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        assert "report.pdf" not in names


@pytest.mark.asyncio
async def test_export_hazard_summary_returns_expected_keys(sample_hazard_response):
    result = await export_hazard_summary(sample_hazard_response, filename="acetone_hazard")
    assert "zip_base64" in result
    assert result["filename"] == "acetone_hazard.zip"
    assert result["size_bytes"] > 0
    assert "manifest" in result


@pytest.mark.asyncio
async def test_export_hazard_summary_zip_contents(sample_hazard_response):
    result = await export_hazard_summary(sample_hazard_response)
    zip_bytes = base64.b64decode(result["zip_base64"])
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        assert "hazardEvidenceSummary.json" in names
        assert "manifest.json" in names
        assert "log.json" not in names  # not present in sample_hazard_response
        assert "summary.md" not in names  # not present in sample_hazard_response

        # Validate manifest
        manifest_data = json.loads(zf.read("manifest.json"))
        file_names = {entry["fileName"] for entry in manifest_data["files"]}
        assert "hazardEvidenceSummary.json" in file_names

        for entry in manifest_data["files"]:
            assert "fileName" in entry
            assert "mediaType" in entry
            assert "sizeBytes" in entry
            assert "checksumSha256" in entry


@pytest.mark.asyncio
async def test_export_hazard_summary_with_log_and_pdf():
    response = {
        "chemical_identifier": "acetone",
        "endpoint": "toxicity",
        "log_json": {"steps": ["step1"]},
        "summary_markdown": "# Hazard Summary",
        "pdf_report_base64": base64.b64encode(b"%PDF-1.4 fake").decode("utf-8"),
        "portable_handoffs": {
            "oqtHazardEvidenceSummary.v1": {
                "schemaName": "oqtHazardEvidenceSummary",
                "schemaVersion": "v1",
            }
        },
    }
    result = await export_hazard_summary(response)
    zip_bytes = base64.b64decode(result["zip_base64"])
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        assert "hazardEvidenceSummary.json" in names
        assert "log.json" in names
        assert "summary.md" in names
        assert "report.pdf" in names
        assert "manifest.json" in names
