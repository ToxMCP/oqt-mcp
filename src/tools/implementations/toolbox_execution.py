import logging
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from src.qsar import QsarClientError, qsar_client
from src.tools.registry import tool_registry

log = logging.getLogger(__name__)


class QsarApplyParams(BaseModel):
    qsar_guid: str = Field(..., description="GUID of the QSAR model to execute.")
    chem_id: str = Field(
        ..., description="Chemical identifier (chemId) registered in the Toolbox."
    )


class ProfilerExecuteParams(BaseModel):
    profiler_guid: str = Field(..., description="GUID of the profiler to execute.")
    chem_id: str = Field(..., description="Chemical identifier (chemId).")
    simulator_guid: Optional[str] = Field(
        None,
        description="Optional simulator GUID for profilers that depend on metabolites.",
    )


class SimulatorExecuteParams(BaseModel):
    simulator_guid: str = Field(
        ..., description="GUID of the metabolism simulator to execute."
    )
    chem_id: Optional[str] = Field(
        None, description="ChemId of a registered structure."
    )
    smiles: Optional[str] = Field(
        None, description="SMILES of the structure when no chemId exists."
    )

    @model_validator(mode="after")
    def ensure_inputs(self):
        if not self.chem_id and not self.smiles:
            raise ValueError("Provide either chem_id or smiles.")
        return self


class QsarReportParams(BaseModel):
    chem_id: str = Field(..., description="Chemical identifier (chemId).")
    qsar_guid: str = Field(..., description="GUID of the QSAR model")
    comments: Optional[str] = Field(
        "generated_via_mcp",
        description="Comments appended to the Toolbox report request.",
    )


class WorkflowExecuteParams(BaseModel):
    workflow_guid: str = Field(..., description="GUID of the Toolbox workflow")
    chem_id: str = Field(..., description="Chemical identifier (chemId)")


class WorkflowReportParams(BaseModel):
    chem_id: str = Field(..., description="Chemical identifier (chemId)")
    workflow_guid: str = Field(..., description="Workflow GUID")
    comments: Optional[str] = Field(
        "generated_via_mcp",
        description="Comments appended to the workflow report request.",
    )


class GroupingParams(BaseModel):
    chem_id: str = Field(..., description="Target chemical (chemId)")
    profiler_guid: str = Field(
        ..., description="Profiler GUID used to assemble similar chemicals"
    )


class StructureParams(BaseModel):
    smiles: str = Field(..., description="SMILES string to process.")


async def run_qsar_model(qsar_guid: str, chem_id: str) -> dict:
    try:
        prediction = await qsar_client.apply_qsar_model(qsar_guid, chem_id)
        domain = await qsar_client.get_qsar_domain(qsar_guid, chem_id)
    except QsarClientError as exc:
        log.error("QSAR apply failed: %s", exc)
        raise
    return {
        "qsar_guid": qsar_guid,
        "chem_id": chem_id,
        "prediction": prediction,
        "domain": domain,
    }


async def run_profiler(
    profiler_guid: str, chem_id: str, simulator_guid: Optional[str] = None
) -> dict:
    try:
        result = await qsar_client.profile_with_profiler(
            profiler_guid, chem_id, simulator_guid
        )
    except QsarClientError as exc:
        log.error("Profiler execution failed: %s", exc)
        raise
    return {
        "profiler_guid": profiler_guid,
        "chem_id": chem_id,
        "simulator_guid": simulator_guid,
        "result": result,
    }


async def run_metabolism_simulator(
    simulator_guid: str, chem_id: Optional[str], smiles: Optional[str]
) -> dict:
    try:
        if chem_id:
            result = await qsar_client.simulate_metabolites_for_chem(
                simulator_guid, chem_id
            )
        else:
            result = await qsar_client.simulate_metabolites_for_smiles(
                simulator_guid, smiles or ""
            )
    except QsarClientError as exc:
        log.error("Metabolism simulator failed: %s", exc)
        raise
    return {
        "simulator_guid": simulator_guid,
        "chem_id": chem_id,
        "smiles": smiles,
        "result": result,
    }


async def download_qmrf(qsar_guid: str, chem_id: str) -> dict:
    try:
        payload = await qsar_client.generate_qmrf(qsar_guid)
    except QsarClientError as exc:
        log.error("QMRF retrieval failed: %s", exc)
        raise
    return {"qsar_guid": qsar_guid, "chem_id": chem_id, "qmrf": payload}


