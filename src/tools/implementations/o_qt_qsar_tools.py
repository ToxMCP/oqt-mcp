import logging
import uuid
import inspect
from typing import Any, Dict

from pydantic import BaseModel, Field

from src.qsar import QsarClientError, qsar_client
from src.tools.registry import tool_registry

log = logging.getLogger(__name__)

# --- Pydantic Models for Tool Parameters (Input Validation - Section 2.3) ---


class ModelInfoParams(BaseModel):
    model_id: str = Field(..., description="The unique identifier for the QSAR model.")


class ChemicalSearchParams(BaseModel):
    query: str = Field(
        ..., description="The search term (Name, CAS number, or SMILES)."
    )
    search_type: str = Field(
        "auto", description="Type of search (e.g., 'auto', 'name', 'cas', 'smiles')."
    )


class QSARPredictionParams(BaseModel):
    smiles: str = Field(
        ..., description="The SMILES representation of the chemical structure."
    )
    model_id: str = Field(
        ..., description="The identifier of the QSAR model to use for prediction."
    )


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
    total = round(
        sum(call.get("duration_ms", 0.0) or 0.0 for call in calls), 3
    ) if calls else 0.0
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


def _attach_toolbox(result: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
    if meta.get("calls"):
        result["toolbox"] = meta
    return result


async def get_public_qsar_model_info(model_id: str) -> dict:
    """Retrieves information about a specific QSAR model."""
    log.info(f"Fetching QSAR model info for ID: {model_id}")
    try:
        payload, meta = await _invoke_with_meta(qsar_client.get_model_metadata, model_id)
    except QsarClientError as exc:
        log.error("Failed to retrieve QSAR model info: %s", exc)
        raise
    toolbox_meta = _aggregate_meta(_format_meta("about/object", meta))
    if isinstance(payload, dict):
        result = dict(payload)
    else:
        result = {"data": payload}
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

    try:
        hits_data, search_meta = await _invoke_with_meta(
            qsar_client.search_chemicals, smiles, "smiles"
        )
    except QsarClientError as exc:
        log.warning("SMILES lookup failed (%s); falling back to run_prediction.", exc)
        payload = await qsar_client.run_prediction(smiles, model_id)
        if isinstance(payload, dict):
            return payload
        return {"smiles": smiles, "model_id": model_id, "prediction": payload}

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
        if isinstance(payload, dict):
            return payload
        return {"smiles": smiles, "model_id": model_id, "prediction": payload}

    result = {
        "chem_id": chem_id,
        "model_id": model_id,
        "prediction": prediction,
        "domain": domain,
        "search_hits": hits,
    }
    toolbox_meta = _aggregate_meta(
        _format_meta("search/smiles", search_meta),
        _format_meta("qsar/apply", apply_meta),
        _format_meta("qsar/domain", domain_meta),
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

    endpoint_payload = None
    profiling_payload = None
    endpoint_meta = None
    profiling_meta = None
    
    # Track availability status
    data_availability = {
        "endpoint_data_available": False,
        "profiling_data_available": False,
        "warnings": []
    }
    
    try:
        endpoint_payload, endpoint_meta = await _invoke_with_meta(
            qsar_client.get_endpoint_data,
            chem_id,
            endpoint=endpoint,
            include_metadata=True,
        )
        data_availability["endpoint_data_available"] = bool(endpoint_payload)
    except QsarClientError as exc:
        error_msg = str(exc)
        log.warning("Endpoint data retrieval failed for %s: %s", chem_id, error_msg)
        
        if "404" in error_msg:
            warning = f"No endpoint data found for '{endpoint}' in the QSAR Toolbox database. This chemical may not have experimental data for this endpoint, or the endpoint name may need adjustment."
            data_availability["warnings"].append(warning)
            summary["endpoint_error"] = warning
        else:
            summary["endpoint_error"] = f"API error: {error_msg}"
            data_availability["warnings"].append(f"Endpoint data retrieval failed: {error_msg}")

    try:
        profiling_payload, profiling_meta = await _invoke_with_meta(
            qsar_client.profile_chemical, chem_id
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
            data_availability["warnings"].append(f"Profiling retrieval failed: {error_msg}")

    summary["endpoint_data"] = endpoint_payload
    summary["profiling"] = profiling_payload
    summary["data_availability"] = data_availability
    
    # Add helpful suggestions if no data was found
    if not data_availability["endpoint_data_available"] and not data_availability["profiling_data_available"]:
        summary["suggestions"] = [
            "Try searching for the chemical first using 'search_chemicals' to verify it exists in the database",
            "If using a name, try the CAS number instead",
            "If using CAS, try the chemical name or SMILES structure",
            "Check that the endpoint name matches available endpoints (use discovery tools to list endpoints)"
        ]
    toolbox_meta = _aggregate_meta(
        _format_meta("search/auto", search_meta),
        _format_meta("data/endpoint", endpoint_meta),
        _format_meta("profiling/all", profiling_meta),
    )
    return _attach_toolbox(summary, toolbox_meta)


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

    result = {
        "smiles": smiles,
        "simulator_guid": simulator_guid,
        "metabolites": metabolites,
    }
    toolbox_meta = _aggregate_meta(
        _format_meta("metabolism/generate", meta),
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
