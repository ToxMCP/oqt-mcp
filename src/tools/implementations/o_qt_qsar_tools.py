import asyncio
import inspect
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from pydantic import BaseModel, Field

from src.config.settings import settings
from src.qsar import QsarClientError, qsar_client
from src.tools.hazard_contracts import (
    build_decision_owner,
    build_endpoint_summaries_from_payload,
    build_hazard_applicability_domain,
    build_hazard_assessment_boundary,
    build_hazard_decision_boundary,
    build_hazard_evidence_blocks,
    build_hazard_required_external_inputs,
    build_hazard_semantic_coverage,
    build_hazard_supports,
    build_hazard_uncertainty_assessment,
    build_request_metadata,
)
from src.tools.provenance import (
    attach_provenance,
    attach_provenance_collection,
    build_endpoint_study_records,
    build_provenance,
)
from src.tools.registry import tool_registry

log = logging.getLogger(__name__)

_TOOLBOX_SOURCE_SYSTEM = "OECD QSAR Toolbox WebAPI"
_GENERATED_BY_VERSION = "O-QT MCP Server v0.3.0"
_TOXMCP_REPOSITORY_URL = "https://github.com/ToxMCP/oqt-mcp"
_TOOLBOX_COMPATIBILITY_NOTE = (
    "Current WebAPI client targets /api/v6 compatibility routes."
)

_ENDPOINT_POSITION_ALIASES = {
    "mutagenicity": "Human Health Hazards#Genetic Toxicity",
    "genotoxicity": "Human Health Hazards#Genetic Toxicity",
    "genetic toxicity": "Human Health Hazards#Genetic Toxicity",
    "skin sensitization": "Human Health Hazards#Sensitisation",
    "skin sensitisation": "Human Health Hazards#Sensitisation",
    "sensitization": "Human Health Hazards#Sensitisation",
    "sensitisation": "Human Health Hazards#Sensitisation",
}

# --- Pydantic Models for Tool Parameters (Input Validation - Section 2.3) ---


class ModelInfoParams(BaseModel):
    model_id: str = Field(..., description="The unique identifier for the QSAR model.")

    model_config = {"protected_namespaces": ()}


class ChemicalSearchParams(BaseModel):
    query: str = Field(
        ..., description="The search term (Name, CAS number, or SMILES)."
    )
    search_type: str = Field(
        "name", description="Type of search (e.g., 'auto', 'name', 'cas', 'smiles')."
    )


class QSARPredictionParams(BaseModel):
    smiles: str = Field(
        ..., description="The SMILES representation of the chemical structure."
    )
    model_id: str = Field(
        ..., description="The identifier of the QSAR model to use for prediction."
    )

    model_config = {"protected_namespaces": ()}


class HazardAnalysisParams(BaseModel):
    chemical_identifier: str = Field(
        ..., description="CAS number or SMILES of the chemical."
    )
    endpoint: str = Field(
        ...,
        description="The toxicological endpoint to analyze (e.g., 'Skin Sensitization', 'Mutagenicity').",
    )


class MetabolismParams(BaseModel):
    smiles: str = Field(
        ..., description="The SMILES representation of the chemical structure."
    )
    simulator: str = Field(
        ...,
        description="The metabolism simulator to use (e.g., 'Liver', 'Skin', 'Microbial').",
    )


# --- Tool Implementations ---
# These functions contain the actual logic for interacting with the O-QT QSAR Toolbox.


