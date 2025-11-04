import base64
import json
import logging
from typing import Any, Dict, Optional
import inspect

from pydantic import BaseModel, Field, model_validator

from src.qsar import QsarClientError, qsar_client
from src.tools.registry import tool_registry
from src.utils.pdf_generator import generate_pdf_report

log = logging.getLogger(__name__)


def _ensure_bytes(payload: Optional[object]) -> bytes:
    if payload is None:
        return b""
    if isinstance(payload, (bytes, bytearray)):
        return bytes(payload)
    if isinstance(payload, memoryview):
        return payload.tobytes()
    if isinstance(payload, str):
        return payload.encode("utf-8")
    if isinstance(payload, (dict, list)):
        return json.dumps(payload).encode("utf-8")
    raise TypeError("Unexpected binary payload type")


def _format_meta(label: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    if not meta:
        return None
    return {
        "endpoint": label,
        "attempts": meta.get("attempts"),
        "duration_ms": meta.get("duration_ms"),
        "timeout_profile": meta.get("timeout_profile"),
        "status_code": meta.get("status_code"),
    }


def _aggregate_meta(*entries: Dict[str, Any]) -> Dict[str, Any]:
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


class PdfFromLogParams(BaseModel):
    log: dict = Field(
        ..., description="Comprehensive log bundle captured from a prior workflow run."
    )
    filename: Optional[str] = Field(
        None,
        description="Optional filename hint for downstream consumers (not used server-side).",
    )


async def run_qsar_model(qsar_guid: str, chem_id: str) -> dict:
    try:
        prediction, apply_meta = await _invoke_with_meta(
            qsar_client.apply_qsar_model, qsar_guid, chem_id
        )
        domain, domain_meta = await _invoke_with_meta(
            qsar_client.get_qsar_domain, qsar_guid, chem_id
        )
    except QsarClientError as exc:
        log.error("QSAR apply failed: %s", exc)
        raise
    toolbox_meta = _aggregate_meta(
        _format_meta("qsar/apply", apply_meta),
        _format_meta("qsar/domain", domain_meta),
    )
    result = {
        "qsar_guid": qsar_guid,
        "chem_id": chem_id,
        "prediction": prediction,
        "domain": domain,
    }
    return _attach_toolbox(result, toolbox_meta)


async def run_profiler(
    profiler_guid: str, chem_id: str, simulator_guid: Optional[str] = None
) -> dict:
    try:
        result, meta = await _invoke_with_meta(
            qsar_client.profile_with_profiler, profiler_guid, chem_id, simulator_guid
        )
    except QsarClientError as exc:
        log.error("Profiler execution failed: %s", exc)
        raise
    result = {
        "profiler_guid": profiler_guid,
        "chem_id": chem_id,
        "simulator_guid": simulator_guid,
        "result": result,
    }
    toolbox_meta = _aggregate_meta(
        _format_meta("profiling/execute", meta),
    )
    return _attach_toolbox(result, toolbox_meta)


async def run_metabolism_simulator(
    simulator_guid: str, chem_id: Optional[str], smiles: Optional[str]
) -> dict:
    try:
        if chem_id:
            result, meta = await _invoke_with_meta(
                qsar_client.simulate_metabolites_for_chem, simulator_guid, chem_id
            )
        else:
            result, meta = await _invoke_with_meta(
                qsar_client.simulate_metabolites_for_smiles, simulator_guid, smiles or ""
            )
    except QsarClientError as exc:
        log.error("Metabolism simulator failed: %s", exc)
        raise
    result = {
        "simulator_guid": simulator_guid,
        "chem_id": chem_id,
        "smiles": smiles,
        "result": result,
    }
    toolbox_meta = _aggregate_meta(
        _format_meta("metabolism/simulate", meta),
    )
    return _attach_toolbox(result, toolbox_meta)


async def download_qmrf(qsar_guid: str, chem_id: str) -> dict:
    try:
        payload, meta = await _invoke_with_meta(
            qsar_client.generate_qmrf, qsar_guid
        )
    except QsarClientError as exc:
        log.error("QMRF retrieval failed: %s", exc)
        raise
    result = {
        "qsar_guid": qsar_guid,
        "chem_id": chem_id,
        "qmrf": payload,
    }
    toolbox_meta = _aggregate_meta(
        _format_meta("report/qmrf", meta),
    )
    return _attach_toolbox(result, toolbox_meta)


async def download_qsar_report(
    chem_id: str, qsar_guid: str, comments: Optional[str]
) -> dict:
    try:
        payload, meta = await _invoke_with_meta(
            qsar_client.generate_qsar_report, chem_id, qsar_guid, comments or ""
        )
    except QsarClientError as exc:
        log.error("QSAR report retrieval failed: %s", exc)
        raise
    pdf_bytes = _ensure_bytes(payload)
    encoded = base64.b64encode(pdf_bytes).decode("utf-8")
    result = {
        "chem_id": chem_id,
        "qsar_guid": qsar_guid,
        "report_base64": encoded,
        "size_bytes": len(pdf_bytes),
    }
    toolbox_meta = _aggregate_meta(
        _format_meta("report/qsar", meta),
    )
    return _attach_toolbox(result, toolbox_meta)


async def execute_workflow(workflow_guid: str, chem_id: str) -> dict:
    try:
        result, meta = await _invoke_with_meta(
            qsar_client.execute_workflow, workflow_guid, chem_id
        )
    except QsarClientError as exc:
        log.error("Workflow execution failed: %s", exc)
        raise
    result = {
        "workflow_guid": workflow_guid,
        "chem_id": chem_id,
        "result": result,
    }
    toolbox_meta = _aggregate_meta(
        _format_meta("workflows/execute", meta),
    )
    return _attach_toolbox(result, toolbox_meta)


async def download_workflow_report(
    chem_id: str, workflow_guid: str, comments: Optional[str]
) -> dict:
    try:
        payload, meta = await _invoke_with_meta(
            qsar_client.workflow_report, chem_id, workflow_guid, comments or ""
        )
    except QsarClientError as exc:
        log.error("Workflow report retrieval failed: %s", exc)
        raise
    pdf_bytes = _ensure_bytes(payload)
    encoded = base64.b64encode(pdf_bytes).decode("utf-8")
    result = {
        "chem_id": chem_id,
        "workflow_guid": workflow_guid,
        "report_base64": encoded,
        "size_bytes": len(pdf_bytes),
    }
    toolbox_meta = _aggregate_meta(
        _format_meta("report/workflow", meta),
    )
    return _attach_toolbox(result, toolbox_meta)


async def group_chemicals(chem_id: str, profiler_guid: str) -> dict:
    try:
        payload, meta = await _invoke_with_meta(
            qsar_client.group_by_profiler, chem_id, profiler_guid
        )
    except QsarClientError as exc:
        log.warning("Grouping failed for %s/%s: %s", chem_id, profiler_guid, exc)
        raise
    result = {
        "chem_id": chem_id,
        "profiler_guid": profiler_guid,
        "group": payload,
    }
    toolbox_meta = _aggregate_meta(
        _format_meta("grouping/profile", meta),
    )
    return _attach_toolbox(result, toolbox_meta)


async def canonicalize_structure(smiles: str) -> dict:
    try:
        payload, meta = await _invoke_with_meta(
            qsar_client.canonicalize_structure, smiles
        )
    except QsarClientError as exc:
        log.error("Structure canonicalization failed: %s", exc)
        raise
    result = {
        "smiles": smiles,
        "canonical": payload,
    }
    toolbox_meta = _aggregate_meta(
        _format_meta("structure/canonize", meta),
    )
    return _attach_toolbox(result, toolbox_meta)


async def structure_connectivity(smiles: str) -> dict:
    try:
        payload, meta = await _invoke_with_meta(
            qsar_client.get_connectivity, smiles
        )
    except QsarClientError as exc:
        log.error("Structure connectivity failed: %s", exc)
        raise
    result = {
        "smiles": smiles,
        "connectivity": payload,
    }
    toolbox_meta = _aggregate_meta(
        _format_meta("structure/connectivity", meta),
    )
    return _attach_toolbox(result, toolbox_meta)


async def render_pdf_from_log(log: dict, filename: Optional[str] = None) -> dict:
    try:
        pdf_payload = generate_pdf_report(log)
    except Exception as exc:  # pragma: no cover - passthrough to caller
        log.error("PDF generation from log failed: %s", exc)
        raise

    if hasattr(pdf_payload, "getvalue"):
        pdf_bytes = pdf_payload.getvalue()
    elif isinstance(pdf_payload, (bytes, bytearray, memoryview)):
        pdf_bytes = bytes(pdf_payload)
    else:  # pragma: no cover - safeguard
        raise TypeError("Unexpected payload produced by generate_pdf_report")

    encoded = base64.b64encode(pdf_bytes).decode("utf-8")
    return {
        "pdf_base64": encoded,
        "size_bytes": len(pdf_bytes),
        "filename": filename or "oqt_report.pdf",
    }


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

    tool_registry.register(
        name="render_pdf_from_log",
        description="Regenerates the regulatory PDF report from a stored log bundle (no Toolbox rerun).",
        parameters_model=PdfFromLogParams,
        implementation=render_pdf_from_log,
    )


register_execution_tools()
