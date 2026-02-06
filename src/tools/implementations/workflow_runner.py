import base64
import copy
import inspect
import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from src.integrations import oqt_assistant
from src.qsar import QsarClientError, qsar_client
from src.tools.registry import tool_registry
from src.utils.pdf_generator import generate_pdf_report

log = logging.getLogger(__name__)


class WorkflowParams(BaseModel):
    identifier: str = Field(
        ..., description="Chemical identifier (common name, CAS number, or SMILES)."
    )
    search_type: str = Field(
        "auto",
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

    @field_validator("search_type", mode="before")
    @classmethod
    def _normalise_search_type(cls, value: Any) -> str:
        if not value:
            return "auto"
        return str(value).strip().lower()

    @field_validator("qsar_mode", mode="before")
    @classmethod
    def _normalise_qsar_mode(cls, value: Any) -> str:
        if not value:
            return "recommended"
        return str(value).strip().lower()


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
    }
    entry.update({k: v for k, v in extra.items() if v is not None})
    return entry


def _aggregate_calls(calls: List[Dict[str, Any]]) -> Dict[str, Any]:
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
        summary_lines.append(f"* No Toolbox records matched `{identifier_display}`.")
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

    profiler_results: List[Dict[str, Any]] = []
    for profiler_guid in profiler_guids:
        try:
            payload, profiler_meta = await qsar_client.profile_with_profiler(
                profiler_guid, chem_id, None, with_meta=True
            )
            profiler_results.append({"profiler_guid": profiler_guid, "result": payload})
            entry = _format_meta(
                "profiling/execute", profiler_meta, profiler_guid=profiler_guid
            )
            if entry:
                toolbox_calls.append(entry)
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
            simulator_results.append(
                {"simulator_guid": simulator_guid, "result": payload}
            )
            entry = _format_meta(
                "metabolism/simulate",
                simulator_meta,
                simulator_guid=simulator_guid,
            )
            if entry:
                toolbox_calls.append(entry)
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
            qsar_results.append(
                {
                    "qsar_guid": qsar_guid,
                    "prediction": prediction,
                    "domain": domain,
                }
            )
            entry_apply = _format_meta("qsar/apply", apply_meta, qsar_guid=qsar_guid)
            entry_domain = _format_meta("qsar/domain", domain_meta, qsar_guid=qsar_guid)
            if entry_apply:
                toolbox_calls.append(entry_apply)
            if entry_domain:
                toolbox_calls.append(entry_domain)
        except QsarClientError as exc:
            message = f"QSAR model {qsar_guid} failed: {exc}"
            log.warning(message)
            log_bundle["errors"].append(message)

    if qsar_results:
        summary_lines.append(
            f"* Completed {len(qsar_results)} QSAR model run(s) for chemId `{chem_id}`."
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
            response["assistant"] = {"enabled": True, **assistant_meta}
            return response

    if assistant_config and assistant_error:
        summary_lines.append(f"* Assistant workflow unavailable: {assistant_error}.")
        log_bundle.setdefault("assistant", {})["error"] = assistant_error

    return _build_workflow_response(status, summary_lines, log_bundle, toolbox_meta)


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

    response = {
        "status": status,
        "identifier": log_bundle["inputs"]["identifier"],
        "summary_markdown": summary_markdown,
        "log_json": log_bundle,
        "pdf_report_base64": pdf_report_base64,
    }
    if toolbox_meta.get("calls"):
        response["toolbox"] = toolbox_meta
    return response


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


register_workflow_tool()
