import base64
import hashlib
import io
import json
import zipfile
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from src.tools.registry import tool_registry


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _build_manifest_entry(file_name: str, media_type: str, data: bytes) -> Dict[str, Any]:
    return {
        "fileName": file_name,
        "mediaType": media_type,
        "sizeBytes": len(data),
        "checksumSha256": _sha256_bytes(data),
    }


def _extract_pdf_bytes(response: Dict[str, Any]) -> Optional[bytes]:
    b64 = response.get("pdf_report_base64") or response.get("pdf_base64")
    if b64 and isinstance(b64, str):
        try:
            return base64.b64decode(b64)
        except Exception:
            return None
    return None


def _assemble_zip(
    *,
    summary_json: Dict[str, Any],
    summary_file_name: str,
    log_json: Optional[Dict[str, Any]] = None,
    markdown_summary: Optional[str] = None,
    pdf_bytes: Optional[bytes] = None,
    include_pdf: bool = True,
) -> Dict[str, Any]:
    """Assemble a ZIP archive with manifest from export components."""
    buffer = io.BytesIO()
    manifest: List[Dict[str, Any]] = []

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Summary JSON
        summary_data = json.dumps(summary_json, indent=2, ensure_ascii=False).encode("utf-8")
        zf.writestr(summary_file_name, summary_data)
        manifest.append(_build_manifest_entry(summary_file_name, "application/json", summary_data))

        # 2. Log JSON
        if log_json is not None:
            log_data = json.dumps(log_json, indent=2, ensure_ascii=False).encode("utf-8")
            zf.writestr("log.json", log_data)
            manifest.append(_build_manifest_entry("log.json", "application/json", log_data))

        # 3. Markdown summary
        if markdown_summary:
            md_data = markdown_summary.encode("utf-8")
            zf.writestr("summary.md", md_data)
            manifest.append(_build_manifest_entry("summary.md", "text/markdown", md_data))

        # 4. PDF report
        if pdf_bytes is not None and include_pdf:
            zf.writestr("report.pdf", pdf_bytes)
            manifest.append(_build_manifest_entry("report.pdf", "application/pdf", pdf_bytes))

        # 5. Manifest JSON
        manifest_data = json.dumps({"files": manifest}, indent=2, ensure_ascii=False).encode("utf-8")
        zf.writestr("manifest.json", manifest_data)

    zip_bytes = buffer.getvalue()
    return {
        "zip_base64": base64.b64encode(zip_bytes).decode("utf-8"),
        "size_bytes": len(zip_bytes),
        "filename": "bundle.zip",
        "manifest": {"files": manifest},
    }


class ExportGroupingBundleParams(BaseModel):
    grouping_response: Dict[str, Any] = Field(
        ...,
        description="Full response dict from build_grouping_justification (contains grouping_justification, log_json, pdf_report_base64, summary_markdown, portable_handoffs).",
    )
    filename: str = Field(
        "grouping_bundle",
        description="Base filename for the output ZIP (without extension).",
    )
    include_pdf: bool = Field(
        True,
        description="Whether to embed the PDF report if present.",
    )


async def export_grouping_bundle(
    grouping_response: Dict[str, Any],
    filename: str = "grouping_bundle",
    include_pdf: bool = True,
) -> Dict[str, Any]:
    portable = grouping_response.get("portable_handoffs") or {}
    summary_json = portable.get("oqtReadAcrossSummary.v1") or grouping_response.get("grouping_justification") or {}

    result = _assemble_zip(
        summary_json=summary_json,
        summary_file_name="readAcrossSummary.json",
        log_json=grouping_response.get("log_json"),
        markdown_summary=grouping_response.get("summary_markdown"),
        pdf_bytes=_extract_pdf_bytes(grouping_response),
        include_pdf=include_pdf,
    )
    result["filename"] = f"{filename}.zip"
    return result


class ExportHazardSummaryParams(BaseModel):
    hazard_response: Dict[str, Any] = Field(
        ...,
        description="Full response dict from analyze_chemical_hazard or run_oqt_multiagent_workflow (contains portable_handoffs with oqtHazardEvidenceSummary.v1).",
    )
    filename: str = Field(
        "hazard_summary",
        description="Base filename for the output ZIP (without extension).",
    )
    include_pdf: bool = Field(
        True,
        description="Whether to embed the PDF report if present.",
    )


async def export_hazard_summary(
    hazard_response: Dict[str, Any],
    filename: str = "hazard_summary",
    include_pdf: bool = True,
) -> Dict[str, Any]:
    portable = hazard_response.get("portable_handoffs") or {}
    summary_json = portable.get("oqtHazardEvidenceSummary.v1") or {}

    result = _assemble_zip(
        summary_json=summary_json,
        summary_file_name="hazardEvidenceSummary.json",
        log_json=hazard_response.get("log_json"),
        markdown_summary=hazard_response.get("summary_markdown"),
        pdf_bytes=_extract_pdf_bytes(hazard_response),
        include_pdf=include_pdf,
    )
    result["filename"] = f"{filename}.zip"
    return result


def register_export_tools() -> None:
    tool_registry.register(
        name="export_grouping_bundle",
        description="Exports a grouping justification response into a structured ZIP archive containing readAcrossSummary.json, log.json, summary.md, report.pdf, and manifest.json.",
        parameters_model=ExportGroupingBundleParams,
        implementation=export_grouping_bundle,
    )
    tool_registry.register(
        name="export_hazard_summary",
        description="Exports a hazard analysis response into a structured ZIP archive containing hazardEvidenceSummary.json, log.json, summary.md, report.pdf, and manifest.json.",
        parameters_model=ExportHazardSummaryParams,
        implementation=export_hazard_summary,
    )


register_export_tools()