async def download_qsar_report(
    chem_id: str, qsar_guid: str, comments: Optional[str]
) -> dict:
    try:
        payload = await qsar_client.generate_qsar_report(
            chem_id, qsar_guid, comments or ""
        )
    except QsarClientError as exc:
        log.error("QSAR report retrieval failed: %s", exc)
        raise
    return {"chem_id": chem_id, "qsar_guid": qsar_guid, "report": payload}


async def execute_workflow(workflow_guid: str, chem_id: str) -> dict:
    try:
        result = await qsar_client.execute_workflow(workflow_guid, chem_id)
    except QsarClientError as exc:
        log.error("Workflow execution failed: %s", exc)
        raise
    return {"workflow_guid": workflow_guid, "chem_id": chem_id, "result": result}


async def download_workflow_report(
    chem_id: str, workflow_guid: str, comments: Optional[str]
) -> dict:
    try:
        payload = await qsar_client.workflow_report(
            chem_id, workflow_guid, comments or ""
        )
    except QsarClientError as exc:
        log.error("Workflow report retrieval failed: %s", exc)
        raise
    return {"chem_id": chem_id, "workflow_guid": workflow_guid, "report": payload}


async def group_chemicals(chem_id: str, profiler_guid: str) -> dict:
    try:
        payload = await qsar_client.group_by_profiler(chem_id, profiler_guid)
    except QsarClientError as exc:
        log.error("Grouping failed: %s", exc)
        raise
    return {"chem_id": chem_id, "profiler_guid": profiler_guid, "group": payload}


async def canonicalize_structure(smiles: str) -> dict:
    try:
        payload = await qsar_client.canonicalize_structure(smiles)
    except QsarClientError as exc:
        log.error("Structure canonicalization failed: %s", exc)
        raise
    return {"smiles": smiles, "canonical": payload}


async def structure_connectivity(smiles: str) -> dict:
    try:
        payload = await qsar_client.get_connectivity(smiles)
    except QsarClientError as exc:
        log.error("Structure connectivity failed: %s", exc)
        raise
    return {"smiles": smiles, "connectivity": payload}


def register_execution_tools() -> None:
    tool_registry.register(
        name="run_qsar_model",
        description="Runs a QSAR model for a chemId and returns the Toolbox payload along with applicability domain notes.",
        parameters_model=QsarApplyParams,
        implementation=run_qsar_model,
    )

    tool_registry.register(
        name="run_profiler",
        description="Executes a specific profiler for a chemId (optionally providing a simulator GUID).",
        parameters_model=ProfilerExecuteParams,
        implementation=run_profiler,
    )

    tool_registry.register(
        name="run_metabolism_simulator",
        description="Runs a metabolism simulator using either a registered chemId or a SMILES string.",
        parameters_model=SimulatorExecuteParams,
        implementation=run_metabolism_simulator,
    )

    tool_registry.register(
        name="download_qmrf",
        description="Retrieves the QMRF document for a QSAR model.",
        parameters_model=QsarApplyParams,
        implementation=download_qmrf,
    )

    tool_registry.register(
        name="download_qsar_report",
        description="Retrieves the QSAR prediction report produced by the Toolbox.",
        parameters_model=QsarReportParams,
        implementation=download_qsar_report,
    )

    tool_registry.register(
        name="execute_workflow",
        description="Runs a Toolbox workflow for a chemId and returns the raw result.",
        parameters_model=WorkflowExecuteParams,
        implementation=execute_workflow,
    )

    tool_registry.register(
        name="download_workflow_report",
        description="Retrieves the report generated for a workflow execution.",
        parameters_model=WorkflowReportParams,
        implementation=download_workflow_report,
    )

    tool_registry.register(
        name="group_chemicals_by_profiler",
        description="Returns grouping results for the provided chemId using a profiler GUID (read-across helper).",
        parameters_model=GroupingParams,
        implementation=group_chemicals,
    )

    tool_registry.register(
        name="canonicalize_structure",
        description="Returns the canonical SMILES for a structure.",
        parameters_model=StructureParams,
        implementation=canonicalize_structure,
    )

    tool_registry.register(
        name="structure_connectivity",
        description="Returns the connectivity string for the supplied SMILES.",
        parameters_model=StructureParams,
        implementation=structure_connectivity,
    )


register_execution_tools()
