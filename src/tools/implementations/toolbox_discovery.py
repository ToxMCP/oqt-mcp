import logging
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from src.qsar import QsarClientError, qsar_client
from src.tools.registry import tool_registry

log = logging.getLogger(__name__)


class EmptyParams(BaseModel):
    """Placeholder parameters model for tools that take no input."""


class ProfilerInfoParams(BaseModel):
    profiler_guid: str = Field(
        ..., description="GUID of the profiler to retrieve metadata for."
    )


class SimulatorInfoParams(BaseModel):
    simulator_guid: str = Field(
        ..., description="GUID of the metabolism simulator to retrieve metadata for."
    )


class CalculatorInfoParams(BaseModel):
    calculator_guid: str = Field(
        ..., description="GUID of the calculator to retrieve metadata for."
    )


class QsarModelsParams(BaseModel):
    position: str = Field(
        ..., description="Endpoint tree position (e.g., 'ECOTOX#Aquatic#Daphnia')."
    )


async def _safe_list_response(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        return [payload]
    return []


async def list_profilers() -> Dict[str, Any]:
    try:
        data = await qsar_client.list_profilers()
    except QsarClientError as exc:
        log.error("Failed to list profilers: %s", exc)
        raise
    return {"profilers": await _safe_list_response(data)}


async def get_profiler_info(profiler_guid: str) -> Dict[str, Any]:
    try:
        data = await qsar_client.get_profiler_info(profiler_guid)
    except QsarClientError as exc:
        log.error("Failed to fetch profiler info (%s): %s", profiler_guid, exc)
        raise
    return {"profiler": data}


async def list_simulators() -> Dict[str, Any]:
    try:
        data = await qsar_client.list_simulators()
    except QsarClientError as exc:
        log.error("Failed to list simulators: %s", exc)
        raise
    return {"simulators": await _safe_list_response(data)}


async def get_simulator_info(simulator_guid: str) -> Dict[str, Any]:
    try:
        data = await qsar_client.get_simulator_info(simulator_guid)
    except QsarClientError as exc:
        log.error("Failed to fetch simulator info (%s): %s", simulator_guid, exc)
        raise
    return {"simulator": data}


async def list_calculators() -> Dict[str, Any]:
    try:
        data = await qsar_client.list_calculators()
    except QsarClientError as exc:
        log.error("Failed to list calculators: %s", exc)
        raise
    return {"calculators": await _safe_list_response(data)}


async def get_calculator_info(calculator_guid: str) -> Dict[str, Any]:
    try:
        data = await qsar_client.get_calculator_info(calculator_guid)
    except QsarClientError as exc:
        log.error("Failed to fetch calculator info (%s): %s", calculator_guid, exc)
        raise
    return {"calculator": data}


async def get_endpoint_tree() -> Dict[str, Any]:
    try:
        data = await qsar_client.get_endpoint_tree()
    except QsarClientError as exc:
        log.error("Failed to fetch endpoint tree: %s", exc)
        raise
    tree = data if isinstance(data, list) else []
    return {"endpoint_tree": tree}


async def get_metadata_hierarchy() -> Dict[str, Any]:
    try:
        data = await qsar_client.get_metadata_hierarchy()
    except QsarClientError as exc:
        log.error("Failed to fetch metadata hierarchy: %s", exc)
        raise
    hierarchy = data if isinstance(data, list) else []
    return {"metadata_hierarchy": hierarchy}


async def list_qsar_models(position: str) -> Dict[str, Any]:
    try:
        models = await qsar_client.list_qsar_models(position)
    except QsarClientError as exc:
        log.error("Failed to list QSAR models for %s: %s", position, exc)
        raise
    return {"position": position, "models": await _safe_list_response(models)}


async def list_all_qsar_models() -> Dict[str, Any]:
    try:
        catalog = await qsar_client.list_all_qsar_models()
    except QsarClientError as exc:
        log.error("Failed to enumerate QSAR catalog: %s", exc)
        raise
    return {"catalog": catalog}


def register_discovery_tools() -> None:
    tool_registry.register(
        name="list_profilers",
        description="Returns the catalog of profilers available in the OECD QSAR Toolbox.",
        parameters_model=EmptyParams,
        implementation=list_profilers,
    )

    tool_registry.register(
        name="get_profiler_info",
        description="Retrieves metadata for a specific profiler (caption, categories, literature).",
        parameters_model=ProfilerInfoParams,
        implementation=get_profiler_info,
    )

    tool_registry.register(
        name="list_simulators",
        description="Lists available metabolism simulators exposed by the QSAR Toolbox.",
        parameters_model=EmptyParams,
        implementation=list_simulators,
    )

    tool_registry.register(
        name="get_simulator_info",
        description="Retrieves detailed information for a metabolism simulator (scope, donor, notes).",
        parameters_model=SimulatorInfoParams,
        implementation=get_simulator_info,
    )

    tool_registry.register(
        name="list_calculators",
        description="Lists calculator modules (physical properties) available in the QSAR Toolbox.",
        parameters_model=EmptyParams,
        implementation=list_calculators,
    )

    tool_registry.register(
        name="get_calculator_info",
        description="Retrieves metadata for a calculator, including units and description.",
        parameters_model=CalculatorInfoParams,
        implementation=get_calculator_info,
    )

    tool_registry.register(
        name="get_endpoint_tree",
        description="Returns the endpoint tree positions used to organize QSAR models and profilers.",
        parameters_model=EmptyParams,
        implementation=get_endpoint_tree,
    )

    tool_registry.register(
        name="get_metadata_hierarchy",
        description="Returns the metadata hierarchy used for filtering endpoints and records.",
        parameters_model=EmptyParams,
        implementation=get_metadata_hierarchy,
    )

    tool_registry.register(
        name="list_qsar_models",
        description="Lists QSAR models associated with a specific endpoint tree position.",
        parameters_model=QsarModelsParams,
        implementation=list_qsar_models,
    )

    tool_registry.register(
        name="list_all_qsar_models",
        description="Enumerates the QSAR model catalog across the entire endpoint tree (deduplicated).",
        parameters_model=EmptyParams,
        implementation=list_all_qsar_models,
    )


register_discovery_tools()
