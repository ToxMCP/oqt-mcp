#!/usr/bin/env python3
"""Generate example exported bundles for documentation and regression testing."""

import asyncio
import base64
import json
import pathlib
import sys

# Ensure the repo root is on PYTHONPATH
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.tools.implementations.export_adapters import (
    export_grouping_bundle,
    export_hazard_summary,
)


PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\nxref\n0 3\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \ntrailer\n<< /Size 3 /Root 1 0 R >>\nstartxref\n105\n%%EOF"


def _grouping_response():
    return {
        "status": "ok",
        "identifier": "acetone",
        "summary_markdown": (
            "# Grouping Justification: Acetone\n\n"
            "Acetone is grouped with structurally similar ketones based on "
            "identical functional groups and comparable physicochemical properties."
        ),
        "grouping_justification": {
            "chemicalIdentity": {"preferredName": "Acetone", "cas": "67-64-1"},
            "analogues": [{"preferredName": "Methyl ethyl ketone"}],
        },
        "log_json": {
            "identifier": "acetone",
            "steps": [
                {"tool": "search_chemicals", "status": "ok"},
                {"tool": "build_grouping_justification", "status": "ok"},
            ],
        },
        "pdf_report_base64": base64.b64encode(PDF_BYTES).decode("utf-8"),
        "portable_handoffs": {
            "oqtWorkflowRecord.v1": {
                "schemaName": "oqtWorkflowRecord",
                "schemaVersion": "v1",
                "workflowId": "wf-acetone-001",
            },
            "oqtReadAcrossSummary.v1": {
                "schemaName": "oqtReadAcrossSummary",
                "schemaVersion": "v1",
                "module": "oqt-mcp",
                "chemicalIdentity": {
                    "inputIdentifier": "acetone",
                    "preferredName": "Acetone",
                    "cas": "67-64-1",
                },
                "groupingMethod": "read_across",
                "analogues": [
                    {"preferredName": "Methyl ethyl ketone", "similarityBasis": "structural"}
                ],
                "dataMatrix": {"rows": []},
                "uncertaintyTable": {"aspects": []},
                "justification": {
                    "hypothesis": "Ketones share metabolic pathways.",
                    "summary": "Read-across is justified.",
                },
                "provenance": {
                    "sourceSystem": "QSAR Toolbox",
                    "generatedBy": "o-qt-mcp-server",
                    "generatedAt": "2026-04-16T10:00:00Z",
                },
            },
        },
    }


def _hazard_response():
    return {
        "chemical_identifier": "acetaminophen",
        "endpoint": "hepatotoxicity",
        "portable_handoffs": {
            "oqtHazardEvidenceSummary.v1": {
                "schemaName": "oqtHazardEvidenceSummary",
                "schemaVersion": "v1",
                "module": "oqt-mcp",
                "chemicalIdentity": {
                    "inputIdentifier": "acetaminophen",
                    "preferredName": "Acetaminophen",
                    "cas": "103-90-2",
                },
                "profilers": [],
                "metabolismFindings": [],
                "qsarFindings": [],
                "endpointSummaries": [],
                "evidenceBlocks": {
                    "endpointData": {"status": "present", "basis": "Toolbox experimental data retrieved."},
                    "profiling": {"status": "none", "basis": "No profiling requested."},
                    "metabolism": {"status": "none", "basis": "No metabolism simulation requested."},
                    "qsar": {"status": "none", "basis": "No QSAR models requested."},
                },
                "uncertaintyAssessment": {
                    "overallConfidence": "medium",
                    "dataQuality": "medium",
                    "comments": "Direct experimental data available; no metabolism or QSAR evidence.",
                },
                "applicabilityDomain": {"status": "within_domain"},
                "provenance": {
                    "sourceSystem": "QSAR Toolbox",
                    "generatedBy": "o-qt-mcp-server",
                    "generatedAt": "2026-04-16T10:00:00Z",
                },
            }
        },
        "log_json": {
            "identifier": "acetaminophen",
            "steps": [
                {"tool": "search_chemicals", "status": "ok"},
                {"tool": "analyze_chemical_hazard", "status": "ok"},
            ],
        },
        "summary_markdown": (
            "# Hazard Summary: Acetaminophen\n\n"
            "Acetaminophen shows hepatotoxicity signals at high doses. "
            "Experimental data supports a medium-confidence assessment."
        ),
        "pdf_report_base64": base64.b64encode(PDF_BYTES).decode("utf-8"),
    }


async def main():
    out_dir = pathlib.Path(__file__).resolve().parent.parent / "examples" / "exported_bundles"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Grouping bundle
    grouping_result = await export_grouping_bundle(_grouping_response(), filename="grouping_bundle_example")
    grouping_zip_path = out_dir / grouping_result["filename"]
    grouping_zip_path.write_bytes(base64.b64decode(grouping_result["zip_base64"]))
    grouping_manifest_path = out_dir / "grouping_bundle_manifest.json"
    grouping_manifest_path.write_text(json.dumps(grouping_result["manifest"], indent=2))
    print(f"Wrote {grouping_zip_path}")
    print(f"Wrote {grouping_manifest_path}")

    # Hazard summary
    hazard_result = await export_hazard_summary(_hazard_response(), filename="hazard_summary_example")
    hazard_zip_path = out_dir / hazard_result["filename"]
    hazard_zip_path.write_bytes(base64.b64decode(hazard_result["zip_base64"]))
    hazard_manifest_path = out_dir / "hazard_summary_manifest.json"
    hazard_manifest_path.write_text(json.dumps(hazard_result["manifest"], indent=2))
    print(f"Wrote {hazard_zip_path}")
    print(f"Wrote {hazard_manifest_path}")


if __name__ == "__main__":
    asyncio.run(main())
