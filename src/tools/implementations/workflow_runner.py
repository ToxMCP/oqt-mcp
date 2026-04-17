import base64
import copy
import hashlib
import inspect
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from src.integrations import oqt_assistant
from src.qsar import QsarClientError, qsar_client
from src.tools.hazard_contracts import (
    build_decision_owner,
    build_endpoint_summaries_from_qsar_results,
    build_hazard_applicability_domain,
    build_hazard_assessment_boundary,
    build_hazard_decision_boundary,
    build_hazard_evidence_blocks,
    build_hazard_required_external_inputs,
    build_hazard_semantic_coverage,
    build_hazard_supports,
    build_hazard_uncertainty_assessment,
    build_read_across_assessment_boundary,
    build_read_across_decision_boundary,
    build_read_across_required_external_inputs,
    build_read_across_supports,
    build_request_metadata,
    build_source_attribution,
)
from src.tools.provenance import build_provenance
from src.tools.registry import tool_registry
from src.utils.pdf_generator import generate_pdf_report
from src.utils.review import ReviewDecision, review_orchestrator

log = logging.getLogger(__name__)

TOXMCP_REPOSITORY_URL = "https://github.com/ToxMCP/oqt-mcp"
TOXMCP_HOMEPAGE_URL = "https://github.com/ToxMCP/toxmcp"
TOOLBOX_SOURCE_SYSTEM = "OECD QSAR Toolbox WebAPI"
TOOLBOX_COMPATIBILITY_NOTE = (
    "Targets OECD QSAR Toolbox WebAPI /api/v6 compatibility routes."
)
GENERATED_BY_VERSION = "O-QT MCP Server v0.3.0"


def _looks_like_uuid(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    try:
        UUID(text)
        return True
    except (ValueError, TypeError, AttributeError):
        return False


class WorkflowParams(BaseModel):
    identifier: str = Field(
        ..., description="Chemical identifier (common name, CAS number, or SMILES)."
    )
    search_type: str = Field(
        "name",
        description="How to interpret the identifier (`auto`, `name`, `cas`, `smiles`).",
    )
    context: Optional[str] = Field(
        None, description="Optional narrative context for the analysis."
    )
    profiler_guids: List[str] = Field(
        default_factory=list,
        description="Specific profiler GUIDs to execute (leave empty to skip).",
    )
    qsar_mode: str = Field(
        "recommended",
        description="QSAR execution preset (`recommended`, `all`, or `none`).",
    )
    qsar_guids: List[str] = Field(
        default_factory=list,
        description="Explicit QSAR model GUIDs to run (overrides presets when supplied).",
    )
    simulator_guids: List[str] = Field(
        default_factory=list,
        description="Metabolism simulator GUIDs to execute for the resolved chemId.",
    )
    llm_provider: Optional[str] = Field(
        None,
        description="Reserved for downstream LLM selection (not used server-side).",
    )
    llm_model: Optional[str] = Field(
        None,
        description="Reserved for downstream LLM selection (not used server-side).",
    )
    llm_api_key: Optional[str] = Field(
        None,
        description="Reserved for downstream LLM selection (not used server-side).",
    )
    require_human_review: bool = Field(
        default=False,
        description="When True, high-risk checkpoints require explicit approval before artifacts are generated.",
    )
    workflow_id: Optional[str] = Field(
        None,
        description="Optional workflow ID for resuming a review-paused workflow.",
    )
    checkpoint_approvals: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Optional list of approved checkpoint decisions to resume a review-paused workflow.",
    )

    @field_validator("search_type", mode="before")
    @classmethod
    def _normalise_search_type(cls, value: Any) -> str:
        if not value:
            return "name"
        return str(value).strip().lower()

    @field_validator("qsar_mode", mode="before")
    @classmethod
    def _normalise_qsar_mode(cls, value: Any) -> str:
        if not value:
            return "recommended"
        return str(value).strip().lower()