def _format_meta(label: str, meta: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not meta:
        return None
    return {
        "endpoint": label,
        "attempts": meta.get("attempts"),
        "duration_ms": meta.get("duration_ms"),
        "timeout_profile": meta.get("timeout_profile"),
        "status_code": meta.get("status_code"),
    }


def _aggregate_meta(*entries: Dict[str, Any] | None) -> Dict[str, Any]:
    calls = [entry for entry in entries if entry]
    total = (
        round(sum(call.get("duration_ms", 0.0) or 0.0 for call in calls), 3)
        if calls
        else 0.0
    )
    return {"calls": calls, "total_duration_ms": total}


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


async def _invoke_with_wallclock_timeout(
    func, *args, wallclock_timeout: float | None = None, **kwargs
):
    if not wallclock_timeout or wallclock_timeout <= 0:
        return await _invoke_with_meta(func, *args, **kwargs)
    try:
        return await asyncio.wait_for(
            _invoke_with_meta(func, *args, **kwargs),
            timeout=wallclock_timeout,
        )
    except asyncio.TimeoutError as exc:
        raise QsarClientError(
            f"Timed out after {wallclock_timeout:.0f}s while waiting for the QSAR Toolbox."
        ) from exc


def _attach_toolbox(result: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
    if meta.get("calls"):
        result["toolbox"] = meta
    return result


def _normalise_endpoint_label(value: str) -> str:
    return " ".join((value or "").replace("#", " ").replace("_", " ").split()).lower()


async def _resolve_endpoint_position(
    endpoint: str,
) -> tuple[str | None, dict[str, Any], dict[str, Any] | None]:
    raw_endpoint = (endpoint or "").strip()
    resolution: dict[str, Any] = {
        "input": endpoint,
        "strategy": "raw-endpoint",
        "resolved_position": None,
    }
    if not raw_endpoint:
        return None, resolution, None

    if "#" in raw_endpoint:
        resolution.update(
            {"strategy": "explicit-position", "resolved_position": raw_endpoint}
        )
        return raw_endpoint, resolution, None

    try:
        positions, meta = await _invoke_with_meta(qsar_client.get_endpoint_tree)
    except QsarClientError as exc:
        log.warning("Endpoint tree lookup failed for %s: %s", endpoint, exc)
        resolution["warning"] = str(exc)
        return None, resolution, None

    endpoint_tree_meta = _format_meta("data/endpoints", meta)
    if not isinstance(positions, list):
        return None, resolution, endpoint_tree_meta

    normalized = _normalise_endpoint_label(raw_endpoint)
    alias = _ENDPOINT_POSITION_ALIASES.get(normalized)
    if alias and alias in positions:
        resolution.update({"strategy": "alias", "resolved_position": alias})
        return alias, resolution, endpoint_tree_meta

    exact_match = next(
        (
            position
            for position in positions
            if str(position).strip().lower() == raw_endpoint.lower()
        ),
        None,
    )
    if exact_match:
        resolution.update(
            {"strategy": "exact-position", "resolved_position": exact_match}
        )
        return exact_match, resolution, endpoint_tree_meta

    leaf_match = next(
        (
            position
            for position in positions
            if _normalise_endpoint_label(str(position).split("#")[-1]) == normalized
        ),
        None,
    )
    if leaf_match:
        resolution.update({"strategy": "leaf-match", "resolved_position": leaf_match})
        return leaf_match, resolution, endpoint_tree_meta

    contains_matches = [
        position
        for position in positions
        if normalized and normalized in _normalise_endpoint_label(str(position))
    ]
    if len(contains_matches) == 1:
        resolution.update(
            {"strategy": "contains-match", "resolved_position": contains_matches[0]}
        )
        return contains_matches[0], resolution, endpoint_tree_meta

    if contains_matches:
        resolution["candidate_positions"] = contains_matches[:5]
    return None, resolution, endpoint_tree_meta


async def _fetch_model_provenance(model_id: str) -> tuple[dict | None, dict | None]:
    try:
        payload, meta = await _invoke_with_meta(
            qsar_client.get_model_metadata, model_id
        )
    except QsarClientError as exc:
        log.warning("QSAR model metadata lookup failed for %s: %s", model_id, exc)
        return None, None
    return build_provenance(payload), _format_meta("about/object", meta)


async def _fetch_simulator_provenance(
    simulator_guid: str,
) -> tuple[dict | None, dict | None]:
    try:
        payload, meta = await _invoke_with_meta(
            qsar_client.get_simulator_info, simulator_guid
        )
    except QsarClientError as exc:
        log.warning("Simulator metadata lookup failed for %s: %s", simulator_guid, exc)
        return None, None
    return build_provenance(payload), _format_meta("metabolism/info", meta)


async def get_public_qsar_model_info(model_id: str) -> dict:
    """Retrieves information about a specific QSAR model."""
    log.info(f"Fetching QSAR model info for ID: {model_id}")
    try:
        payload, meta = await _invoke_with_meta(
            qsar_client.get_model_metadata, model_id
        )
    except QsarClientError as exc:
        log.error("Failed to retrieve QSAR model info: %s", exc)
        raise
    toolbox_meta = _aggregate_meta(_format_meta("about/object", meta))
    if isinstance(payload, dict):
        result = dict(payload)
    else:
        result = {"data": payload}
    result = attach_provenance(result, payload)
    return _attach_toolbox(result, toolbox_meta)


async def search_chemicals(query: str, search_type: str) -> dict:
    """Searches for a chemical in the QSAR Toolbox database."""
    log.info(f"Searching chemical: {query} (Type: {search_type})")
    try:
        results, meta = await _invoke_with_meta(
            qsar_client.search_chemicals, query, search_type
        )
    except QsarClientError as exc:
        log.error("Chemical search failed: %s", exc)
        raise
    toolbox_meta = _aggregate_meta(_format_meta("search/chemicals", meta))
    if isinstance(results, dict):
        return _attach_toolbox(dict(results), toolbox_meta)
    result = {"results": results}
    return _attach_toolbox(result, toolbox_meta)


async def run_qsar_prediction(smiles: str, model_id: str) -> dict:
    """Runs a QSAR prediction."""
    log.info(
        f"Running QSAR prediction for SMILES: {smiles[:20]}... using model: {model_id}"
    )

    model_provenance, model_meta = await _fetch_model_provenance(model_id)

    try:
        hits_data, search_meta = await _invoke_with_meta(
            qsar_client.search_chemicals, smiles, "smiles"
        )
    except QsarClientError as exc:
        log.warning("SMILES lookup failed (%s); falling back to run_prediction.", exc)
        payload = await qsar_client.run_prediction(smiles, model_id)
        result = (
            dict(payload)
            if isinstance(payload, dict)
            else {
                "smiles": smiles,
                "model_id": model_id,
                "prediction": payload,
            }
        )
        if model_provenance:
            result["model_provenance"] = model_provenance
        toolbox_meta = _aggregate_meta(_format_meta("about/object", model_meta))
        return _attach_toolbox(result, toolbox_meta)

    hits = hits_data
    if isinstance(hits, dict):
        hits = [hits]

    if not hits:
        raise QsarClientError("No Toolbox structures matched the provided SMILES.")

    chem_id = hits[0].get("ChemId")
    if not chem_id:
        raise QsarClientError("QSAR Toolbox did not return a chemId for the SMILES.")

    try:
        prediction, apply_meta = await _invoke_with_meta(
            qsar_client.apply_qsar_model, model_id, chem_id
        )
        domain, domain_meta = await _invoke_with_meta(
            qsar_client.get_qsar_domain, model_id, chem_id
        )
    except QsarClientError as exc:
        log.warning("QSAR apply failed (%s); falling back to run_prediction.", exc)
        payload = await qsar_client.run_prediction(smiles, model_id)
        result = (
            dict(payload)
            if isinstance(payload, dict)
            else {
                "smiles": smiles,
                "model_id": model_id,
                "prediction": payload,
            }
        )
        if model_provenance:
            result["model_provenance"] = model_provenance
        toolbox_meta = _aggregate_meta(
            _format_meta("search/smiles", search_meta),
            _format_meta("about/object", model_meta),
        )
        return _attach_toolbox(result, toolbox_meta)

    # Light-weight applicability-domain gating (OQT-01)
    domain_value = ""
    if isinstance(domain, dict):
        domain_value = domain.get("DomainResult") or domain.get("Domain") or ""
    elif isinstance(domain, str):
        domain_value = domain
    domain_normalized = (
        str(domain_value).strip().replace(" ", "").replace("-", "").lower()
    )
    ad_warning = domain_normalized in {"outofdomain", "out_of_domain"}

    result = {
        "chem_id": chem_id,
        "model_id": model_id,
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
        result["ad_recommendation"] = (
            "This prediction is outside the model's applicability domain. "
            "Treat with caution and consider experimental validation or read-across."
        )
    if model_provenance:
        result["model_provenance"] = model_provenance
    toolbox_meta = _aggregate_meta(
        _format_meta("search/smiles", search_meta),
        _format_meta("qsar/apply", apply_meta),
        _format_meta("qsar/domain", domain_meta),
        _format_meta("about/object", model_meta),
    )
    return _attach_toolbox(result, toolbox_meta)


def _normalise_identifier(identifier: str) -> str:
    return (identifier or "").strip()


def _looks_like_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, TypeError, AttributeError):
        return False


async def analyze_chemical_hazard(chemical_identifier: str, endpoint: str) -> dict:
    """Analyzes hazards by fetching experimental data and profiling."""
    log.info(f"Analyzing hazard for {chemical_identifier} regarding {endpoint}")

    identifier = _normalise_identifier(chemical_identifier)
    resolution_log: dict[str, any] = {"query": identifier}
    chem_id = identifier
    search_hits = []

    if not _looks_like_uuid(identifier):
        try:
            hits_payload, search_meta = await _invoke_with_meta(
                qsar_client.search_chemicals, identifier, "auto"
            )
        except QsarClientError as exc:
            log.warning("Hazard analysis search failed: %s", exc)
            hits_payload = []
            search_meta = None

        search_hits = hits_payload
        if isinstance(search_hits, dict):
            search_hits = [search_hits]

        resolution_log["search_hits"] = search_hits
        if search_hits:
            chem_id = search_hits[0].get("ChemId") or chem_id
    else:
        search_meta = None

    summary: dict[str, any] = {
        "chemical_identifier": identifier,
        "resolved_chem_id": chem_id,
        "endpoint": endpoint,
        "search_hits": search_hits,
    }
    if search_hits:
        first_hit = search_hits[0]
        summary["chemical_identity"] = {
            "chem_id": chem_id,
            "preferred_name": (first_hit.get("Names") or [identifier])[0],
            "cas": first_hit.get("Cas"),
            "smiles": first_hit.get("Smiles") or first_hit.get("SMILES"),
        }
    elif _looks_like_uuid(chem_id):
        summary["chemical_identity"] = {
            "chem_id": chem_id,
            "preferred_name": identifier,
            "cas": None,
            "smiles": None,
        }

    endpoint_payload = None
    profiling_payload = None
    endpoint_meta = None
    profiling_meta = None
    endpoint_tree_meta = None

    endpoint_position, endpoint_resolution, endpoint_tree_meta = (
        await _resolve_endpoint_position(endpoint)
    )
    summary["endpoint_resolution"] = endpoint_resolution
    if endpoint_position:
        summary["resolved_endpoint_position"] = endpoint_position

    # Track availability status
    data_availability = {
        "endpoint_data_available": False,
        "profiling_data_available": False,
        "warnings": [],
    }

    try:
        endpoint_kwargs = {"include_metadata": True}
        if endpoint_position:
            endpoint_kwargs["position"] = endpoint_position
        else:
            endpoint_kwargs["endpoint"] = endpoint

        endpoint_payload, endpoint_meta = await _invoke_with_meta(
            qsar_client.get_endpoint_data,
            chem_id,
            **endpoint_kwargs,
        )
        data_availability["endpoint_data_available"] = bool(endpoint_payload)
    except QsarClientError as exc:
        error_msg = str(exc)
        if endpoint_position and endpoint_position != endpoint:
            log.warning(
                "Endpoint position lookup failed for %s at %s: %s; retrying raw endpoint",
                chem_id,
                endpoint_position,
                error_msg,
            )
            try:
                endpoint_payload, endpoint_meta = await _invoke_with_meta(
                    qsar_client.get_endpoint_data,
                    chem_id,
                    endpoint=endpoint,
                    include_metadata=True,
                )
                data_availability["endpoint_data_available"] = bool(endpoint_payload)
            except QsarClientError as fallback_exc:
                error_msg = str(fallback_exc)
                log.warning(
                    "Endpoint data retrieval failed for %s via raw endpoint %s: %s",
                    chem_id,
                    endpoint,
                    error_msg,
                )
        else:
            log.warning("Endpoint data retrieval failed for %s: %s", chem_id, error_msg)

        if "404" in error_msg:
            warning = f"No endpoint data found for '{endpoint}' in the QSAR Toolbox database. This chemical may not have experimental data for this endpoint, or the endpoint name may need adjustment."
            data_availability["warnings"].append(warning)
            summary["endpoint_error"] = warning
        else:
            summary["endpoint_error"] = f"API error: {error_msg}"
            data_availability["warnings"].append(
                f"Endpoint data retrieval failed: {error_msg}"
            )

    try:
        profiling_payload, profiling_meta = await _invoke_with_wallclock_timeout(
            qsar_client.profile_chemical,
            chem_id,
            wallclock_timeout=settings.qsar.QSAR_HAZARD_PROFILING_WALLCLOCK_TIMEOUT_SECONDS,
        )
        data_availability["profiling_data_available"] = bool(profiling_payload)
    except QsarClientError as exc:
        error_msg = str(exc)
        log.warning("Profiling retrieval failed for %s: %s", chem_id, error_msg)

        if "404" in error_msg:
            warning = f"No profiling data found for this chemical in the QSAR Toolbox. The chemical may not be in the profiling database, or you may need to use a different identifier (try CAS number or SMILES)."
            data_availability["warnings"].append(warning)
            summary["profiling_error"] = warning
        else:
            summary["profiling_error"] = f"API error: {error_msg}"
            data_availability["warnings"].append(
                f"Profiling retrieval failed: {error_msg}"
            )

    summary["endpoint_data"] = endpoint_payload
    summary["profiling"] = profiling_payload
    summary["data_availability"] = data_availability
    generated_at = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    endpoint_study_records = build_endpoint_study_records(endpoint_payload)
    summary["endpoint_study_records"] = endpoint_study_records
    summary["endpoint_summaries"] = build_endpoint_summaries_from_payload(
        endpoint_payload,
        requested_endpoint=endpoint,
        resolved_position=summary.get("resolved_endpoint_position"),
    )
    summary["request_metadata"] = build_request_metadata(
        requested_at=generated_at,
        requested_endpoints=[endpoint],
        summary_only=False,
    )
    summary["uncertainty_assessment"] = build_hazard_uncertainty_assessment(
        endpoint_record_count=len(endpoint_study_records),
        endpoint_requested=True,
        profiling_record_count=1 if profiling_payload else 0,
        profiling_requested=True,
        extra_gaps=data_availability["warnings"],
    )
    summary = attach_provenance_collection(
        summary, endpoint_payload, field_name="endpoint_data_provenance"
    )
    summary = attach_provenance_collection(
        summary, profiling_payload, field_name="profiling_provenance"
    )
    summary["evidence_blocks"] = build_hazard_evidence_blocks(
        endpoint_summaries=summary["endpoint_summaries"],
        endpoint_provenance=summary.get("endpoint_data_provenance"),
        profiling_provenance=summary.get("profiling_provenance"),
        uncertainty_assessment=summary["uncertainty_assessment"],
    )
    summary["applicability_domain"] = build_hazard_applicability_domain([])
    summary["uncertainty_assessment"]["semanticCoverage"] = (
        build_hazard_semantic_coverage(
            endpoint_summaries=summary["endpoint_summaries"],
            applicability_domain=summary["applicability_domain"],
            uncertainty_assessment=summary["uncertainty_assessment"],
        )
    )

    # Add helpful suggestions if no data was found
    if (
        not data_availability["endpoint_data_available"]
        and not data_availability["profiling_data_available"]
    ):
        summary["suggestions"] = [
            "Try searching for the chemical first using 'search_chemicals' to verify it exists in the database",
            "If using a name, try the CAS number instead",
            "If using CAS, try the chemical name or SMILES structure",
            "Check that the endpoint name matches available endpoints (use discovery tools to list endpoints)",
        ]
    toolbox_meta = _aggregate_meta(
        _format_meta("search/auto", search_meta),
        endpoint_tree_meta,
        _format_meta("data/endpoint", endpoint_meta),
        _format_meta("profiling/all", profiling_meta),
    )
    result = _attach_toolbox(summary, toolbox_meta)

    record_id = f"oqthzd-{uuid.uuid4().hex[:12]}"
    result["portable_handoffs"] = {
        "oqtHazardEvidenceSummary.v1": {
            "schemaName": "oqtHazardEvidenceSummary",
            "schemaVersion": "v1",
            "module": "oqt-mcp",
            "chemicalIdentity": {
                "inputIdentifier": identifier,
                "preferredName": result.get("chemical_identity", {}).get(
                    "preferred_name"
                )
                or identifier,
                "chemId": chem_id,
                **(
                    {"cas": result["chemical_identity"]["cas"]}
                    if result.get("chemical_identity", {}).get("cas")
                    else {}
                ),
                **(
                    {"smiles": result["chemical_identity"]["smiles"]}
                    if result.get("chemical_identity", {}).get("smiles")
                    else {}
                ),
            },
            "profilers": [],
            "metabolismFindings": [],
            "qsarFindings": [],
            "endpointSummaries": result["endpoint_summaries"],
            "evidenceBlocks": result["evidence_blocks"],
            "requestMetadata": {
                "requestedAt": result["request_metadata"]["requestedAt"],
                "requestedEndpoints": result["request_metadata"]["requestedEndpoints"],
                "requestedProfilers": [],
                "requestedSimulators": [],
                "requestedQsarModels": [],
                "summaryOnly": False,
            },
            "assessmentBoundary": build_hazard_assessment_boundary(),
            "decisionBoundary": build_hazard_decision_boundary(),
            "decisionOwner": build_decision_owner(),
            "supports": build_hazard_supports(
                endpoint_summaries=result["endpoint_summaries"],
                profiler_findings=[],
                applicability_domain=result["applicability_domain"],
            ),
            "requiredExternalInputs": build_hazard_required_external_inputs(),
            "uncertaintyAssessment": result["uncertainty_assessment"],
            "applicabilityDomain": result["applicability_domain"],
            "applicabilityNotes": [
                _TOOLBOX_COMPATIBILITY_NOTE,
                "This summary captures direct endpoint and profiling retrieval only; broader module evidence still requires explicit profiler, metabolism, or QSAR execution.",
            ],
            "provenance": {
                "workflowId": record_id,
                "sourceSystem": _TOOLBOX_SOURCE_SYSTEM,
                "generatedBy": _GENERATED_BY_VERSION,
                "generatedAt": generated_at,
                "references": [_TOXMCP_REPOSITORY_URL],
                "sourceTools": [
                    call["endpoint"]
                    for call in result.get("toolbox", {}).get("calls", [])
                    if isinstance(call, dict) and call.get("endpoint")
                ],
                "sources": [
                    {
                        "name": call["endpoint"],
                        "endpoint": call["endpoint"],
                        **(
                            {"statusCode": int(call["status_code"])}
                            if isinstance(call.get("status_code"), (int, float))
                            else {}
                        ),
                        **(
                            {"durationMs": float(call["duration_ms"])}
                            if isinstance(call.get("duration_ms"), (int, float))
                            else {}
                        ),
                        **(
                            {"attempts": int(call["attempts"])}
                            if isinstance(call.get("attempts"), (int, float))
                            else {}
                        ),
                        **(
                            {"timeoutProfile": str(call["timeout_profile"])}
                            if call.get("timeout_profile")
                            else {}
                        ),
                        **({"reference": chem_id} if chem_id else {}),
                    }
                    for call in result.get("toolbox", {}).get("calls", [])
                    if isinstance(call, dict) and call.get("endpoint")
                ],
            },
            "limitations": data_availability["warnings"]
            or [
                "This summary does not include explicit profiler, metabolism, or QSAR model executions."
            ],
            "context": None,
        }
    }
    return result


async def generate_metabolites(smiles: str, simulator: str) -> dict:
    """Simulates metabolism for a given chemical structure."""
    log.info(
        f"Generating metabolites for {smiles[:20]}... using simulator: {simulator}"
    )

    simulator_guid = simulator.strip()
    if not _looks_like_uuid(simulator_guid):
        try:
            catalog = await qsar_client.list_simulators()
        except QsarClientError as exc:
            log.warning("Failed to resolve simulator caption: %s", exc)
            catalog = []

        if isinstance(catalog, dict):
            catalog = [catalog]

        match = next(
            (
                entry
                for entry in catalog or []
                if isinstance(entry, dict)
                and entry.get("Caption", "").lower() == simulator.lower()
            ),
            None,
        )
        if not match or not match.get("Guid"):
            log.warning(
                "Simulator caption '%s' could not be resolved; using raw identifier.",
                simulator,
            )
        else:
            simulator_guid = match["Guid"]

    try:
        metabolites, meta = await _invoke_with_meta(
            qsar_client.generate_metabolites, smiles, simulator_guid
        )
    except QsarClientError as exc:
        log.error("Metabolite generation failed: %s", exc)
        raise

    simulator_provenance, simulator_meta = await _fetch_simulator_provenance(
        simulator_guid
    )

    result = {
        "smiles": smiles,
        "simulator_guid": simulator_guid,
        "metabolites": metabolites,
    }
    if simulator_provenance:
        result["simulator_provenance"] = simulator_provenance
    toolbox_meta = _aggregate_meta(
        _format_meta("metabolism/generate", meta),
        _format_meta("metabolism/info", simulator_meta),
    )
    return _attach_toolbox(result, toolbox_meta)


# --- Tool Registration ---


def register_qsar_tools():
    """Registers the O-QT QSAR tools with the tool registry."""

    tool_registry.register(
        name="get_public_qsar_model_info",
        # Descriptions are critical for LLM understanding (Section 3.1)
        description="Retrieves metadata and status information for a specified public QSAR model from the O-QT Toolbox.",
        parameters_model=ModelInfoParams,
        implementation=get_public_qsar_model_info,
    )

    tool_registry.register(
        name="search_chemicals",
        description="Searches the QSAR Toolbox database for chemical structures by name, CAS number, or SMILES.",
        parameters_model=ChemicalSearchParams,
        implementation=search_chemicals,
    )

    tool_registry.register(
        name="run_qsar_prediction",
        description="Executes a QSAR prediction for a chemical structure (SMILES string) using a specified model.",
        parameters_model=QSARPredictionParams,
        implementation=run_qsar_prediction,
    )

    tool_registry.register(
        name="analyze_chemical_hazard",
        description="Performs a hazard analysis by fetching experimental data and running profilers for a specific toxicological endpoint.",
        parameters_model=HazardAnalysisParams,
        implementation=analyze_chemical_hazard,
    )

    tool_registry.register(
        name="generate_metabolites",
        description="Simulates the metabolism of a chemical structure using a specified simulator (e.g., Liver, Skin).",
        parameters_model=MetabolismParams,
        implementation=generate_metabolites,
    )


# Register tools upon import
register_qsar_tools()
