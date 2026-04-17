#!/usr/bin/env python3
"""Generate committed example agency dossiers by calling the live MCP server."""

import base64
import io
import json
import pathlib
import sys
import zipfile

import httpx

BASE_URL = "http://127.0.0.1:8001"
OUT_DIR = pathlib.Path(__file__).resolve().parent.parent / "examples" / "agency_dossiers"


def mcp_call(name: str, arguments: dict) -> dict:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }
    resp = httpx.post(f"{BASE_URL}/mcp", json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"MCP error: {data['error']}")
    content = data["result"]["content"][0]["text"]
    return json.loads(content)


def write_zip_to_dir(zip_b64: str, directory: pathlib.Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    zip_bytes = base64.b64decode(zip_b64)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for member in zf.namelist():
            data = zf.read(member)
            dest = directory / member
            if member.endswith(".json"):
                try:
                    parsed = json.loads(data.decode("utf-8"))
                    dest.write_text(
                        json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8"
                    )
                except Exception:
                    dest.write_bytes(data)
            else:
                dest.write_bytes(data)
    print(f"  Wrote {directory}")


def generate_acetone_hazard() -> None:
    print(">>> Generating acetone hazard dossier...")
    result = mcp_call(
        "run_oqt_multiagent_workflow",
        {
            "identifier": "67-64-1",
            "search_type": "cas",
            "context": None,
            "profiler_guids": [],
            "qsar_mode": "none",
            "qsar_guids": [],
            "simulator_guids": [],
            "llm_provider": None,
            "llm_model": None,
            "llm_api_key": None,
            "require_human_review": False,
        },
    )
    export = mcp_call(
        "export_hazard_summary",
        {"hazard_response": result, "filename": "acetone_hazard", "include_pdf": True},
    )
    write_zip_to_dir(export["zip_base64"], OUT_DIR / "acetone_hazard")


def generate_acetone_grouping() -> None:
    print(">>> Generating acetone grouping dossier...")
    result = mcp_call(
        "build_grouping_justification",
        {
            "identifier": "67-64-1",
            "search_type": "cas",
            "problem_formulation": "Assess structural grouping for ketone read-across.",
            "decision_context": "hazard_identification",
            "endpoints": ["Acute toxicity"],
            "route_of_exposure": None,
            "grouping_hypothesis": "Ketones share metabolic pathways and similar toxicological profiles.",
            "analogue_identifiers": ["78-93-3"],
            "analogue_search_type": "cas",
            "profiler_guids": [],
            "simulator_guids": [],
            "qsar_guids": [],
            "accepted_uncertainty_level": "medium",
            "context": None,
            "package_mode": "packaged_dossier",
        },
    )
    export = mcp_call(
        "export_grouping_bundle",
        {
            "grouping_response": result,
            "filename": "acetone_grouping",
            "include_pdf": True,
        },
    )
    write_zip_to_dir(export["zip_base64"], OUT_DIR / "acetone_grouping")


def generate_benzene_ad_gated() -> None:
    print(">>> Generating benzene AD-gated hazard dossier...")
    # Use run_oqt_multiagent_workflow with QSAR mode to get AD gating behavior
    result = mcp_call(
        "run_oqt_multiagent_workflow",
        {
            "identifier": "71-43-2",
            "search_type": "cas",
            "context": None,
            "profiler_guids": [],
            "qsar_mode": "recommended",
            "qsar_guids": [],
            "simulator_guids": [],
            "llm_provider": None,
            "llm_model": None,
            "llm_api_key": None,
            "require_human_review": False,
        },
    )
    export = mcp_call(
        "export_hazard_summary",
        {"hazard_response": result, "filename": "benzene_ad_gated", "include_pdf": True},
    )
    write_zip_to_dir(export["zip_base64"], OUT_DIR / "benzene_ad_gated")


def main():
    try:
        health = httpx.get(f"{BASE_URL}/health", timeout=10).json()
        if health.get("status") != "healthy":
            raise RuntimeError(f"Server unhealthy: {health}")
    except Exception as exc:
        print(f"ERROR: Cannot reach MCP server at {BASE_URL}: {exc}")
        sys.exit(1)

    generate_acetone_hazard()
    generate_acetone_grouping()
    generate_benzene_ad_gated()
    print("\nAll agency dossiers generated successfully.")


if __name__ == "__main__":
    main()