class GroupingJustificationParams(BaseModel):
    identifier: str = Field(
        ...,
        description="Target chemical identifier (common name, CAS number, or SMILES).",
    )
    search_type: str = Field(
        "name",
        description="How to interpret the target identifier (`auto`, `name`, `cas`, `smiles`).",
    )
    problem_formulation: str = Field(
        ...,
        description="Problem formulation and intended use of the grouping or read-across exercise.",
    )
    decision_context: str = Field(
        ...,
        description="Decision context such as screening, hazard identification, or risk assessment.",
    )
    endpoints: List[str] = Field(
        default_factory=list,
        description="Endpoints that require justification in the grouping dossier.",
    )
    route_of_exposure: Optional[str] = Field(
        None,
        description="Route of exposure relevant to the endpoints under consideration.",
    )
    grouping_hypothesis: str = Field(
        ...,
        description="Hypothesis describing why the target and source chemicals are sufficiently similar.",
    )
    analogue_identifiers: List[str] = Field(
        default_factory=list,
        description="Candidate source analogue or category member identifiers to resolve in the Toolbox.",
    )
    analogue_search_type: str = Field(
        "name",
        description="How to interpret the analogue identifiers (`auto`, `name`, `cas`, `smiles`).",
    )
    profiler_guids: List[str] = Field(
        default_factory=list,
        description="Profilers to execute as part of the similarity assessment.",
    )
    simulator_guids: List[str] = Field(
        default_factory=list,
        description="Metabolism simulators to execute for ADME/TK support.",
    )
    qsar_guids: List[str] = Field(
        default_factory=list,
        description="QSAR model GUIDs to execute as supporting evidence for the target substance.",
    )
    accepted_uncertainty_level: str = Field(
        "medium",
        description="Maximum residual uncertainty tolerated for the stated purpose (`low`, `medium`, `high`).",
    )
    context: Optional[str] = Field(
        None,
        description="Optional extra narrative instructions for the generated dossier.",
    )

    @field_validator("search_type", "analogue_search_type", mode="before")
    @classmethod
    def _normalise_search_modes(cls, value: Any) -> str:
        if not value:
            return "name"
        return str(value).strip().lower()

    @field_validator("accepted_uncertainty_level", mode="before")
    @classmethod
    def _normalise_uncertainty_level(cls, value: Any) -> str:
        if not value:
            return "medium"
        return str(value).strip().lower()

    @field_validator("endpoints", mode="before")
    @classmethod
    def _coerce_endpoints(cls, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return value
        return [str(value)]

    @model_validator(mode="after")
    def _validate_endpoints(self):
        self.endpoints = _unique(self.endpoints)
        if not self.endpoints:
            raise ValueError("Provide at least one endpoint.")
        return self


def _unique(values: List[str]) -> List[str]:
    seen = set()
    normalised: List[str] = []
    for item in values or []:
        candidate = (item or "").strip()
        if candidate and candidate not in seen:
            seen.add(candidate)
            normalised.append(candidate)
    return normalised


def _coerce_hits(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [entry for entry in payload if isinstance(entry, dict)]
    if isinstance(payload, dict):
        return [payload]
    return []


def _first_present(record: Dict[str, Any], candidates: List[str]) -> Any:
    for candidate in candidates:
        value = record.get(candidate)
        if value not in (None, ""):
            return value
    return None


def _chemical_summary(hit: Dict[str, Any], identifier: str) -> Dict[str, Any]:
    raw_names = hit.get("Names")
    names = (
        [str(name).strip() for name in raw_names if str(name).strip()]
        if isinstance(raw_names, list)
        else []
    )
    preferred_name = (
        names[0]
        if names
        else str(hit.get("Name") or hit.get("Caption") or identifier).strip()
    )
    summary = {
        "input_identifier": identifier,
        "preferred_name": preferred_name,
        "chem_id": hit.get("ChemId"),
        "cas": hit.get("Cas"),
        "names": names,
    }
    optional_fields = {
        "smiles": ["Smiles", "SMILES"],
        "canonical_smiles": ["CanonicalSmiles", "CanonicalSMILES", "Canonical"],
        "dtxsid": ["Dtxsid", "DTXSID"],
        "ec_number": ["EcNumber", "ECNumber"],
        "formula": ["Formula", "MolecularFormula"],
        "molecular_weight": ["MolWeight", "MolecularWeight", "MW"],
        "log_kow": ["LogKow", "logKow", "LogP", "XlogP"],
        "melting_point": ["MeltingPoint", "Mp"],
        "boiling_point": ["BoilingPoint", "Bp"],
        "density": ["Density"],
        "water_solubility": ["WaterSolubility", "SolubilityInWater"],
        "vapor_pressure": ["VaporPressure"],
    }
    for output_key, input_keys in optional_fields.items():
        value = _first_present(hit, input_keys)
        if value not in (None, ""):
            summary[output_key] = value
    return summary


def _normalise_scalar(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _summarise_payload(payload: Any) -> str:
    if payload is None:
        return "No payload returned."
    if isinstance(payload, list):
        return f"Returned {len(payload)} item(s)."
    if isinstance(payload, dict):
        keys = list(payload.keys())[:5]
        key_summary = ", ".join(str(key) for key in keys) or "no keys"
        return f"Returned object with keys: {key_summary}."
    text = str(payload).strip()
    if len(text) > 160:
        text = text[:157] + "..."
    return f"Returned {type(payload).__name__}: {text}"


def _build_evidence_row(
    subject_role: str,
    subject_name: str,
    evidence_type: str,
    tool_name: str,
    status: str,
    summary: str,
    *,
    endpoint: Optional[str] = None,
    reference: Optional[str] = None,
) -> Dict[str, Any]:
    row = {
        "subject_role": subject_role,
        "subject_name": subject_name,
        "evidence_type": evidence_type,
        "tool": tool_name,
        "status": status,
        "summary": summary,
    }
    if endpoint:
        row["endpoint"] = endpoint
    if reference:
        row["reference"] = reference
    return row


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _build_artifact_entry(
    *,
    field_name: str,
    delivery: str,
    media_type: str,
    description: str,
    payload: Any = None,
    encoding: Optional[str] = None,
    source: str = "mcp-inline-field",
    integrity_note: Optional[str] = None,
) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "fieldName": field_name,
        "delivery": delivery,
        "mediaType": media_type,
        "description": description,
        "source": source,
    }
    if encoding:
        entry["encoding"] = encoding

    payload_bytes: Optional[bytes] = None
    note = integrity_note
    if payload is not None:
        if media_type == "application/json":
            payload_bytes = _canonical_json_bytes(payload)
            if not note:
                note = "SHA-256 computed over canonical JSON serialization."
        elif isinstance(payload, (bytes, bytearray, memoryview)):
            payload_bytes = bytes(payload)
        else:
            payload_bytes = str(payload).encode("utf-8")

    if payload_bytes is not None:
        entry["sizeBytes"] = len(payload_bytes)
        entry["checksumSha256"] = hashlib.sha256(payload_bytes).hexdigest()
    if note:
        entry["integrityNote"] = note
    return entry


def _build_attachment_manifest(
    root_entity_type: str,
    artifacts: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    prefix = root_entity_type.replace("_", "-")
    manifest: List[Dict[str, Any]] = []
    attachment_specs = (
        ("json", "structured_log", f"{prefix}-log.json"),
        ("markdown", "narrative_summary", f"{prefix}-summary.md"),
        ("pdf", "audit_report", f"{prefix}-report.pdf"),
    )
    for artifact_key, role, name in attachment_specs:
        artifact = artifacts[artifact_key]
        manifest.append(
            {
                "name": name,
                "role": role,
                **artifact,
            }
        )
    return manifest


def _extract_numeric(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = _normalise_scalar(value)
    if not text:
        return None
    match = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", text.replace(",", "."))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


async def _collect_structure_signature(
    substance: Dict[str, Any],
    subject_role: str,
    toolbox_calls: List[Dict[str, Any]],
) -> Dict[str, Any]:
    name = substance.get("preferred_name", substance.get("input_identifier", "Unknown"))
    chem_id = substance.get("chem_id")
    input_smiles = _normalise_scalar(
        substance.get("canonical_smiles") or substance.get("smiles")
    )
    signature = {
        "subject_role": subject_role,
        "subject_name": name,
        "chem_id": chem_id,
        "input_smiles": input_smiles,
        "canonical_smiles": None,
        "connectivity": None,
        "status": "not_assessed",
        "notes": "No SMILES descriptor was available in the resolved Toolbox record.",
    }
    if not input_smiles:
        return signature

    notes: List[str] = []
    try:
        canonical_payload, canonical_meta = await _invoke_with_meta(
            qsar_client.canonicalize_structure, input_smiles
        )
        signature["canonical_smiles"] = _normalise_scalar(canonical_payload)
        entry = _format_meta(
            "structure/canonize",
            canonical_meta,
            chem_id=chem_id,
            subject_role=subject_role,
        )
        if entry:
            toolbox_calls.append(entry)
    except QsarClientError as exc:
        notes.append(f"Canonicalization failed: {exc}")

    try:
        connectivity_payload, connectivity_meta = await _invoke_with_meta(
            qsar_client.get_connectivity, input_smiles
        )
        signature["connectivity"] = _normalise_scalar(connectivity_payload)
        entry = _format_meta(
            "structure/connectivity",
            connectivity_meta,
            chem_id=chem_id,
            subject_role=subject_role,
        )
        if entry:
            toolbox_calls.append(entry)
    except QsarClientError as exc:
        notes.append(f"Connectivity calculation failed: {exc}")

    if signature["canonical_smiles"] or signature["connectivity"]:
        signature["status"] = "assessed"
        signature["notes"] = (
            "Derived structure signature from Toolbox structure helpers."
        )
        if notes:
            signature["notes"] += " " + " ".join(notes)
    else:
        signature["status"] = "partial" if notes else "not_assessed"
        signature["notes"] = " ".join(notes) if notes else signature["notes"]
    return signature


def _build_structure_comparison(
    target_signature: Dict[str, Any],
    source_signatures: List[Dict[str, Any]],
) -> Dict[str, Any]:
    comparisons: List[Dict[str, Any]] = []
    assessed_pairs = 0
    canonical_exact_matches = 0
    connectivity_exact_matches = 0
    missing_pairs = 0

    for source in source_signatures:
        canonical_match = None
        connectivity_match = None
        comparable = False
        notes: List[str] = []

        if target_signature.get("canonical_smiles") and source.get("canonical_smiles"):
            canonical_match = (
                target_signature["canonical_smiles"] == source["canonical_smiles"]
            )
            comparable = True
            if canonical_match:
                canonical_exact_matches += 1
                notes.append("Canonical SMILES match exactly.")
            else:
                notes.append("Canonical SMILES differ.")

        if target_signature.get("connectivity") and source.get("connectivity"):
            connectivity_match = (
                target_signature["connectivity"] == source["connectivity"]
            )
            comparable = True
            if connectivity_match:
                connectivity_exact_matches += 1
                notes.append("Connectivity strings match exactly.")
            else:
                notes.append("Connectivity strings differ.")

        if comparable:
            assessed_pairs += 1
            status = "assessed"
        else:
            missing_pairs += 1
            status = "not_assessed"
            notes.append(
                "Comparable structure signatures were not available for both substances."
            )

        comparisons.append(
            {
                "source_name": source.get("subject_name"),
                "source_chem_id": source.get("chem_id"),
                "status": status,
                "canonical_match": canonical_match,
                "connectivity_match": connectivity_match,
                "target_canonical_smiles": target_signature.get("canonical_smiles"),
                "source_canonical_smiles": source.get("canonical_smiles"),
                "target_connectivity": target_signature.get("connectivity"),
                "source_connectivity": source.get("connectivity"),
                "notes": " ".join(notes),
            }
        )

    return {
        "target": target_signature,
        "sources": source_signatures,
        "comparisons": comparisons,
        "summary": {
            "assessed_pairs": assessed_pairs,
            "canonical_exact_matches": canonical_exact_matches,
            "connectivity_exact_matches": connectivity_exact_matches,
            "pairs_missing_structure_signatures": missing_pairs,
        },
    }


def _compare_descriptor_values(target_value: Any, source_value: Any) -> Dict[str, Any]:
    target_text = _normalise_scalar(target_value)
    source_text = _normalise_scalar(source_value)
    result = {"target": target_text, "source": source_text}
    if target_text is None or source_text is None:
        result["comparison"] = "insufficient_data"
        return result

    target_num = _extract_numeric(target_value)
    source_num = _extract_numeric(source_value)
    if target_num is not None and source_num is not None:
        absolute_delta = round(source_num - target_num, 6)
        relative_delta = (
            round(abs(absolute_delta) / abs(target_num), 6) if target_num else None
        )
        approx_match = abs(absolute_delta) <= 0.01 or (
            relative_delta is not None and relative_delta <= 0.05
        )
        result["comparison"] = "approx_match" if approx_match else "different"
        result["absolute_delta"] = absolute_delta
        if relative_delta is not None:
            result["relative_delta"] = relative_delta
        return result

    result["comparison"] = "exact_match" if target_text == source_text else "different"
    return result


def _build_physicochemical_comparison(
    target_substance: Dict[str, Any],
    source_analogues: List[Dict[str, Any]],
) -> Dict[str, Any]:
    descriptor_keys = [
        "formula",
        "molecular_weight",
        "log_kow",
        "melting_point",
        "boiling_point",
        "density",
        "water_solubility",
        "vapor_pressure",
    ]
    target_descriptors = {
        key: target_substance.get(key)
        for key in descriptor_keys
        if target_substance.get(key) not in (None, "")
    }
    comparisons: List[Dict[str, Any]] = []
    assessed_pairs = 0
    shared_descriptor_count = 0

    for analogue in source_analogues:
        shared: Dict[str, Any] = {}
        for key in descriptor_keys:
            target_value = target_substance.get(key)
            source_value = analogue.get(key)
            if target_value in (None, "") or source_value in (None, ""):
                continue
            shared[key] = _compare_descriptor_values(target_value, source_value)

        if shared:
            assessed_pairs += 1
            shared_descriptor_count += len(shared)
            status = "assessed"
            notes = f"Compared {len(shared)} shared descriptor(s)."
        else:
            status = "not_assessed"
            notes = "No overlapping physicochemical descriptors were available in the resolved records."

        comparisons.append(
            {
                "source_name": analogue.get("preferred_name"),
                "source_chem_id": analogue.get("chem_id"),
                "status": status,
                "shared_descriptors": shared,
                "notes": notes,
            }
        )

    return {
        "target_descriptors": target_descriptors,
        "comparisons": comparisons,
        "summary": {
            "assessed_pairs": assessed_pairs,
            "shared_descriptor_count": shared_descriptor_count,
            "descriptor_keys_considered": descriptor_keys,
        },
    }


def _structure_evidence_rows(
    structure_comparison: Dict[str, Any]
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    target = structure_comparison.get("target", {})
    if target.get("input_smiles"):
        rows.append(
            _build_evidence_row(
                "target",
                target.get("subject_name", "Unknown"),
                "structure_signature",
                "canonicalize_structure/structure_connectivity",
                target.get("status", "not_assessed"),
                target.get("notes", ""),
                reference=str(target.get("chem_id")) if target.get("chem_id") else None,
            )
        )
    for comparison in structure_comparison.get("comparisons", []):
        rows.append(
            _build_evidence_row(
                "source_analogue",
                comparison.get("source_name", "Unknown"),
                "structure_comparison",
                "canonicalize_structure/structure_connectivity",
                comparison.get("status", "not_assessed"),
                comparison.get("notes", ""),
                reference=(
                    str(comparison.get("source_chem_id"))
                    if comparison.get("source_chem_id")
                    else None
                ),
            )
        )
    return rows


def _physchem_evidence_rows(
    physicochemical_comparison: Dict[str, Any],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for comparison in physicochemical_comparison.get("comparisons", []):
        rows.append(
            _build_evidence_row(
                "source_analogue",
                comparison.get("source_name", "Unknown"),
                "physicochemical_comparison",
                "search_chemicals",
                comparison.get("status", "not_assessed"),
                comparison.get("notes", ""),
                reference=(
                    str(comparison.get("source_chem_id"))
                    if comparison.get("source_chem_id")
                    else None
                ),
            )
        )
    return rows


async def _resolve_chemical(
    identifier: str,
    search_type: str,
    label: str,
    toolbox_calls: List[Dict[str, Any]],
) -> Dict[str, Any]:
    candidate = (identifier or "").strip()
    resolved = {
        "identifier": candidate,
        "search_type": search_type,
        "status": "not_found",
        "hits": [],
        "selected": None,
        "summary": None,
        "error": None,
    }
    if not candidate:
        resolved["status"] = "skipped"
        resolved["error"] = "Identifier was blank."
        return resolved

    if _looks_like_uuid(candidate):
        primary = {"ChemId": candidate, "Names": [candidate]}
        resolved["status"] = "resolved"
        resolved["hits"] = [primary]
        resolved["selected"] = primary
        resolved["summary"] = _chemical_summary(primary, candidate)
        return resolved

    try:
        payload, meta = await _invoke_with_meta(
            qsar_client.search_chemicals, candidate, search_type
        )
    except QsarClientError as exc:
        resolved["status"] = "error"
        resolved["error"] = str(exc)
        return resolved

    entry = _format_meta(f"{label}/search", meta, identifier=candidate)
    if entry:
        toolbox_calls.append(entry)

    hits = _coerce_hits(payload)
    resolved["hits"] = hits
    if not hits:
        resolved["error"] = f"No Toolbox records matched '{candidate}'."
        return resolved

    primary = next((hit for hit in hits if hit.get("ChemId")), hits[0])
    resolved["status"] = "resolved"
    resolved["selected"] = primary
    resolved["summary"] = _chemical_summary(primary, candidate)
    return resolved


def _format_meta(
    label: str, meta: Dict[str, Any] | None, **extra: Any
) -> Dict[str, Any] | None:
    if not meta:
        return None
    entry = {
        "endpoint": label,
        "attempts": meta.get("attempts"),
        "duration_ms": meta.get("duration_ms"),
        "timeout_profile": meta.get("timeout_profile"),
        "status_code": meta.get("status_code"),
        "api_versions": meta.get("api_versions"),
        "server_date": meta.get("server_date"),
    }
    entry.update({k: v for k, v in extra.items() if v is not None})
    return {k: v for k, v in entry.items() if v is not None}


def _aggregate_calls(calls: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = (
        round(sum(call.get("duration_ms", 0.0) or 0.0 for call in calls), 3)
        if calls
        else 0.0
    )
    return {"calls": calls, "total_duration_ms": total}


def _build_source_records(toolbox_meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for call in toolbox_meta.get("calls", []) or []:
        name = _normalise_scalar(call.get("endpoint")) or "unknown"
        record: Dict[str, Any] = {"name": name, "endpoint": name}
        status_code = call.get("status_code")
        if isinstance(status_code, (int, float)):
            record["statusCode"] = int(status_code)
        duration_ms = call.get("duration_ms")
        if isinstance(duration_ms, (int, float)):
            record["durationMs"] = float(duration_ms)
        attempts = call.get("attempts")
        if isinstance(attempts, (int, float)):
            record["attempts"] = int(attempts)
        timeout_profile = _normalise_scalar(call.get("timeout_profile"))
        if timeout_profile:
            record["timeoutProfile"] = timeout_profile
        reference = _normalise_scalar(
            call.get("qsar_guid")
            or call.get("profiler_guid")
            or call.get("simulator_guid")
            or call.get("chem_id")
            or call.get("identifier")
        )
        if reference:
            record["reference"] = reference
        records.append(record)
    return records


def _build_workflow_provenance(
    generated_at: str, toolbox_meta: Dict[str, Any]
) -> Dict[str, Any]:
    sources = _build_source_records(toolbox_meta)
    source_tools = _unique([item["name"] for item in sources])
    provenance: Dict[str, Any] = {
        "sourceSystem": TOOLBOX_SOURCE_SYSTEM,
        "generatedBy": GENERATED_BY_VERSION,
        "generatedAt": generated_at,
        "repository": TOXMCP_REPOSITORY_URL,
        "toolboxCompatibility": TOOLBOX_COMPATIBILITY_NOTE,
        "references": [TOXMCP_HOMEPAGE_URL],
    }
    if source_tools:
        provenance["sourceTools"] = source_tools
    if sources:
        provenance["sources"] = sources
    return provenance


def _build_summary_provenance(
    *,
    record_key: str,
    record_value: str,
    generated_at: str,
    toolbox_meta: Dict[str, Any],
) -> Dict[str, Any]:
    sources = _build_source_records(toolbox_meta)
    source_tools = _unique([item["name"] for item in sources])
    provenance: Dict[str, Any] = {
        record_key: record_value,
        "sourceSystem": TOOLBOX_SOURCE_SYSTEM,
        "generatedBy": GENERATED_BY_VERSION,
        "generatedAt": generated_at,
        "references": [TOXMCP_REPOSITORY_URL],
    }
    if source_tools:
        provenance["sourceTools"] = source_tools
    if sources:
        provenance["sources"] = sources
    return provenance


async def _invoke_with_meta(func, *args, **kwargs):
    try:
        result = await func(*args, with_meta=True, **kwargs)
    except TypeError:
        filtered_kwargs = kwargs
        try:
            signature = inspect.signature(func)
            filtered_kwargs = {
                key: value
                for key, value in kwargs.items()
                if key in signature.parameters
            }
        except (TypeError, ValueError):
            filtered_kwargs = kwargs
        result = await func(*args, **filtered_kwargs)
        return result, None
    if isinstance(result, tuple) and len(result) == 2:
        return result
    return result, None


async def _fetch_model_provenance(
    qsar_guid: str, cache: Dict[str, Dict[str, Any] | None]
) -> tuple[Dict[str, Any] | None, Dict[str, Any] | None]:
    if qsar_guid in cache:
        return cache[qsar_guid], None
    try:
        payload, meta = await _invoke_with_meta(
            qsar_client.get_model_metadata, qsar_guid
        )
    except QsarClientError as exc:
        log.warning("QSAR model metadata lookup failed for %s: %s", qsar_guid, exc)
        cache[qsar_guid] = None
        return None, None
    provenance = build_provenance(payload)
    cache[qsar_guid] = provenance
    return provenance, _format_meta("about/object", meta, qsar_guid=qsar_guid)


async def _fetch_profiler_provenance(
    profiler_guid: str, cache: Dict[str, Dict[str, Any] | None]
) -> tuple[Dict[str, Any] | None, Dict[str, Any] | None]:
    if profiler_guid in cache:
        return cache[profiler_guid], None
    try:
        payload, meta = await _invoke_with_meta(
            qsar_client.get_profiler_info, profiler_guid
        )
    except QsarClientError as exc:
        log.warning("Profiler metadata lookup failed for %s: %s", profiler_guid, exc)
        cache[profiler_guid] = None
        return None, None
    provenance = build_provenance(payload)
    cache[profiler_guid] = provenance
    return provenance, _format_meta("profiling/info", meta, profiler_guid=profiler_guid)


async def _fetch_simulator_provenance(
    simulator_guid: str, cache: Dict[str, Dict[str, Any] | None]
) -> tuple[Dict[str, Any] | None, Dict[str, Any] | None]:
    if simulator_guid in cache:
        return cache[simulator_guid], None
    try:
        payload, meta = await _invoke_with_meta(
            qsar_client.get_simulator_info, simulator_guid
        )
    except QsarClientError as exc:
        log.warning("Simulator metadata lookup failed for %s: %s", simulator_guid, exc)
        cache[simulator_guid] = None
        return None, None
    provenance = build_provenance(payload)
    cache[simulator_guid] = provenance
    return provenance, _format_meta(
        "metabolism/info", meta, simulator_guid=simulator_guid
    )


def _iso_utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _handoff_record_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def _portable_identity_from_summary(
    summary: Dict[str, Any] | None, fallback_identifier: str
) -> Dict[str, Any] | None:
    if not isinstance(summary, dict):
        return None
    chem_id = _normalise_scalar(summary.get("chem_id"))
    preferred_name = _normalise_scalar(summary.get("preferred_name"))
    if not chem_id or not preferred_name:
        return None

    identity = {
        "inputIdentifier": _normalise_scalar(summary.get("input_identifier"))
        or fallback_identifier,
        "preferredName": preferred_name,
        "chemId": chem_id,
    }
    cas = _normalise_scalar(summary.get("cas"))
    smiles = _normalise_scalar(summary.get("smiles"))
    if cas:
        identity["cas"] = cas
    if smiles:
        identity["smiles"] = smiles
    return identity


def _matching_errors(errors: List[str], reference: str) -> List[str]:
    return [message for message in errors if reference in message]


def _build_profiler_findings(
    requested_ids: List[str], results: List[Dict[str, Any]], errors: List[str]
) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for item in results or []:
        reference = _normalise_scalar(item.get("profiler_guid"))
        if reference:
            grouped.setdefault(reference, []).append(item)

    findings: List[Dict[str, Any]] = []
    for requested_id in _unique(requested_ids):
        matches = grouped.get(requested_id, [])
        if matches:
            provenance = (
                matches[0].get("profiler_provenance")
                if isinstance(matches[0], dict)
                else None
            )
            provenance_clause = ""
            if isinstance(provenance, dict):
                label = _normalise_scalar(provenance.get("title"))
                owner = _normalise_scalar(provenance.get("owner"))
                details = [item for item in [label, owner] if item]
                if details:
                    provenance_clause = f" ({'; '.join(details)})"
            subject_roles = _unique(
                [
                    str(item.get("subject_role"))
                    for item in matches
                    if item.get("subject_role")
                ]
            )
            subject_clause = (
                f" across {', '.join(subject_roles)}" if subject_roles else ""
            )
            findings.append(
                {
                    "profilerGuid": requested_id,
                    "status": "ok",
                    "summary": (
                        f"Collected {len(matches)} profiler result(s){subject_clause}{provenance_clause}. "
                        f"{_summarise_payload(matches[0].get('result'))}"
                    ),
                    **(
                        {"source": build_source_attribution(provenance)}
                        if build_source_attribution(provenance)
                        else {}
                    ),
                }
            )
            continue

        error_messages = _matching_errors(errors, requested_id)
        findings.append(
            {
                "profilerGuid": requested_id,
                "status": "error" if error_messages else "not_run",
                "summary": (
                    " ".join(error_messages)
                    if error_messages
                    else "Requested profiler evidence was not returned."
                ),
            }
        )
    return findings


def _build_metabolism_findings(
    requested_ids: List[str], results: List[Dict[str, Any]], errors: List[str]
) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for item in results or []:
        reference = _normalise_scalar(item.get("simulator_guid"))
        if reference:
            grouped.setdefault(reference, []).append(item)

    findings: List[Dict[str, Any]] = []
    for requested_id in _unique(requested_ids):
        matches = grouped.get(requested_id, [])
        if matches:
            provenance = (
                matches[0].get("simulator_provenance")
                if isinstance(matches[0], dict)
                else None
            )
            provenance_clause = ""
            if isinstance(provenance, dict):
                label = _normalise_scalar(provenance.get("title"))
                owner = _normalise_scalar(provenance.get("owner"))
                details = [item for item in [label, owner] if item]
                if details:
                    provenance_clause = f" ({'; '.join(details)})"
            findings.append(
                {
                    "simulatorGuid": requested_id,
                    "status": "ok",
                    "summary": (
                        f"Collected {len(matches)} simulator result(s){provenance_clause}. "
                        f"{_summarise_payload(matches[0].get('result'))}"
                    ),
                    **(
                        {"metaboliteCount": len(matches[0].get("result", []))}
                        if isinstance(matches[0].get("result"), list)
                        else {}
                    ),
                    **(
                        {"source": build_source_attribution(provenance)}
                        if build_source_attribution(provenance)
                        else {}
                    ),
                }
            )
            continue

        error_messages = _matching_errors(errors, requested_id)
        findings.append(
            {
                "simulatorGuid": requested_id,
                "status": "error" if error_messages else "not_run",
                "summary": (
                    " ".join(error_messages)
                    if error_messages
                    else "Requested metabolism evidence was not returned."
                ),
            }
        )
    return findings


def _build_qsar_findings(
    requested_ids: List[str], results: List[Dict[str, Any]], errors: List[str]
) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for item in results or []:
        reference = _normalise_scalar(item.get("qsar_guid"))
        if reference:
            grouped.setdefault(reference, []).append(item)

    findings: List[Dict[str, Any]] = []
    for requested_id in _unique(requested_ids):
        matches = grouped.get(requested_id, [])
        if matches:
            provenance = (
                matches[0].get("model_provenance")
                if isinstance(matches[0], dict)
                else None
            )
            summary_prefix = ""
            if isinstance(provenance, dict):
                label = _normalise_scalar(provenance.get("title"))
                owner = _normalise_scalar(provenance.get("owner"))
                details = [item for item in [label, owner] if item]
                if details:
                    summary_prefix = f"{'; '.join(details)}. "
            prediction = matches[0].get("prediction")
            prediction_value = None
            endpoint = None
            unit = None
            domain_status = None
            if isinstance(prediction, dict):
                prediction_value = prediction.get("Value")
                endpoint = _normalise_scalar(prediction.get("Endpoint"))
                unit = _normalise_scalar(prediction.get("Unit"))
                domain_status = _normalise_scalar(
                    prediction.get("DomainResult") or prediction.get("Domain")
                )
            if not domain_status:
                domain = matches[0].get("domain")
                if isinstance(domain, dict):
                    domain_status = _normalise_scalar(
                        domain.get("DomainResult") or domain.get("Domain")
                    )
                else:
                    domain_status = _normalise_scalar(domain)
            findings.append(
                {
                    "qsarGuid": requested_id,
                    "status": "ok",
                    "predictionSummary": summary_prefix
                    + _summarise_payload(matches[0].get("prediction")),
                    "domainSummary": _summarise_payload(matches[0].get("domain")),
                    **({"endpoint": endpoint} if endpoint else {}),
                    **(
                        {"predictedValue": prediction_value}
                        if prediction_value is not None
                        else {}
                    ),
                    **({"unit": unit} if unit else {}),
                    **({"domainStatus": domain_status} if domain_status else {}),
                    **(
                        {"source": build_source_attribution(provenance)}
                        if build_source_attribution(provenance)
                        else {}
                    ),
                }
            )
            continue

        error_messages = _matching_errors(errors, requested_id)
        error_summary = (
            " ".join(error_messages)
            if error_messages
            else "Requested QSAR evidence was not returned."
        )
        findings.append(
            {
                "qsarGuid": requested_id,
                "status": "error" if error_messages else "not_run",
                "predictionSummary": error_summary,
                "domainSummary": error_summary,
            }
        )
    return findings


def _build_portable_workflow_record(
    *,
    record_id: str,
    identifier: str,
    search_type: str,
    context: Optional[str],
    primary_entrypoint: str,
    helper_tools: List[str],
    status: str,
    log_bundle: Dict[str, Any],
    toolbox_meta: Dict[str, Any],
    assistant_enabled: bool,
    generated_at: str,
    root_entity_type: str,
    selected_summary: Dict[str, Any] | None = None,
    artifact_log: Optional[Dict[str, Any]] = None,
    summary_markdown: Optional[str] = None,
    pdf_bytes: Optional[bytes] = None,
) -> Dict[str, Any]:
    input_identifier = {"value": identifier}
    if isinstance(selected_summary, dict):
        resolved_name = _normalise_scalar(selected_summary.get("preferred_name"))
        chem_id = _normalise_scalar(selected_summary.get("chem_id"))
        if resolved_name:
            input_identifier["resolvedName"] = resolved_name
        if chem_id:
            input_identifier["chemId"] = chem_id

    inputs = log_bundle.get("inputs", {})
    json_payload = artifact_log if artifact_log is not None else log_bundle
    markdown_payload = summary_markdown
    if markdown_payload is None:
        markdown_payload = _normalise_scalar(
            (artifact_log or {}).get("final_report")
            if isinstance(artifact_log, dict)
            else None
        ) or _normalise_scalar(log_bundle.get("final_report"))

    artifacts = {
        "json": _build_artifact_entry(
            field_name="log_json",
            delivery="inline",
            media_type="application/json",
            description="Comprehensive workflow log bundle.",
            payload=json_payload,
        ),
        "markdown": _build_artifact_entry(
            field_name="summary_markdown",
            delivery="inline",
            media_type="text/markdown",
            description="Human-readable workflow narrative.",
            payload=markdown_payload,
        ),
        "pdf": _build_artifact_entry(
            field_name="pdf_report_base64",
            delivery="inline",
            media_type="application/pdf",
            description="Base64-encoded PDF report.",
            payload=pdf_bytes,
            encoding="base64",
        ),
    }

    return {
        "schemaName": "oqtWorkflowRecord",
        "schemaVersion": "v1",
        "module": "oqt-mcp",
        "workflowId": record_id,
        "inputIdentifier": input_identifier,
        "searchType": search_type,
        "context": context,
        "rootEntity": {
            "entityType": root_entity_type,
            "entityId": record_id,
            "label": input_identifier.get("resolvedName") or identifier,
        },
        "packageSemantics": {
            "mode": "working_bundle",
            "isReadOnly": False,
            "containsExternalReferences": True,
            "purpose": "live_mcp_response",
        },
        "toolchain": {
            "primaryEntrypoint": primary_entrypoint,
            "helperTools": _unique(helper_tools),
            "toolboxCompatibility": TOOLBOX_COMPATIBILITY_NOTE,
        },
        "artifacts": artifacts,
        "attachments": _build_attachment_manifest(root_entity_type, artifacts),
        "executionMetadata": {
            "status": status,
            "assistantEnabled": assistant_enabled,
            "requestedProfilers": _unique(inputs.get("profiler_guids", []) or []),
            "requestedSimulators": _unique(inputs.get("simulator_guids", []) or []),
            "requestedQsarModels": _unique(inputs.get("qsar_guids", []) or []),
            "toolboxCallCount": len(toolbox_meta.get("calls", []) or []),
            "toolboxTotalDurationMs": toolbox_meta.get("total_duration_ms", 0.0) or 0.0,
            "errors": [str(message) for message in log_bundle.get("errors", []) or []],
        },
        "provenance": _build_workflow_provenance(generated_at, toolbox_meta),
    }


def _build_workflow_portable_handoffs(
    status: str,
    log_bundle: Dict[str, Any],
    toolbox_meta: Dict[str, Any],
    *,
    assistant_enabled: bool = False,
    artifact_log: Optional[Dict[str, Any]] = None,
    summary_markdown: Optional[str] = None,
    pdf_bytes: Optional[bytes] = None,
) -> Dict[str, Any]:
    inputs = log_bundle.get("inputs", {})
    identifier = str(
        inputs.get("identifier") or log_bundle.get("identifier") or ""
    ).strip()
    search_type = str(inputs.get("search_type") or "name")
    selected_summary = None
    if isinstance(log_bundle.get("selected_chemical"), dict):
        selected_summary = _chemical_summary(
            log_bundle["selected_chemical"], identifier
        )

    generated_at = _iso_utc_now()
    workflow_id = _handoff_record_id("oqtwf")
    handoffs = {
        "oqtWorkflowRecord.v1": _build_portable_workflow_record(
            record_id=workflow_id,
            identifier=identifier,
            search_type=search_type,
            context=inputs.get("context"),
            primary_entrypoint="run_oqt_multiagent_workflow",
            helper_tools=_unique(
                ["search_chemicals"]
                + (
                    ["run_profiler"]
                    if _unique(inputs.get("profiler_guids", []) or [])
                    else []
                )
                + (
                    ["run_metabolism_simulator"]
                    if _unique(inputs.get("simulator_guids", []) or [])
                    else []
                )
                + (
                    ["run_qsar_model"]
                    if _unique(inputs.get("qsar_guids", []) or [])
                    else []
                )
            ),
            status=status,
            log_bundle=log_bundle,
            toolbox_meta=toolbox_meta,
            assistant_enabled=assistant_enabled,
            generated_at=generated_at,
            root_entity_type="workflow_execution",
            selected_summary=selected_summary,
            artifact_log=artifact_log,
            summary_markdown=summary_markdown,
            pdf_bytes=pdf_bytes,
        )
    }

    identity = _portable_identity_from_summary(selected_summary, identifier)
    if not identity:
        return handoffs

    errors = [str(message) for message in log_bundle.get("errors", []) or []]
    profiler_findings = _build_profiler_findings(
        inputs.get("profiler_guids", []) or [],
        log_bundle.get("profiler_results", []) or [],
        errors,
    )
    metabolism_findings = _build_metabolism_findings(
        inputs.get("simulator_guids", []) or [],
        log_bundle.get("simulator_results", []) or [],
        errors,
    )
    qsar_findings = _build_qsar_findings(
        inputs.get("qsar_guids", []) or [],
        log_bundle.get("qsar_results", []) or [],
        errors,
    )
    endpoint_summaries = build_endpoint_summaries_from_qsar_results(
        log_bundle.get("qsar_results", []) or []
    )

    limitations: List[str] = []
    if status != "ok":
        limitations.append(f"Workflow completed with status '{status}'.")
    if inputs.get("profiler_guids") and not any(
        item.get("status") == "ok" for item in profiler_findings
    ):
        limitations.append("No requested profiler evidence was returned successfully.")
    if inputs.get("simulator_guids") and not any(
        item.get("status") == "ok" for item in metabolism_findings
    ):
        limitations.append(
            "No requested metabolism evidence was returned successfully."
        )
    if inputs.get("qsar_guids") and not any(
        item.get("status") == "ok" for item in qsar_findings
    ):
        limitations.append("No requested QSAR evidence was returned successfully.")
    limitations.extend(errors)

    uncertainty_assessment = build_hazard_uncertainty_assessment(
        endpoint_record_count=0,
        profiling_record_count=sum(
            1 for item in profiler_findings if item.get("status") == "ok"
        ),
        profiling_requested_total=len(_unique(inputs.get("profiler_guids", []) or [])),
        metabolism_record_count=sum(
            1 for item in metabolism_findings if item.get("status") == "ok"
        ),
        metabolism_requested_total=len(
            _unique(inputs.get("simulator_guids", []) or [])
        ),
        qsar_record_count=sum(
            1 for item in qsar_findings if item.get("status") == "ok"
        ),
        qsar_requested_total=len(_unique(inputs.get("qsar_guids", []) or [])),
        extra_gaps=errors,
    )
    applicability_domain = build_hazard_applicability_domain(qsar_findings)
    uncertainty_assessment["semanticCoverage"] = build_hazard_semantic_coverage(
        endpoint_summaries=endpoint_summaries,
        applicability_domain=applicability_domain,
        uncertainty_assessment=uncertainty_assessment,
    )

    handoffs["oqtHazardEvidenceSummary.v1"] = {
        "schemaName": "oqtHazardEvidenceSummary",
        "schemaVersion": "v1",
        "module": "oqt-mcp",
        "chemicalIdentity": identity,
        "profilers": profiler_findings,
        "metabolismFindings": metabolism_findings,
        "qsarFindings": qsar_findings,
        "endpointSummaries": endpoint_summaries,
        "evidenceBlocks": build_hazard_evidence_blocks(
            endpoint_summaries=endpoint_summaries,
            profiler_findings=profiler_findings,
            metabolism_findings=metabolism_findings,
            qsar_findings=qsar_findings,
            uncertainty_assessment=uncertainty_assessment,
        ),
        "requestMetadata": build_request_metadata(
            requested_at=generated_at,
            requested_endpoints=[],
            requested_profilers=inputs.get("profiler_guids", []) or [],
            requested_simulators=inputs.get("simulator_guids", []) or [],
            requested_qsar_models=inputs.get("qsar_guids", []) or [],
            summary_only=True,
        ),
        "assessmentBoundary": build_hazard_assessment_boundary(),
        "decisionBoundary": build_hazard_decision_boundary(),
        "decisionOwner": build_decision_owner(),
        "supports": build_hazard_supports(
            endpoint_summaries=endpoint_summaries,
            profiler_findings=profiler_findings,
            applicability_domain=applicability_domain,
        ),
        "requiredExternalInputs": build_hazard_required_external_inputs(),
        "uncertaintyAssessment": uncertainty_assessment,
        "applicabilityDomain": applicability_domain,
        "applicabilityNotes": [
            TOOLBOX_COMPATIBILITY_NOTE,
            "Use this module-scoped evidence as input to a downstream orchestrator for cross-module synthesis.",
        ],
        "provenance": {
            **_build_summary_provenance(
                record_key="workflowId",
                record_value=workflow_id,
                generated_at=generated_at,
                toolbox_meta=toolbox_meta,
            )
        },
        "limitations": _unique(limitations),
        "context": inputs.get("context"),
    }
    return handoffs


def _build_applicability_domain(
    grouping_justification: Dict[str, Any],
) -> Dict[str, Any]:
    report_context = grouping_justification.get("report_context", {}) or {}
    similarity_assessment = (
        grouping_justification.get("similarity_assessment", {}) or {}
    )
    uncertainty = grouping_justification.get("uncertainty_assessment", {}) or {}
    hypothesis = _normalise_scalar(report_context.get("grouping_hypothesis"))
    inclusion_criteria: List[str] = []
    if hypothesis:
        inclusion_criteria.append(f"Grouping hypothesis: {hypothesis}")
    inclusion_criteria.append(
        "Target and source substances must resolve to Toolbox records with stable identifiers and enough comparison data to support analogue evaluation."
    )
    endpoints = [
        str(item) for item in report_context.get("endpoints", []) or [] if item
    ]
    if endpoints:
        inclusion_criteria.append(
            f"Assessment scope is limited to the requested endpoint set: {', '.join(endpoints)}."
        )
    route_of_exposure = _normalise_scalar(report_context.get("route_of_exposure"))
    if route_of_exposure:
        inclusion_criteria.append(
            f"Assessment scope is limited to the stated route of exposure: {route_of_exposure}."
        )

    exclusion_criteria = []
    for excluded in grouping_justification.get("excluded_analogues", []) or []:
        analogue_identifier = (
            _normalise_scalar(excluded.get("identifier")) or "Unknown analogue"
        )
        reason = _normalise_scalar(excluded.get("reason")) or "Unspecified exclusion."
        exclusion_criteria.append(f"{analogue_identifier}: {reason}")

    allowed_differences = []
    if hypothesis:
        allowed_differences.append(
            "Differences are only acceptable when the stated grouping hypothesis remains plausible across the assessed similarity contexts and residual uncertainty stays within the accepted level."
        )

    boundary_notes: List[str] = []
    for aspect in (
        "structural_similarity",
        "physicochemical_similarity",
        "adme_tk_similarity",
        "mechanistic_similarity",
    ):
        comments = _normalise_scalar(
            (similarity_assessment.get(aspect) or {}).get("comments")
        )
        if comments:
            boundary_notes.append(comments)
    for item in uncertainty.get("what_is_not_addressed", []) or []:
        label = str(item).replace("_", " ")
        boundary_notes.append(f"Not fully addressed: {label}.")

    supporting_contexts = [
        aspect
        for aspect, value in similarity_assessment.items()
        if isinstance(value, dict) and value.get("status") != "not_assessed"
    ]

    return {
        "inclusionCriteria": _unique(inclusion_criteria),
        "exclusionCriteria": _unique(exclusion_criteria),
        "allowedDifferences": _unique(allowed_differences),
        "boundaryNotes": _unique(boundary_notes),
        "supportingSimilarityContexts": _unique(supporting_contexts),
        "subcategoryNotes": [],
    }


def _classify_result_type(row: Dict[str, Any]) -> str:
    tool_name = _normalise_scalar(row.get("tool")) or ""
    evidence_type = _normalise_scalar(row.get("evidence_type")) or ""
    if tool_name in {"run_profiler", "group_chemicals_by_profiler"}:
        return "profiler"
    if tool_name == "run_metabolism_simulator":
        return "metabolism_simulation"
    if tool_name == "run_qsar_model" or evidence_type == "qsar":
        return "qsar_prediction"
    if evidence_type in {"omics", "hts_hcs_omics"}:
        return "hts_hcs_omics"
    if evidence_type == "aop":
        return "aop"
    return "other"


def _build_portable_data_matrix(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    portable_rows = []
    for row in rows or []:
        status = _normalise_status(row.get("status")) or "not_run"
        subject_role = _normalise_scalar(row.get("subject_role")) or "unknown"
        if subject_role not in {
            "target",
            "source_analogue",
            "category_member",
            "unknown",
        }:
            subject_role = "unknown"
        portable_row: Dict[str, Any] = {
            "subjectRole": subject_role,
            "subjectName": str(row.get("subject_name") or "Unknown subject"),
            "evidenceType": str(row.get("evidence_type") or "other"),
            "toolName": str(row.get("tool") or "unknown"),
            "resultType": _classify_result_type(row),
            "status": status,
            "summary": str(row.get("summary") or "No summary recorded."),
        }
        endpoint = _normalise_scalar(row.get("endpoint"))
        if endpoint:
            portable_row["endpoint"] = endpoint
        reference = _normalise_scalar(row.get("reference"))
        if reference:
            portable_row["reference"] = reference
        portable_rows.append(portable_row)
    return {
        "rowCount": len(portable_rows),
        "rows": portable_rows,
        "notes": [
            "Rows summarize the O-QT evidence matrix assembled for the grouping dossier."
        ],
    }


def _build_portable_uncertainty_table(
    uncertainty_assessment: Dict[str, Any],
    decision_context: str,
    recommended_follow_ups: List[str],
) -> Dict[str, Any]:
    rows = []
    for item in uncertainty_assessment.get("assessment_table", []) or []:
        rows.append(
            {
                "aspect": str(item.get("aspect") or "unspecified"),
                "dataQuality": str(item.get("data_quality") or "low"),
                "strengthOfEvidence": str(item.get("strength_of_evidence") or "low"),
                "uncertainty": str(item.get("uncertainty") or "high"),
                "comments": str(item.get("comments") or ""),
            }
        )
    acceptable = bool(uncertainty_assessment.get("acceptable_for_context", False))
    fit_message = (
        "Residual uncertainty is acceptable for the stated decision context."
        if acceptable
        else f"Residual uncertainty remains above the accepted level for {decision_context or 'the stated decision context'}."
    )
    payload: Dict[str, Any] = {
        "acceptedLevel": str(uncertainty_assessment.get("accepted_level") or "medium"),
        "overallLevel": str(uncertainty_assessment.get("overall_level") or "high"),
        "acceptableForContext": acceptable,
        "decisionContextFit": fit_message,
        "whatIsNotAddressed": [
            str(item)
            for item in uncertainty_assessment.get("what_is_not_addressed", []) or []
        ],
        "rows": rows,
    }
    actions = _unique(recommended_follow_ups)
    if actions:
        payload["recommendedActions"] = actions
    return payload


def _build_grouping_portable_handoffs(
    status: str,
    identifier: str,
    log_bundle: Dict[str, Any],
    grouping_justification: Dict[str, Any],
    toolbox_meta: Dict[str, Any],
    *,
    artifact_log: Optional[Dict[str, Any]] = None,
    summary_markdown: Optional[str] = None,
    pdf_bytes: Optional[bytes] = None,
) -> Dict[str, Any]:
    inputs = log_bundle.get("inputs", {})
    report_context = grouping_justification.get("report_context", {}) or {}
    target_substance = grouping_justification.get("target_substance") or {}
    identity = _portable_identity_from_summary(target_substance, identifier)

    generated_at = _iso_utc_now()
    workflow_id = _handoff_record_id("oqtgrp")
    handoffs = {
        "oqtWorkflowRecord.v1": _build_portable_workflow_record(
            record_id=workflow_id,
            identifier=identifier,
            search_type=str(inputs.get("search_type") or "name"),
            context=inputs.get("context"),
            primary_entrypoint="build_grouping_justification",
            helper_tools=_unique(
                ["search_chemicals", "canonicalize_structure", "structure_connectivity"]
                + (
                    ["run_profiler", "group_chemicals_by_profiler"]
                    if _unique(inputs.get("profiler_guids", []) or [])
                    else []
                )
                + (
                    ["run_metabolism_simulator"]
                    if _unique(inputs.get("simulator_guids", []) or [])
                    else []
                )
                + (
                    ["run_qsar_model"]
                    if _unique(inputs.get("qsar_guids", []) or [])
                    else []
                )
            ),
            status=status,
            log_bundle=log_bundle,
            toolbox_meta=toolbox_meta,
            assistant_enabled=False,
            generated_at=generated_at,
            root_entity_type="grouping_dossier",
            selected_summary=target_substance,
            artifact_log=artifact_log,
            summary_markdown=summary_markdown,
            pdf_bytes=pdf_bytes,
        )
    }

    if not identity:
        return handoffs

    errors = [str(message) for message in log_bundle.get("errors", []) or []]
    profiler_findings = _build_profiler_findings(
        inputs.get("profiler_guids", []) or [],
        log_bundle.get("profiler_results", []) or [],
        errors,
    )
    uncertainty = grouping_justification.get("uncertainty_assessment", {}) or {}
    endpoint_conclusions = []
    for item in grouping_justification.get("endpoint_justifications", []) or []:
        endpoint_conclusions.append(
            {
                "endpoint": str(item.get("endpoint") or "Unspecified endpoint"),
                "conclusion": str(item.get("conclusion") or "No conclusion recorded."),
                "confidence": str(item.get("confidence") or "low"),
                "residualUncertainty": str(
                    item.get("residual_uncertainty")
                    or uncertainty.get("overall_level")
                    or "high"
                ),
            }
        )

    analogue_entries = []
    rationale = _normalise_scalar(report_context.get("grouping_hypothesis")) or (
        "Resolved source analogue supporting the grouping hypothesis."
    )
    for analogue in grouping_justification.get("source_analogues", []) or []:
        chem_id = _normalise_scalar(analogue.get("chem_id"))
        preferred_name = _normalise_scalar(analogue.get("preferred_name"))
        identifier_value = _normalise_scalar(analogue.get("input_identifier"))
        if not chem_id or not preferred_name or not identifier_value:
            continue
        analogue_entries.append(
            {
                "identifier": identifier_value,
                "preferredName": preferred_name,
                "chemId": chem_id,
                "rationale": rationale,
            }
        )

    limitations: List[str] = []
    if status != "ok":
        limitations.append(f"Grouping dossier completed with status '{status}'.")
    for excluded in grouping_justification.get("excluded_analogues", []) or []:
        analogue_identifier = (
            _normalise_scalar(excluded.get("identifier")) or "Unknown analogue"
        )
        reason = _normalise_scalar(excluded.get("reason")) or "Unspecified exclusion."
        limitations.append(f"{analogue_identifier}: {reason}")
    limitations.extend(grouping_justification.get("recommended_follow_ups", []) or [])
    limitations.extend(errors)

    uncertainty_table = _build_portable_uncertainty_table(
        uncertainty,
        str(report_context.get("decision_context") or "the stated decision context"),
        grouping_justification.get("recommended_follow_ups", []) or [],
    )

    handoffs["oqtReadAcrossSummary.v1"] = {
        "schemaName": "oqtReadAcrossSummary",
        "schemaVersion": "v1",
        "module": "oqt-mcp",
        "chemicalIdentity": identity,
        "groupingMethod": {
            "type": "analogue_read_across",
            "problemFormulation": str(
                report_context.get("problem_formulation") or "Not specified."
            ),
            "decisionContext": str(
                report_context.get("decision_context") or "Not specified."
            ),
            "acceptedUncertaintyLevel": str(
                report_context.get("accepted_uncertainty_level") or "medium"
            ),
            **(
                {"routeOfExposure": str(report_context.get("route_of_exposure"))}
                if report_context.get("route_of_exposure")
                else {}
            ),
        },
        "analogues": analogue_entries,
        "assessmentBoundary": build_read_across_assessment_boundary(),
        "decisionBoundary": build_read_across_decision_boundary(),
        "decisionOwner": build_decision_owner(),
        "supports": build_read_across_supports(),
        "requiredExternalInputs": build_read_across_required_external_inputs(),
        "applicabilityDomain": _build_applicability_domain(grouping_justification),
        "dataMatrix": _build_portable_data_matrix(
            grouping_justification.get("data_matrix", []) or []
        ),
        "uncertaintyTable": uncertainty_table,
        "supportingProfiler": profiler_findings,
        "justification": {
            "hypothesis": rationale,
            "summary": (
                f"Grouping dossier assembled with {len(analogue_entries)} resolved analogue(s); "
                f"overall residual uncertainty is {uncertainty.get('overall_level', 'high')}; "
                "see uncertaintyTable for aspect-level scoring."
            ),
            "residualUncertainty": str(uncertainty.get("overall_level") or "high"),
            "acceptableForContext": bool(
                uncertainty.get("acceptable_for_context", False)
            ),
            "endpointConclusions": endpoint_conclusions,
        },
        "provenance": _build_summary_provenance(
            record_key="recordId",
            record_value=workflow_id,
            generated_at=generated_at,
            toolbox_meta=toolbox_meta,
        ),
        "limitations": _unique(limitations),
    }
    return handoffs


def _normalise_status(value: Optional[str]) -> Optional[str]:
    candidate = _normalise_scalar(value)
    if not candidate:
        return None
    candidate = candidate.lower()
    return candidate if candidate in {"ok", "partial", "not_found", "error"} else None


def _infer_workflow_status(log_bundle: Dict[str, Any]) -> str:
    selected = isinstance(log_bundle.get("selected_chemical"), dict)
    errors = [str(message) for message in log_bundle.get("errors", []) or []]
    if selected:
        return "partial" if errors else "ok"
    if not log_bundle.get("search_results"):
        if any("No Toolbox records found" in message for message in errors):
            return "not_found"
    return "error" if errors else "ok"


def _infer_grouping_status(log_bundle: Dict[str, Any]) -> str:
    target_resolution = log_bundle.get("target_resolution", {}) or {}
    target_status = _normalise_scalar(target_resolution.get("status"))
    errors = [str(message) for message in log_bundle.get("errors", []) or []]
    if target_status and target_status != "resolved":
        return "not_found" if target_status == "not_found" else "error"
    return "partial" if errors else "ok"


def build_portable_handoffs_from_log_bundle(
    log: Dict[str, Any],
    workflow_type: str = "auto",
    status: Optional[str] = None,
) -> Dict[str, Any]:
    requested_type = _normalise_scalar(workflow_type) or "auto"
    if requested_type not in {"auto", "workflow", "grouping"}:
        raise ValueError("workflow_type must be one of: auto, workflow, grouping.")

    source_log = log or {}
    log_bundle = source_log
    if isinstance(source_log.get("mcp_workflow"), dict) and requested_type in {
        "auto",
        "workflow",
    }:
        log_bundle = source_log["mcp_workflow"]

    if requested_type == "auto":
        effective_type = (
            "grouping"
            if isinstance(log_bundle.get("grouping_justification"), dict)
            or "target_resolution" in log_bundle
            else "workflow"
        )
    else:
        effective_type = requested_type

    normalised_status = _normalise_status(status)

    if effective_type == "grouping":
        grouping_justification = log_bundle.get("grouping_justification")
        if not isinstance(grouping_justification, dict):
            raise ValueError(
                "Grouping logs must contain a 'grouping_justification' object."
            )
        identifier = (
            _normalise_scalar(log_bundle.get("identifier"))
            or _normalise_scalar(
                grouping_justification.get("report_context", {}).get("identifier")
            )
            or _normalise_scalar(log_bundle.get("inputs", {}).get("identifier"))
            or "unknown"
        )
        inferred_status = normalised_status or _infer_grouping_status(log_bundle)
        return {
            "workflow_type": effective_type,
            "status": inferred_status,
            "portable_handoffs": _build_grouping_portable_handoffs(
                inferred_status,
                identifier,
                log_bundle,
                grouping_justification,
                log_bundle.get("toolbox", {}) or {},
                artifact_log=source_log if isinstance(source_log, dict) else log_bundle,
                summary_markdown=_normalise_scalar(
                    (source_log or {}).get("final_report")
                    if isinstance(source_log, dict)
                    else None
                )
                or _normalise_scalar(log_bundle.get("final_report")),
            ),
        }

    identifier = (
        _normalise_scalar(log_bundle.get("identifier"))
        or _normalise_scalar(log_bundle.get("inputs", {}).get("identifier"))
        or "unknown"
    )
    inferred_status = normalised_status or _infer_workflow_status(log_bundle)
    assistant_enabled = isinstance(source_log.get("assistant_session"), dict)
    return {
        "workflow_type": effective_type,
        "status": inferred_status,
        "portable_handoffs": _build_workflow_portable_handoffs(
            inferred_status,
            log_bundle,
            log_bundle.get("toolbox", {}) or {},
            assistant_enabled=assistant_enabled,
            artifact_log=source_log if isinstance(source_log, dict) else log_bundle,
            summary_markdown=_normalise_scalar(
                (source_log or {}).get("final_report")
                if isinstance(source_log, dict)
                else None
            )
            or _normalise_scalar(log_bundle.get("final_report")),
        ),
    }


async def run_oqt_multiagent_workflow(
    identifier: str,
    search_type: str,
    context: Optional[str],
    profiler_guids: List[str],
    qsar_mode: str,
    qsar_guids: List[str],
    simulator_guids: List[str],
    llm_provider: Optional[str],
    llm_model: Optional[str],
    llm_api_key: Optional[str],
    require_human_review: bool = False,
    workflow_id: Optional[str] = None,
    checkpoint_approvals: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    profiler_guids = _unique(profiler_guids)
    simulator_guids = _unique(simulator_guids)
    qsar_guids = _unique(qsar_guids)
    assistant_config = oqt_assistant.resolve_assistant_config(
        provider_override=llm_provider,
        model_override=llm_model,
        api_key_override=llm_api_key,
    )
    assistant_result = None
    assistant_error: Optional[str] = None
    assistant_meta: Optional[Dict[str, Any]] = None

    log_bundle: Dict[str, Any] = {
        "identifier": identifier,
        "inputs": {
            "identifier": identifier,
            "search_type": search_type,
            "context": context,
            "profiler_guids": profiler_guids,
            "qsar_mode": qsar_mode,
            "qsar_guids": qsar_guids,
            "simulator_guids": simulator_guids,
            "llm_provider": llm_provider,
            "llm_model": llm_model,
        },
        "generated_by": "O-QT MCP Server",
        "search_results": [],
        "selected_chemical": None,
        "profiler_results": [],
        "simulator_results": [],
        "qsar_results": [],
        "errors": [],
    }

    summary_lines: List[str] = []
    status = "ok"
    identifier_display = identifier.strip()
    toolbox_calls: List[Dict[str, Any]] = []
    workflow_id = workflow_id or str(uuid4())
    checkpoint_approvals = checkpoint_approvals or []

    # Apply any supplied checkpoint approvals before proceeding
    for approval in checkpoint_approvals:
        cid = approval.get("checkpoint_id")
        decision_str = approval.get("decision", "approved")
        if cid:
            try:
                decision = ReviewDecision(decision_str.lower())
                review_orchestrator.submit_review(
                    cid, "mcp_user", decision, comments=approval.get("comments")
                )
            except ValueError as exc:
                log.warning("Invalid checkpoint approval %s: %s", cid, exc)

    if _looks_like_uuid(identifier_display):
        primary = {"ChemId": identifier_display, "Names": [identifier_display]}
        hits = [primary]
        chem_id = identifier_display
        log_bundle["search_results"] = hits
    else:
        try:
            search_payload, search_meta = await _invoke_with_meta(
                qsar_client.search_chemicals, identifier_display, search_type
            )
        except QsarClientError as exc:
            message = f"Search failed: {exc}"
            log.error(message)
            log_bundle["errors"].append(message)
            status = "error"
            summary_lines.append(
                f"* Unable to resolve `{identifier_display}` in the Toolbox."
            )
            return _build_workflow_response(
                status, summary_lines, log_bundle, _aggregate_calls(toolbox_calls)
            )

        hits = _coerce_hits(search_payload)
        log_bundle["search_results"] = hits
        search_entry = _format_meta("workflow/search", search_meta)
        if search_entry:
            toolbox_calls.append(search_entry)

        if not hits:
            status = "not_found"
            message = f"No Toolbox records found for '{identifier_display}'."
            log.warning(message)
            log_bundle["errors"].append(message)
            summary_lines.append(
                f"* No Toolbox records matched `{identifier_display}`."
            )
            return _build_workflow_response(
                status, summary_lines, log_bundle, _aggregate_calls(toolbox_calls)
            )

        primary = next((hit for hit in hits if hit.get("ChemId")), hits[0])
        chem_id = primary.get("ChemId")
    log_bundle["selected_chemical"] = primary

    cas_number = primary.get("Cas")
    cas_display = str(cas_number) if cas_number not in (None, "") else "n/a"
    names = primary.get("Names") or []
    preferred_name = names[0] if names else identifier_display

    summary_lines.append(
        f"* Resolved `{identifier_display}` to **{preferred_name}** "
        f"(chemId `{chem_id}` · CAS {cas_display})."
    )

    if require_human_review:
        review_orchestrator.create_checkpoint_if_missing(
            workflow_id=workflow_id,
            step="chemical_identity",
            data={
                "input_identifier": identifier,
                "resolved_name": preferred_name,
                "chem_id": chem_id,
                "cas": cas_display,
                "search_type_used": search_type,
            },
        )

    profiler_provenance_cache: Dict[str, Dict[str, Any] | None] = {}
    simulator_provenance_cache: Dict[str, Dict[str, Any] | None] = {}
    model_provenance_cache: Dict[str, Dict[str, Any] | None] = {}

    profiler_results: List[Dict[str, Any]] = []
    for profiler_guid in profiler_guids:
        try:
            payload, profiler_meta = await qsar_client.profile_with_profiler(
                profiler_guid, chem_id, None, with_meta=True
            )
            profiler_provenance, profiler_info_entry = await _fetch_profiler_provenance(
                profiler_guid, profiler_provenance_cache
            )
            profiler_result = {"profiler_guid": profiler_guid, "result": payload}
            if profiler_provenance:
                profiler_result["profiler_provenance"] = profiler_provenance
            profiler_results.append(profiler_result)
            entry = _format_meta(
                "profiling/execute", profiler_meta, profiler_guid=profiler_guid
            )
            if entry:
                toolbox_calls.append(entry)
            if profiler_info_entry:
                toolbox_calls.append(profiler_info_entry)
        except QsarClientError as exc:
            message = f"Profiler {profiler_guid} failed: {exc}"
            log.warning(message)
            log_bundle["errors"].append(message)

    if profiler_results:
        summary_lines.append(
            f"* Executed {len(profiler_results)} profiler(s) "
            f"for chemId `{chem_id}`."
        )
    elif profiler_guids:
        summary_lines.append(
            "* Profiler execution requested, but no results were returned."
        )

    simulator_results: List[Dict[str, Any]] = []
    for simulator_guid in simulator_guids:
        try:
            payload, simulator_meta = await qsar_client.simulate_metabolites_for_chem(
                simulator_guid, chem_id, with_meta=True
            )
            simulator_provenance, simulator_info_entry = (
                await _fetch_simulator_provenance(
                    simulator_guid, simulator_provenance_cache
                )
            )
            simulator_result = {"simulator_guid": simulator_guid, "result": payload}
            if simulator_provenance:
                simulator_result["simulator_provenance"] = simulator_provenance
            simulator_results.append(simulator_result)
            entry = _format_meta(
                "metabolism/simulate",
                simulator_meta,
                simulator_guid=simulator_guid,
            )
            if entry:
                toolbox_calls.append(entry)
            if simulator_info_entry:
                toolbox_calls.append(simulator_info_entry)
        except QsarClientError as exc:
            message = f"Metabolism simulator {simulator_guid} failed: {exc}"
            log.warning(message)
            log_bundle["errors"].append(message)

    if simulator_results:
        summary_lines.append(
            f"* Generated metabolites with {len(simulator_results)} simulator(s)."
        )
    elif simulator_guids:
        summary_lines.append(
            "* Metabolism simulation requested, but no simulator results were returned."
        )

    qsar_results: List[Dict[str, Any]] = []
    effective_qsar_guids = qsar_guids

    if not effective_qsar_guids and qsar_mode not in {"none", ""}:
        summary_lines.append(
            "* QSAR models were not executed automatically. Provide `qsar_guids` "
            "to run specific models in the workflow."
        )

    for qsar_guid in effective_qsar_guids:
        try:
            prediction, apply_meta = await qsar_client.apply_qsar_model(
                qsar_guid, chem_id, with_meta=True
            )
            domain, domain_meta = await qsar_client.get_qsar_domain(
                qsar_guid, chem_id, with_meta=True
            )
            model_provenance, model_info_entry = await _fetch_model_provenance(
                qsar_guid, model_provenance_cache
            )
            # Light-weight AD check (OQT-01)
            domain_value = ""
            if isinstance(domain, dict):
                domain_value = domain.get("DomainResult") or domain.get("Domain") or ""
            elif isinstance(domain, str):
                domain_value = domain
            domain_normalized = (
                str(domain_value).strip().replace(" ", "").replace("-", "").lower()
            )
            ad_warning = domain_normalized in {"outofdomain", "out_of_domain"}

            qsar_result = {
                "qsar_guid": qsar_guid,
                "prediction": prediction,
                "domain": domain,
                "ad_status": (
                    "out_of_domain"
                    if ad_warning
                    else (
                        "in_domain"
                        if domain_normalized
                        in {"indomain", "in_domain", "insideapplicabilitydomain"}
                        else "unknown"
                    )
                ),
                "ad_warning": ad_warning,
            }
            if ad_warning:
                qsar_result["ad_recommendation"] = (
                    "This prediction is outside the model's applicability domain. "
                    "Treat with caution and consider experimental validation or read-across."
                )
            if model_provenance:
                qsar_result["model_provenance"] = model_provenance
            qsar_results.append(qsar_result)
            entry_apply = _format_meta("qsar/apply", apply_meta, qsar_guid=qsar_guid)
            entry_domain = _format_meta("qsar/domain", domain_meta, qsar_guid=qsar_guid)
            if entry_apply:
                toolbox_calls.append(entry_apply)
            if entry_domain:
                toolbox_calls.append(entry_domain)
            if model_info_entry:
                toolbox_calls.append(model_info_entry)
        except QsarClientError as exc:
            message = f"QSAR model {qsar_guid} failed: {exc}"
            log.warning(message)
            log_bundle["errors"].append(message)

    if qsar_results:
        summary_lines.append(
            f"* Completed {len(qsar_results)} QSAR model run(s) for chemId `{chem_id}`."
        )
        ad_warnings = [r for r in qsar_results if r.get("ad_warning")]
        if ad_warnings:
            summary_lines.append(
                f"* ⚠️ {len(ad_warnings)} model run(s) reported OUT OF APPLICABILITY DOMAIN."
            )
            if require_human_review:
                review_orchestrator.create_checkpoint_if_missing(
                    workflow_id=workflow_id,
                    step="ad_assessment",
                    data={
                        "chemical_name": preferred_name,
                        "chem_id": chem_id,
                        "ad_warning_count": len(ad_warnings),
                        "ad_models": [
                            {"guid": r["qsar_guid"], "ad_status": r.get("ad_status")}
                            for r in ad_warnings
                        ],
                    },
                )

    if context:
        summary_lines.append(f"* Context: {context}")

    log_bundle["profiler_results"] = profiler_results
    log_bundle["simulator_results"] = simulator_results
    log_bundle["qsar_results"] = qsar_results
    log_bundle["selected_name"] = preferred_name

    if log_bundle["errors"] and status == "ok":
        status = "partial"

    toolbox_meta = _aggregate_calls(toolbox_calls)
    if toolbox_meta["calls"]:
        log_bundle["toolbox"] = toolbox_meta
        # Capture upstream API version / timestamp from any call that has it (REG-05)
        api_versions = None
        server_date = None
        for call in toolbox_meta["calls"]:
            if isinstance(call, dict):
                if not api_versions and call.get("api_versions"):
                    api_versions = call["api_versions"]
                if not server_date and call.get("server_date"):
                    server_date = call["server_date"]
        if api_versions or server_date:
            log_bundle["toolbox_provenance"] = {
                "api_versions": api_versions,
                "server_date": server_date,
            }

    # Final review checkpoint before artifact generation (OQT-02)
    pending = review_orchestrator.pending_checkpoints(workflow_id)
    if require_human_review and pending:
        review_orchestrator.create_checkpoint_if_missing(
            workflow_id=workflow_id,
            step="final_report",
            data={
                "preview_summary": "\n".join(summary_lines),
                "predictions_count": len(qsar_results),
                "warnings_count": len([r for r in qsar_results if r.get("ad_warning")]),
            },
        )
        # Re-check pending after adding final checkpoint
        pending = review_orchestrator.pending_checkpoints(workflow_id)
        return _build_review_required_response(
            workflow_id, summary_lines, log_bundle, toolbox_meta, pending
        )

    if assistant_config:
        default_context = (
            context or "Publication-grade hazard assessment (MCP workflow)"
        )
        include_qsar = bool(qsar_guids) or qsar_mode not in {"none", "", "off", "skip"}
        fast_qsar = qsar_mode in {"recommended", "auto"} and not qsar_guids
        qsar_limit = len(qsar_guids) if qsar_guids else None
        try:
            assistant_base_url = qsar_client.base_url.rstrip("/")
            if not assistant_base_url.endswith("/api/v6"):
                assistant_base_url = f"{assistant_base_url}/api/v6"

            assistant_result = await oqt_assistant.generate_assistant_output(
                identifier=identifier,
                search_type=search_type,
                context=default_context,
                qsar_base_url=assistant_base_url,
                config=assistant_config,
                simulator_guids=simulator_guids or None,
                include_qsar=include_qsar,
                selected_qsar_guids=qsar_guids or None,
                fast_qsar=fast_qsar,
                qsar_limit=qsar_limit,
                exclude_qsar_guids=None,
                exclude_qsar_contains=None,
                qsar_model_timeout_s=None,
                qsar_total_budget_s=None,
                enable_metabolism=bool(simulator_guids),
            )
            assistant_meta = {
                "provider": assistant_config.provider,
                "model": assistant_config.model,
                "duration_s": round(assistant_result.duration_s, 3),
            }
        except (
            Exception
        ) as exc:  # pragma: no cover - requires optional assistant install
            assistant_error = str(exc)
            log.warning(
                "Assistant workflow failed; falling back to deterministic summary: %s",
                exc,
            )
        else:
            pdf_bytes = assistant_result.pdf_bytes
            if not pdf_bytes:
                try:
                    pdf_buffer = generate_pdf_report(assistant_result.log_bundle)
                    pdf_bytes = pdf_buffer.getvalue()
                except Exception as pdf_exc:  # pragma: no cover
                    log.warning("Assistant PDF regeneration failed: %s", pdf_exc)
                    pdf_bytes = b""

            response = {
                "status": "ok",
                "identifier": assistant_result.log_bundle.get("identifier", identifier),
                "summary_markdown": assistant_result.final_report,
                "pdf_report_base64": base64.b64encode(pdf_bytes).decode("utf-8"),
            }
            combined_log = copy.deepcopy(assistant_result.log_bundle)
            combined_log["assistant_session"] = {
                "provider": assistant_config.provider,
                "model": assistant_config.model,
                "duration_s": round(assistant_result.duration_s, 3),
                "specialist_outputs": assistant_result.specialist_sections,
            }
            combined_log["mcp_workflow"] = log_bundle
            response["log_json"] = combined_log
            if toolbox_meta.get("calls"):
                response["toolbox"] = toolbox_meta
            response["portable_handoffs"] = _build_workflow_portable_handoffs(
                "ok",
                log_bundle,
                toolbox_meta,
                assistant_enabled=True,
                artifact_log=combined_log,
                summary_markdown=assistant_result.final_report,
                pdf_bytes=pdf_bytes,
            )
            response["assistant"] = {"enabled": True, **assistant_meta}
            return response

    if assistant_config and assistant_error:
        summary_lines.append(f"* Assistant workflow unavailable: {assistant_error}.")
        log_bundle.setdefault("assistant", {})["error"] = assistant_error

    return _build_workflow_response(status, summary_lines, log_bundle, toolbox_meta)


def _build_review_required_response(
    workflow_id: str,
    summary_lines: List[str],
    log_bundle: Dict[str, Any],
    toolbox_meta: Dict[str, Any],
    pending_checkpoints: List[Any],
) -> Dict[str, Any]:
    summary_markdown = "\n".join(
        ["## QSAR Workflow Summary", ""]
        + summary_lines
        + ["", "*Workflow paused for human review.*"]
    )
    log_bundle["final_report"] = summary_markdown
    response = {
        "status": "review_required",
        "identifier": log_bundle["inputs"]["identifier"],
        "summary_markdown": summary_markdown,
        "log_json": log_bundle,
        "workflow_id": workflow_id,
        "review_checkpoints": [cp.to_dict() for cp in pending_checkpoints],
    }
    if toolbox_meta.get("calls"):
        response["toolbox"] = toolbox_meta
    response["portable_handoffs"] = _build_workflow_portable_handoffs(
        "review_required",
        log_bundle,
        toolbox_meta,
        artifact_log=log_bundle,
        summary_markdown=summary_markdown,
        pdf_bytes=b"",
    )
    return response


def _build_workflow_response(
    status: str,
    summary_lines: List[str],
    log_bundle: Dict[str, Any],
    toolbox_meta: Dict[str, Any],
) -> Dict[str, Any]:
    if not summary_lines:
        summary_lines = ["* No workflow actions were completed."]

    summary_markdown = "\n".join(["## QSAR Workflow Summary", ""] + summary_lines)
    log_bundle["final_report"] = summary_markdown

    pdf_buffer = generate_pdf_report(log_bundle)
    if hasattr(pdf_buffer, "getvalue"):
        pdf_bytes = pdf_buffer.getvalue()
    elif isinstance(pdf_buffer, (bytes, bytearray, memoryview)):
        pdf_bytes = bytes(pdf_buffer)
    else:  # pragma: no cover - safeguard for unexpected implementations
        raise TypeError("Unexpected PDF payload produced by generate_pdf_report")

    pdf_report_base64 = base64.b64encode(pdf_bytes).decode("utf-8")

    qsar_results = log_bundle.get("qsar_results") or []
    qsar_guids_executed = [
        r["qsar_guid"]
        for r in qsar_results
        if isinstance(r, dict) and r.get("qsar_guid")
    ]

    response = {
        "status": status,
        "identifier": log_bundle["inputs"]["identifier"],
        "summary_markdown": summary_markdown,
        "log_json": log_bundle,
        "pdf_report_base64": pdf_report_base64,
        "portable_handoffs": _build_workflow_portable_handoffs(
            status,
            log_bundle,
            toolbox_meta,
            artifact_log=log_bundle,
            summary_markdown=summary_markdown,
            pdf_bytes=pdf_bytes,
        ),
    }
    if qsar_guids_executed:
        response["qsar_models_executed"] = qsar_guids_executed
    if toolbox_meta.get("calls"):
        response["toolbox"] = toolbox_meta
    return response


def _build_similarity_assessment(
    source_analogues: List[Dict[str, Any]],
    structure_comparison: Dict[str, Any],
    physicochemical_comparison: Dict[str, Any],
    profiler_results: List[Dict[str, Any]],
    profiler_groupings: List[Dict[str, Any]],
    simulator_results: List[Dict[str, Any]],
    qsar_results: List[Dict[str, Any]],
    grouping_hypothesis: str,
) -> Dict[str, Dict[str, Any]]:
    analogue_count = len(source_analogues)
    structure_summary = structure_comparison.get("summary", {})
    physchem_summary = physicochemical_comparison.get("summary", {})
    target_profiles = sum(
        1 for item in profiler_results if item.get("subject_role") == "target"
    )
    source_profiles = sum(
        1 for item in profiler_results if item.get("subject_role") == "source_analogue"
    )
    target_simulators = sum(
        1 for item in simulator_results if item.get("subject_role") == "target"
    )
    source_simulators = sum(
        1 for item in simulator_results if item.get("subject_role") == "source_analogue"
    )

    return {
        "structural_similarity": {
            "status": (
                "assessed"
                if structure_summary.get("assessed_pairs")
                else (
                    "limited"
                    if analogue_count
                    and structure_comparison.get("target", {}).get("input_smiles")
                    else "not_assessed"
                )
            ),
            "data_quality": (
                "medium" if structure_summary.get("assessed_pairs") else "low"
            ),
            "strength_of_evidence": (
                "medium" if structure_summary.get("assessed_pairs") else "low"
            ),
            "comments": (
                f"Assessed {structure_summary.get('assessed_pairs', 0)} target/source pair(s); "
                f"{structure_summary.get('canonical_exact_matches', 0)} canonical SMILES exact match(es) and "
                f"{structure_summary.get('connectivity_exact_matches', 0)} connectivity exact match(es)."
                if structure_summary.get("assessed_pairs")
                else (
                    "Source analogues were resolved, but comparable structure signatures were not available for the assessed pairs."
                    if analogue_count
                    else "No source analogues were provided, so structural similarity could not be documented."
                )
            ),
        },
        "physicochemical_similarity": {
            "status": (
                "assessed"
                if physchem_summary.get("assessed_pairs")
                else (
                    "limited"
                    if analogue_count
                    and physicochemical_comparison.get("target_descriptors")
                    else "not_assessed"
                )
            ),
            "data_quality": (
                "medium" if physchem_summary.get("shared_descriptor_count") else "low"
            ),
            "strength_of_evidence": (
                "medium" if physchem_summary.get("shared_descriptor_count") else "low"
            ),
            "comments": (
                f"Compared {physchem_summary.get('shared_descriptor_count', 0)} shared physicochemical descriptor(s) across "
                f"{physchem_summary.get('assessed_pairs', 0)} target/source pair(s)."
                if physchem_summary.get("shared_descriptor_count")
                else (
                    "Target and source substances were resolved, but no overlapping physicochemical descriptors were exposed in the available records."
                    if analogue_count
                    else "No source analogues were provided, so physicochemical similarity could not be documented."
                )
            ),
        },
        "reactivity_profile_similarity": {
            "status": (
                "assessed"
                if target_profiles and source_profiles
                else "limited" if target_profiles else "not_assessed"
            ),
            "data_quality": "medium" if target_profiles else "low",
            "strength_of_evidence": (
                "medium" if target_profiles and source_profiles else "low"
            ),
            "comments": (
                f"Profiler evidence was gathered under the hypothesis: {grouping_hypothesis}"
                if target_profiles
                else "No profiler evidence was collected for the selected substances."
            ),
        },
        "adme_tk_similarity": {
            "status": (
                "assessed"
                if target_simulators and source_simulators
                else "limited" if target_simulators else "not_assessed"
            ),
            "data_quality": "medium" if target_simulators else "low",
            "strength_of_evidence": (
                "medium" if target_simulators and source_simulators else "low"
            ),
            "comments": (
                "Metabolism simulator output is available for the target and at least one source analogue."
                if target_simulators and source_simulators
                else (
                    "Metabolism simulation is only available for the target substance."
                    if target_simulators
                    else "No metabolism simulator evidence was collected."
                )
            ),
        },
        "bioactivity_similarity": {
            "status": "limited" if profiler_results or qsar_results else "not_assessed",
            "data_quality": "medium" if profiler_results or qsar_results else "low",
            "strength_of_evidence": "low",
            "comments": (
                "Bioactivity support is limited to profiler and QSAR outputs collected in this dossier."
                if profiler_results or qsar_results
                else "No bioactivity-oriented evidence was collected."
            ),
        },
        "mechanistic_similarity": {
            "status": (
                "limited" if profiler_groupings or simulator_results else "not_assessed"
            ),
            "data_quality": (
                "medium" if profiler_groupings or simulator_results else "low"
            ),
            "strength_of_evidence": "medium" if profiler_groupings else "low",
            "comments": (
                "Mechanistic support is based on profiler grouping and/or metabolism evidence."
                if profiler_groupings or simulator_results
                else "No mechanistic support was collected."
            ),
        },
        "toxicological_profile_similarity": {
            "status": "limited" if qsar_results else "not_assessed",
            "data_quality": "medium" if qsar_results else "low",
            "strength_of_evidence": "low",
            "comments": (
                "Target-side QSAR predictions were included as supporting evidence."
                if qsar_results
                else "No QSAR model support was included in this dossier."
            ),
        },
    }


def _uncertainty_from_context(context: Dict[str, Any]) -> str:
    if context.get("status") == "not_assessed":
        return "high"
    if context.get("strength_of_evidence") == "high":
        return "low"
    if context.get("strength_of_evidence") == "medium":
        return "medium"
    return "high"


def _build_uncertainty_assessment(
    similarity_assessment: Dict[str, Dict[str, Any]],
    accepted_uncertainty_level: str,
    source_analogues: List[Dict[str, Any]],
) -> Dict[str, Any]:
    ranks = {"low": 1, "medium": 2, "high": 3}
    rows: List[Dict[str, Any]] = []
    missing_aspects: List[str] = []
    scores: List[int] = []

    for aspect, context in similarity_assessment.items():
        uncertainty = _uncertainty_from_context(context)
        rows.append(
            {
                "aspect": aspect,
                "data_quality": context.get("data_quality", "low"),
                "strength_of_evidence": context.get("strength_of_evidence", "low"),
                "uncertainty": uncertainty,
                "comments": context.get("comments", ""),
            }
        )
        if context.get("status") == "not_assessed":
            missing_aspects.append(aspect)
        scores.append(ranks[uncertainty])

    overall_level = "high"
    if scores:
        average = sum(scores) / len(scores)
        if average <= 1.4:
            overall_level = "low"
        elif average <= 2.2:
            overall_level = "medium"
    if not source_analogues:
        overall_level = "high"

    accepted_level = (
        accepted_uncertainty_level if accepted_uncertainty_level in ranks else "medium"
    )
    return {
        "accepted_level": accepted_level,
        "overall_level": overall_level,
        "acceptable_for_context": ranks[overall_level] <= ranks[accepted_level],
        "what_is_not_addressed": missing_aspects,
        "assessment_table": rows,
    }


def _build_endpoint_justifications(
    endpoints: List[str],
    source_analogues: List[Dict[str, Any]],
    similarity_assessment: Dict[str, Dict[str, Any]],
    uncertainty_assessment: Dict[str, Any],
    grouping_hypothesis: str,
    decision_context: str,
    route_of_exposure: Optional[str],
    profiler_guids: List[str],
    simulator_guids: List[str],
    qsar_guids: List[str],
) -> List[Dict[str, Any]]:
    source_names = [item.get("preferred_name", "Unknown") for item in source_analogues]
    supported_contexts = [
        aspect
        for aspect, value in similarity_assessment.items()
        if value.get("status") != "not_assessed"
    ]
    overall_uncertainty = uncertainty_assessment.get("overall_level", "high")
    confidence = {"low": "high", "medium": "medium", "high": "low"}[overall_uncertainty]

    justifications: List[Dict[str, Any]] = []
    for endpoint in endpoints:
        if source_analogues:
            strategy = "read_across_with_weight_of_evidence"
            conclusion = (
                f"Provisional analogue justification assembled for {endpoint}."
                if uncertainty_assessment.get("acceptable_for_context")
                else f"Analogue dossier assembled for {endpoint}, but residual uncertainty remains above the accepted level."
            )
        else:
            strategy = "weight_of_evidence_preparation_only"
            conclusion = f"No source analogue set was resolved for {endpoint}; additional analogue selection is required before read-across can be defended."

        support_bits = [
            (
                f"{len(source_analogues)} source analogue(s)"
                if source_analogues
                else "no resolved source analogues"
            ),
            (
                f"{len(profiler_guids)} profiler(s)"
                if profiler_guids
                else "no profiler evidence"
            ),
            (
                f"{len(simulator_guids)} simulator(s)"
                if simulator_guids
                else "no metabolism evidence"
            ),
            f"{len(qsar_guids)} QSAR model(s)" if qsar_guids else "no QSAR evidence",
        ]
        rationale = (
            f"Decision context: {decision_context}. Grouping hypothesis: {grouping_hypothesis}. "
            f"The dossier currently includes {', '.join(support_bits)}. "
            f"Supported similarity contexts: {', '.join(supported_contexts) if supported_contexts else 'none documented'}."
        )

        payload = {
            "endpoint": endpoint,
            "strategy": strategy,
            "conclusion": conclusion,
            "confidence": confidence,
            "residual_uncertainty": overall_uncertainty,
            "supporting_similarity_contexts": supported_contexts,
            "source_analogues": source_names,
            "decision_context": decision_context,
            "rationale": rationale,
        }
        if route_of_exposure:
            payload["route_of_exposure"] = route_of_exposure
        justifications.append(payload)

    return justifications


def _build_recommended_follow_ups(
    source_analogues: List[Dict[str, Any]],
    similarity_assessment: Dict[str, Dict[str, Any]],
    uncertainty_assessment: Dict[str, Any],
    profiler_guids: List[str],
    simulator_guids: List[str],
    qsar_guids: List[str],
) -> List[str]:
    follow_ups: List[str] = []
    if not source_analogues:
        follow_ups.append(
            "Provide candidate source analogues or category members so the dossier can move from exploratory evidence collection to an actual read-across case."
        )
    if similarity_assessment["structural_similarity"]["status"] != "assessed":
        follow_ups.append(
            "Add richer structure-distance metrics or calculator-backed physicochemical descriptors if you want stronger analogue adequacy support than the current record-derived comparisons."
        )
    if not profiler_guids:
        follow_ups.append(
            "Run at least one endpoint-relevant profiler to strengthen the reactivity and mechanistic rationale."
        )
    if not simulator_guids:
        follow_ups.append(
            "Add metabolism simulator evidence when ADME/TK or metabolite similarity is part of the grouping hypothesis."
        )
    if not qsar_guids:
        follow_ups.append(
            "Attach endpoint-specific QSAR model runs or empirical study data to reinforce toxicological support."
        )
    if not uncertainty_assessment.get("acceptable_for_context"):
        follow_ups.append(
            "Residual uncertainty is above the accepted level; either collect bridging evidence or narrow the decision context."
        )
    return _unique(follow_ups)


def _build_grouping_markdown(
    report_context: Dict[str, Any],
    target_substance: Dict[str, Any],
    source_analogues: List[Dict[str, Any]],
    excluded_analogues: List[Dict[str, Any]],
    structure_comparison: Dict[str, Any],
    physicochemical_comparison: Dict[str, Any],
    evidence_matrix: List[Dict[str, Any]],
    endpoint_justifications: List[Dict[str, Any]],
    uncertainty_assessment: Dict[str, Any],
    recommended_follow_ups: List[str],
) -> str:
    lines = ["## OECD Grouping Justification", ""]
    lines.append(f"* Decision context: {report_context['decision_context']}")
    lines.append(f"* Problem formulation: {report_context['problem_formulation']}")
    lines.append(f"* Grouping hypothesis: {report_context['grouping_hypothesis']}")
    lines.append(f"* Endpoints: {', '.join(report_context['endpoints'])}")
    if report_context.get("route_of_exposure"):
        lines.append(f"* Route of exposure: {report_context['route_of_exposure']}")
    if report_context.get("context"):
        lines.append(f"* Additional context: {report_context['context']}")

    lines.extend(["", "### Target and Analogues", ""])
    cas_value = target_substance.get("cas") or "n/a"
    lines.append(
        f"* Target: **{target_substance.get('preferred_name', report_context['identifier'])}** (chemId `{target_substance.get('chem_id')}` · CAS {cas_value})"
    )
    if source_analogues:
        analogue_text = ", ".join(
            f"{item.get('preferred_name')} (chemId `{item.get('chem_id')}`)"
            for item in source_analogues
        )
        lines.append(f"* Resolved source analogues: {analogue_text}")
    else:
        lines.append("* Resolved source analogues: none")
    if excluded_analogues:
        excluded_text = ", ".join(
            f"{item.get('identifier')} ({item.get('reason')})"
            for item in excluded_analogues
        )
        lines.append(f"* Excluded or unresolved analogues: {excluded_text}")

    lines.extend(["", "### Similarity Comparison", ""])
    structure_summary = structure_comparison.get("summary", {})
    physchem_summary = physicochemical_comparison.get("summary", {})
    lines.append(
        f"* Structural pairs assessed: {structure_summary.get('assessed_pairs', 0)}; canonical exact matches: {structure_summary.get('canonical_exact_matches', 0)}; connectivity exact matches: {structure_summary.get('connectivity_exact_matches', 0)}."
    )
    lines.append(
        f"* Physicochemical descriptor comparisons: {physchem_summary.get('shared_descriptor_count', 0)} across {physchem_summary.get('assessed_pairs', 0)} pair(s)."
    )

    lines.extend(["", "### Evidence", ""])
    lines.append(f"* Evidence rows captured: {len(evidence_matrix)}")
    lines.append(
        f"* Overall residual uncertainty: **{uncertainty_assessment.get('overall_level', 'high')}**"
    )
    lines.append(
        f"* Acceptable for stated purpose: **{'yes' if uncertainty_assessment.get('acceptable_for_context') else 'no'}**"
    )

    lines.extend(["", "### Endpoint Conclusions", ""])
    for endpoint in endpoint_justifications:
        lines.append(
            f"* {endpoint['endpoint']}: {endpoint['conclusion']} Confidence: {endpoint['confidence']}; residual uncertainty: {endpoint['residual_uncertainty']}."
        )

    if recommended_follow_ups:
        lines.extend(["", "### Recommended Follow-up", ""])
        for item in recommended_follow_ups:
            lines.append(f"* {item}")

    return "\n".join(lines)


def _build_grouping_response(
    status: str,
    identifier: str,
    summary_markdown: str,
    log_bundle: Dict[str, Any],
    grouping_justification: Dict[str, Any],
    toolbox_meta: Dict[str, Any],
) -> Dict[str, Any]:
    log_bundle["final_report"] = summary_markdown
    log_bundle["grouping_justification"] = grouping_justification

    pdf_buffer = generate_pdf_report(log_bundle)
    if hasattr(pdf_buffer, "getvalue"):
        pdf_bytes = pdf_buffer.getvalue()
    elif isinstance(pdf_buffer, (bytes, bytearray, memoryview)):
        pdf_bytes = bytes(pdf_buffer)
    else:  # pragma: no cover - safeguard for unexpected implementations
        raise TypeError("Unexpected PDF payload produced by generate_pdf_report")

    response = {
        "status": status,
        "identifier": identifier,
        "summary_markdown": summary_markdown,
        "grouping_justification": grouping_justification,
        "log_json": log_bundle,
        "pdf_report_base64": base64.b64encode(pdf_bytes).decode("utf-8"),
        "portable_handoffs": _build_grouping_portable_handoffs(
            status,
            identifier,
            log_bundle,
            grouping_justification,
            toolbox_meta,
            artifact_log=log_bundle,
            summary_markdown=summary_markdown,
            pdf_bytes=pdf_bytes,
        ),
    }
    if toolbox_meta.get("calls"):
        response["toolbox"] = toolbox_meta
    return response


async def build_grouping_justification(
    identifier: str,
    search_type: str,
    problem_formulation: str,
    decision_context: str,
    endpoints: List[str],
    route_of_exposure: Optional[str],
    grouping_hypothesis: str,
    analogue_identifiers: List[str],
    analogue_search_type: str,
    profiler_guids: List[str],
    simulator_guids: List[str],
    qsar_guids: List[str],
    accepted_uncertainty_level: str,
    context: Optional[str],
) -> Dict[str, Any]:
    endpoints = _unique(endpoints)
    analogue_identifiers = _unique(analogue_identifiers)
    profiler_guids = _unique(profiler_guids)
    simulator_guids = _unique(simulator_guids)
    qsar_guids = _unique(qsar_guids)

    toolbox_calls: List[Dict[str, Any]] = []
    log_bundle: Dict[str, Any] = {
        "identifier": identifier,
        "inputs": {
            "identifier": identifier,
            "search_type": search_type,
            "problem_formulation": problem_formulation,
            "decision_context": decision_context,
            "endpoints": endpoints,
            "route_of_exposure": route_of_exposure,
            "grouping_hypothesis": grouping_hypothesis,
            "analogue_identifiers": analogue_identifiers,
            "analogue_search_type": analogue_search_type,
            "profiler_guids": profiler_guids,
            "simulator_guids": simulator_guids,
            "qsar_guids": qsar_guids,
            "accepted_uncertainty_level": accepted_uncertainty_level,
            "context": context,
        },
        "generated_by": "O-QT MCP Server",
        "target_resolution": None,
        "analogue_resolutions": [],
        "excluded_analogues": [],
        "structure_comparison": {},
        "physicochemical_comparison": {},
        "profiler_results": [],
        "profiler_groupings": [],
        "simulator_results": [],
        "qsar_results": [],
        "data_matrix": [],
        "errors": [],
    }

    target_resolution = await _resolve_chemical(
        identifier, search_type, "grouping/target", toolbox_calls
    )
    log_bundle["target_resolution"] = target_resolution

    if target_resolution["status"] != "resolved" or not target_resolution["summary"]:
        message = target_resolution.get("error") or f"Unable to resolve '{identifier}'."
        log.warning(message)
        log_bundle["errors"].append(message)
        summary_markdown = "\n".join(
            [
                "## OECD Grouping Justification",
                "",
                f"* Target resolution failed for `{identifier}`.",
                f"* Reason: {message}",
            ]
        )
        return _build_grouping_response(
            "not_found",
            identifier,
            summary_markdown,
            log_bundle,
            {
                "report_context": {
                    "identifier": identifier,
                    "decision_context": decision_context,
                    "problem_formulation": problem_formulation,
                    "grouping_hypothesis": grouping_hypothesis,
                    "endpoints": endpoints,
                },
                "target_substance": None,
                "source_analogues": [],
                "excluded_analogues": [],
                "structure_comparison": {},
                "physicochemical_comparison": {},
                "data_matrix": [],
                "similarity_assessment": {},
                "uncertainty_assessment": {},
                "endpoint_justifications": [],
                "recommended_follow_ups": [
                    "Resolve the target substance in the Toolbox before attempting a grouping dossier."
                ],
            },
            _aggregate_calls(toolbox_calls),
        )

    target_substance = target_resolution["summary"]
    target_name = target_substance.get("preferred_name", identifier)
    target_chem_id = target_substance.get("chem_id")
    evidence_matrix: List[Dict[str, Any]] = [
        _build_evidence_row(
            "target",
            target_name,
            "identity",
            "search_chemicals",
            "resolved",
            f"Resolved to chemId `{target_chem_id}`.",
            reference=str(target_chem_id) if target_chem_id else None,
        )
    ]

    source_analogues: List[Dict[str, Any]] = []
    excluded_analogues: List[Dict[str, Any]] = []
    for analogue in analogue_identifiers:
        resolved = await _resolve_chemical(
            analogue, analogue_search_type, "grouping/analogue", toolbox_calls
        )
        log_bundle["analogue_resolutions"].append(resolved)
        if resolved["status"] == "resolved" and resolved["summary"]:
            summary = resolved["summary"]
            if not summary.get("chem_id"):
                excluded_analogues.append(
                    {
                        "identifier": analogue,
                        "reason": "Resolved record did not expose a chemId.",
                    }
                )
                continue
            source_analogues.append(summary)
            evidence_matrix.append(
                _build_evidence_row(
                    "source_analogue",
                    summary.get("preferred_name", analogue),
                    "identity",
                    "search_chemicals",
                    "resolved",
                    f"Resolved to chemId `{summary.get('chem_id')}`.",
                    reference=str(summary.get("chem_id")),
                )
            )
        else:
            excluded_analogues.append(
                {
                    "identifier": analogue,
                    "reason": resolved.get("error") or "No Toolbox record found.",
                }
            )

    target_structure_signature = await _collect_structure_signature(
        target_substance, "target", toolbox_calls
    )
    source_structure_signatures: List[Dict[str, Any]] = []
    for analogue in source_analogues:
        source_structure_signatures.append(
            await _collect_structure_signature(
                analogue, "source_analogue", toolbox_calls
            )
        )
    structure_comparison = _build_structure_comparison(
        target_structure_signature, source_structure_signatures
    )
    physicochemical_comparison = _build_physicochemical_comparison(
        target_substance, source_analogues
    )
    evidence_matrix.extend(_structure_evidence_rows(structure_comparison))
    evidence_matrix.extend(_physchem_evidence_rows(physicochemical_comparison))

    if not target_chem_id:
        message = f"Target '{target_name}' did not expose a chemId, so profiler, grouping, metabolism, and QSAR calls cannot run."
        log_bundle["errors"].append(message)

    profiler_results: List[Dict[str, Any]] = []
    profiler_groupings: List[Dict[str, Any]] = []
    simulator_results: List[Dict[str, Any]] = []
    qsar_results: List[Dict[str, Any]] = []
    profiler_provenance_cache: Dict[str, Dict[str, Any] | None] = {}
    simulator_provenance_cache: Dict[str, Dict[str, Any] | None] = {}
    model_provenance_cache: Dict[str, Dict[str, Any] | None] = {}

    if target_chem_id:
        for profiler_guid in profiler_guids:
            try:
                payload, meta = await _invoke_with_meta(
                    qsar_client.profile_with_profiler,
                    profiler_guid,
                    target_chem_id,
                    None,
                )
                profiler_provenance, profiler_info_entry = (
                    await _fetch_profiler_provenance(
                        profiler_guid, profiler_provenance_cache
                    )
                )
                profiler_result = {
                    "subject_role": "target",
                    "subject_name": target_name,
                    "chem_id": target_chem_id,
                    "profiler_guid": profiler_guid,
                    "result": payload,
                }
                if profiler_provenance:
                    profiler_result["profiler_provenance"] = profiler_provenance
                profiler_results.append(profiler_result)
                entry = _format_meta(
                    "profiling/execute",
                    meta,
                    profiler_guid=profiler_guid,
                    chem_id=target_chem_id,
                )
                if entry:
                    toolbox_calls.append(entry)
                if profiler_info_entry:
                    toolbox_calls.append(profiler_info_entry)
                evidence_matrix.append(
                    _build_evidence_row(
                        "target",
                        target_name,
                        "profiler",
                        "run_profiler",
                        "ok",
                        _summarise_payload(payload),
                        reference=profiler_guid,
                    )
                )
            except QsarClientError as exc:
                message = (
                    f"Profiler {profiler_guid} failed for target {target_name}: {exc}"
                )
                log.warning(message)
                log_bundle["errors"].append(message)
                evidence_matrix.append(
                    _build_evidence_row(
                        "target",
                        target_name,
                        "profiler",
                        "run_profiler",
                        "error",
                        str(exc),
                        reference=profiler_guid,
                    )
                )

            try:
                payload, meta = await _invoke_with_meta(
                    qsar_client.group_by_profiler, target_chem_id, profiler_guid
                )
                profiler_groupings.append(
                    {
                        "target_chem_id": target_chem_id,
                        "profiler_guid": profiler_guid,
                        "grouping": payload,
                    }
                )
                entry = _format_meta(
                    "grouping/profile",
                    meta,
                    profiler_guid=profiler_guid,
                    chem_id=target_chem_id,
                )
                if entry:
                    toolbox_calls.append(entry)
                evidence_matrix.append(
                    _build_evidence_row(
                        "target",
                        target_name,
                        "grouping",
                        "group_chemicals_by_profiler",
                        "ok",
                        _summarise_payload(payload),
                        reference=profiler_guid,
                    )
                )
            except QsarClientError as exc:
                message = f"Grouping by profiler {profiler_guid} failed for target {target_name}: {exc}"
                log.warning(message)
                log_bundle["errors"].append(message)
                evidence_matrix.append(
                    _build_evidence_row(
                        "target",
                        target_name,
                        "grouping",
                        "group_chemicals_by_profiler",
                        "error",
                        str(exc),
                        reference=profiler_guid,
                    )
                )

            for analogue in source_analogues:
                analogue_name = analogue.get(
                    "preferred_name", analogue.get("input_identifier", "Unknown")
                )
                analogue_chem_id = analogue.get("chem_id")
                try:
                    payload, meta = await _invoke_with_meta(
                        qsar_client.profile_with_profiler,
                        profiler_guid,
                        analogue_chem_id,
                        None,
                    )
                    profiler_provenance, profiler_info_entry = (
                        await _fetch_profiler_provenance(
                            profiler_guid, profiler_provenance_cache
                        )
                    )
                    profiler_result = {
                        "subject_role": "source_analogue",
                        "subject_name": analogue_name,
                        "chem_id": analogue_chem_id,
                        "profiler_guid": profiler_guid,
                        "result": payload,
                    }
                    if profiler_provenance:
                        profiler_result["profiler_provenance"] = profiler_provenance
                    profiler_results.append(profiler_result)
                    entry = _format_meta(
                        "profiling/execute",
                        meta,
                        profiler_guid=profiler_guid,
                        chem_id=analogue_chem_id,
                    )
                    if entry:
                        toolbox_calls.append(entry)
                    if profiler_info_entry:
                        toolbox_calls.append(profiler_info_entry)
                    evidence_matrix.append(
                        _build_evidence_row(
                            "source_analogue",
                            analogue_name,
                            "profiler",
                            "run_profiler",
                            "ok",
                            _summarise_payload(payload),
                            reference=profiler_guid,
                        )
                    )
                except QsarClientError as exc:
                    message = f"Profiler {profiler_guid} failed for source analogue {analogue_name}: {exc}"
                    log.warning(message)
                    log_bundle["errors"].append(message)
                    evidence_matrix.append(
                        _build_evidence_row(
                            "source_analogue",
                            analogue_name,
                            "profiler",
                            "run_profiler",
                            "error",
                            str(exc),
                            reference=profiler_guid,
                        )
                    )

        for simulator_guid in simulator_guids:
            try:
                payload, meta = await _invoke_with_meta(
                    qsar_client.simulate_metabolites_for_chem,
                    simulator_guid,
                    target_chem_id,
                )
                simulator_provenance, simulator_info_entry = (
                    await _fetch_simulator_provenance(
                        simulator_guid, simulator_provenance_cache
                    )
                )
                simulator_result = {
                    "subject_role": "target",
                    "subject_name": target_name,
                    "chem_id": target_chem_id,
                    "simulator_guid": simulator_guid,
                    "result": payload,
                }
                if simulator_provenance:
                    simulator_result["simulator_provenance"] = simulator_provenance
                simulator_results.append(simulator_result)
                entry = _format_meta(
                    "metabolism/simulate",
                    meta,
                    simulator_guid=simulator_guid,
                    chem_id=target_chem_id,
                )
                if entry:
                    toolbox_calls.append(entry)
                if simulator_info_entry:
                    toolbox_calls.append(simulator_info_entry)
                evidence_matrix.append(
                    _build_evidence_row(
                        "target",
                        target_name,
                        "metabolism",
                        "run_metabolism_simulator",
                        "ok",
                        _summarise_payload(payload),
                        reference=simulator_guid,
                    )
                )
            except QsarClientError as exc:
                message = (
                    f"Simulator {simulator_guid} failed for target {target_name}: {exc}"
                )
                log.warning(message)
                log_bundle["errors"].append(message)
                evidence_matrix.append(
                    _build_evidence_row(
                        "target",
                        target_name,
                        "metabolism",
                        "run_metabolism_simulator",
                        "error",
                        str(exc),
                        reference=simulator_guid,
                    )
                )

            for analogue in source_analogues:
                analogue_name = analogue.get(
                    "preferred_name", analogue.get("input_identifier", "Unknown")
                )
                analogue_chem_id = analogue.get("chem_id")
                try:
                    payload, meta = await _invoke_with_meta(
                        qsar_client.simulate_metabolites_for_chem,
                        simulator_guid,
                        analogue_chem_id,
                    )
                    simulator_provenance, simulator_info_entry = (
                        await _fetch_simulator_provenance(
                            simulator_guid, simulator_provenance_cache
                        )
                    )
                    simulator_result = {
                        "subject_role": "source_analogue",
                        "subject_name": analogue_name,
                        "chem_id": analogue_chem_id,
                        "simulator_guid": simulator_guid,
                        "result": payload,
                    }
                    if simulator_provenance:
                        simulator_result["simulator_provenance"] = simulator_provenance
                    simulator_results.append(simulator_result)
                    entry = _format_meta(
                        "metabolism/simulate",
                        meta,
                        simulator_guid=simulator_guid,
                        chem_id=analogue_chem_id,
                    )
                    if entry:
                        toolbox_calls.append(entry)
                    if simulator_info_entry:
                        toolbox_calls.append(simulator_info_entry)
                    evidence_matrix.append(
                        _build_evidence_row(
                            "source_analogue",
                            analogue_name,
                            "metabolism",
                            "run_metabolism_simulator",
                            "ok",
                            _summarise_payload(payload),
                            reference=simulator_guid,
                        )
                    )
                except QsarClientError as exc:
                    message = f"Simulator {simulator_guid} failed for source analogue {analogue_name}: {exc}"
                    log.warning(message)
                    log_bundle["errors"].append(message)
                    evidence_matrix.append(
                        _build_evidence_row(
                            "source_analogue",
                            analogue_name,
                            "metabolism",
                            "run_metabolism_simulator",
                            "error",
                            str(exc),
                            reference=simulator_guid,
                        )
                    )

        for qsar_guid in qsar_guids:
            try:
                prediction, apply_meta = await _invoke_with_meta(
                    qsar_client.apply_qsar_model, qsar_guid, target_chem_id
                )
                domain, domain_meta = await _invoke_with_meta(
                    qsar_client.get_qsar_domain, qsar_guid, target_chem_id
                )
                model_provenance, model_info_entry = await _fetch_model_provenance(
                    qsar_guid, model_provenance_cache
                )
                qsar_result = {
                    "subject_role": "target",
                    "subject_name": target_name,
                    "chem_id": target_chem_id,
                    "qsar_guid": qsar_guid,
                    "prediction": prediction,
                    "domain": domain,
                }
                if model_provenance:
                    qsar_result["model_provenance"] = model_provenance
                qsar_results.append(qsar_result)
                entry_apply = _format_meta(
                    "qsar/apply",
                    apply_meta,
                    qsar_guid=qsar_guid,
                    chem_id=target_chem_id,
                )
                entry_domain = _format_meta(
                    "qsar/domain",
                    domain_meta,
                    qsar_guid=qsar_guid,
                    chem_id=target_chem_id,
                )
                if entry_apply:
                    toolbox_calls.append(entry_apply)
                if entry_domain:
                    toolbox_calls.append(entry_domain)
                if model_info_entry:
                    toolbox_calls.append(model_info_entry)
                evidence_matrix.append(
                    _build_evidence_row(
                        "target",
                        target_name,
                        "qsar",
                        "run_qsar_model",
                        "ok",
                        f"Prediction: {_summarise_payload(prediction)} Domain: {_summarise_payload(domain)}",
                        reference=qsar_guid,
                    )
                )
            except QsarClientError as exc:
                message = (
                    f"QSAR model {qsar_guid} failed for target {target_name}: {exc}"
                )
                log.warning(message)
                log_bundle["errors"].append(message)
                evidence_matrix.append(
                    _build_evidence_row(
                        "target",
                        target_name,
                        "qsar",
                        "run_qsar_model",
                        "error",
                        str(exc),
                        reference=qsar_guid,
                    )
                )

    similarity_assessment = _build_similarity_assessment(
        source_analogues,
        structure_comparison,
        physicochemical_comparison,
        profiler_results,
        profiler_groupings,
        simulator_results,
        qsar_results,
        grouping_hypothesis,
    )
    uncertainty_assessment = _build_uncertainty_assessment(
        similarity_assessment,
        accepted_uncertainty_level,
        source_analogues,
    )
    endpoint_justifications = _build_endpoint_justifications(
        endpoints,
        source_analogues,
        similarity_assessment,
        uncertainty_assessment,
        grouping_hypothesis,
        decision_context,
        route_of_exposure,
        profiler_guids,
        simulator_guids,
        qsar_guids,
    )
    recommended_follow_ups = _build_recommended_follow_ups(
        source_analogues,
        similarity_assessment,
        uncertainty_assessment,
        profiler_guids,
        simulator_guids,
        qsar_guids,
    )

    report_context = {
        "identifier": identifier,
        "search_type": search_type,
        "problem_formulation": problem_formulation,
        "decision_context": decision_context,
        "grouping_hypothesis": grouping_hypothesis,
        "endpoints": endpoints,
        "route_of_exposure": route_of_exposure,
        "accepted_uncertainty_level": accepted_uncertainty_level,
        "context": context,
    }
    grouping_justification = {
        "report_context": report_context,
        "target_substance": target_substance,
        "source_analogues": source_analogues,
        "excluded_analogues": excluded_analogues,
        "structure_comparison": structure_comparison,
        "physicochemical_comparison": physicochemical_comparison,
        "data_matrix": evidence_matrix,
        "similarity_assessment": similarity_assessment,
        "uncertainty_assessment": uncertainty_assessment,
        "endpoint_justifications": endpoint_justifications,
        "recommended_follow_ups": recommended_follow_ups,
    }

    summary_markdown = _build_grouping_markdown(
        report_context,
        target_substance,
        source_analogues,
        excluded_analogues,
        structure_comparison,
        physicochemical_comparison,
        evidence_matrix,
        endpoint_justifications,
        uncertainty_assessment,
        recommended_follow_ups,
    )

    log_bundle["excluded_analogues"] = excluded_analogues
    log_bundle["structure_comparison"] = structure_comparison
    log_bundle["physicochemical_comparison"] = physicochemical_comparison
    log_bundle["profiler_results"] = profiler_results
    log_bundle["profiler_groupings"] = profiler_groupings
    log_bundle["simulator_results"] = simulator_results
    log_bundle["qsar_results"] = qsar_results
    log_bundle["data_matrix"] = evidence_matrix

    status = "ok"
    if log_bundle["errors"]:
        status = "partial"

    toolbox_meta = _aggregate_calls(toolbox_calls)
    if toolbox_meta.get("calls"):
        log_bundle["toolbox"] = toolbox_meta

    return _build_grouping_response(
        status,
        identifier,
        summary_markdown,
        log_bundle,
        grouping_justification,
        toolbox_meta,
    )


class ApproveCheckpointParams(BaseModel):
    checkpoint_id: str = Field(
        ..., description="The checkpoint ID to approve or reject."
    )
    decision: str = Field(
        "approved",
        description="Decision for this checkpoint: `approved` or `rejected`.",
    )
    comments: Optional[str] = Field(
        None, description="Optional reviewer comments explaining the decision."
    )


async def approve_workflow_checkpoint(
    checkpoint_id: str,
    decision: str,
    comments: Optional[str],
) -> Dict[str, Any]:
    checkpoint = review_orchestrator.get_checkpoint(checkpoint_id)
    if not checkpoint:
        return {
            "status": "error",
            "message": f"Checkpoint {checkpoint_id} not found.",
        }
    try:
        review_decision = ReviewDecision(decision.lower())
        review_orchestrator.submit_review(
            checkpoint_id, "mcp_user", review_decision, comments=comments
        )
    except ValueError as exc:
        return {
            "status": "error",
            "message": str(exc),
        }
    return {
        "status": "ok",
        "checkpoint_id": checkpoint_id,
        "decision": review_decision.value,
        "workflow_id": checkpoint.workflow_id,
        "message": f"Checkpoint {checkpoint_id} marked as {review_decision.value}.",
    }


def register_workflow_tool() -> None:
    tool_registry.register(
        name="run_oqt_multiagent_workflow",
        description="Executes the O-QT multi-agent orchestration: searches for the chemical, optionally runs profilers, metabolism simulators, and QSAR models, and returns a Markdown summary, log JSON, and PDF report.",
        parameters_model=WorkflowParams,
        implementation=run_oqt_multiagent_workflow,
    )
    tool_registry.register(
        name="run_qsar_workflow",
        description="Deprecated alias for run_oqt_multiagent_workflow. Executes the O-QT multi-agent orchestration and returns structured results plus artifacts.",
        parameters_model=WorkflowParams,
        implementation=run_oqt_multiagent_workflow,
    )
    tool_registry.register(
        name="build_grouping_justification",
        description="Builds an OECD-style grouping/read-across dossier by resolving a target and source analogues, collecting profiler/metabolism/QSAR evidence, and returning a structured justification with uncertainty reporting.",
        parameters_model=GroupingJustificationParams,
        implementation=build_grouping_justification,
    )
    tool_registry.register(
        name="approve_workflow_checkpoint",
        description="Approves or rejects a pending workflow review checkpoint. Used to resume workflows that paused for human review.",
        parameters_model=ApproveCheckpointParams,
        implementation=approve_workflow_checkpoint,
    )


register_workflow_tool()
