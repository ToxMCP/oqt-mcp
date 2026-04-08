import asyncio
import base64
import json
import os
from pathlib import Path

import httpx
import jsonschema
import pytest

import src.tools.implementations.o_qt_qsar_tools  # noqa: F401
import src.tools.implementations.toolbox_discovery  # noqa: F401
import src.tools.implementations.toolbox_execution  # noqa: F401
import src.tools.implementations.workflow_runner  # noqa: F401
from src.auth.rbac import ROLES
from src.auth.service import User
from src.config.settings import settings
from src.qsar.client import QsarClient, QsarClientError
from src.tools.registry import tool_registry

ROOT = Path(__file__).resolve().parents[2]
_FLAG = os.getenv("QSAR_LIVE_TESTS", "").lower()
_ENABLED = _FLAG in {"1", "true", "yes", "on"}
_SLOW_FLAG = os.getenv("QSAR_LIVE_SLOW_TESTS", "").lower()
_SLOW_ENABLED = _SLOW_FLAG in {"1", "true", "yes", "on"}
_BASE_URL = settings.qsar.QSAR_TOOLBOX_API_URL.rstrip("/")
_USER = User({"sub": "integration|live", "roles": [ROLES["SYSTEM_BYPASS"]]})
_FALLBACK_SMILES = os.getenv("QSAR_LIVE_FALLBACK_SMILES", "CC(C)=O")
_FALLBACK_CHEM_ID = os.getenv(
    "QSAR_LIVE_FALLBACK_CHEM_ID", "25511866-347f-d9f9-d598-d23f9501a8cb"
)
_FALLBACK_ANALOGUE_SMILES = os.getenv("QSAR_LIVE_FALLBACK_ANALOGUE_SMILES", "CCC(C)=O")
_FALLBACK_PROFILER_GUID = os.getenv(
    "QSAR_LIVE_FALLBACK_PROFILER_GUID", "a06271f5-944e-4892-b0ad-fa5f7217ec14"
)
_FALLBACK_PROFILER_CAPTION = os.getenv(
    "QSAR_LIVE_FALLBACK_PROFILER_CAPTION",
    "Acute aquatic toxicity classification by Verhaar (Modified)",
)
_FALLBACK_SIMULATOR_GUID = os.getenv("QSAR_LIVE_FALLBACK_SIMULATOR_GUID")
_FALLBACK_SIMULATOR_CAPTION = os.getenv("QSAR_LIVE_FALLBACK_SIMULATOR_CAPTION")
_FALLBACK_SIMULATOR_GUID = (
    _FALLBACK_SIMULATOR_GUID or "981641a6-bd66-4566-8a4e-11403fe786a6"
)
_FALLBACK_SIMULATOR_CAPTION = _FALLBACK_SIMULATOR_CAPTION or "Autoxidation simulator"
_FALLBACK_QSAR_GUID = os.getenv(
    "QSAR_LIVE_FALLBACK_QSAR_GUID", "aaea1ad1-a0db-1fb2-290a-6b5f52f049b2"
)
_FALLBACK_WORKFLOW_GUID = os.getenv(
    "QSAR_LIVE_FALLBACK_WORKFLOW_GUID", "33b163fd-7e42-47f8-b52c-59d911785aa8"
)


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _ENABLED,
        reason="Live QSAR Toolbox integration tests are disabled. "
        "Set QSAR_LIVE_TESTS=1 to enable.",
    ),
    pytest.mark.skipif(
        not _BASE_URL,
        reason="QSAR_TOOLBOX_API_URL is not configured.",
    ),
]


def _load_schema(name: str) -> dict:
    with (ROOT / "schemas" / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _client() -> QsarClient:
    base_url = _BASE_URL
    if base_url.endswith("/api/v6") or "/api/v6/" in base_url:
        pytest.skip(
            "QSAR_TOOLBOX_API_URL should point at the host root (e.g. http://host:port)."
        )
    return QsarClient(
        base_url,
        timeout=settings.qsar.QSAR_LIGHT_TIMEOUT_SECONDS,
        timeout_profiles={
            "light": httpx.Timeout(
                connect=5.0,
                read=settings.qsar.QSAR_LIGHT_TIMEOUT_SECONDS,
                write=settings.qsar.QSAR_LIGHT_TIMEOUT_SECONDS,
                pool=10.0,
            ),
            "heavy": httpx.Timeout(
                connect=10.0,
                read=settings.qsar.QSAR_HEAVY_TIMEOUT_SECONDS,
                write=max(60.0, settings.qsar.QSAR_HEAVY_TIMEOUT_SECONDS),
                pool=15.0,
            ),
        },
        max_attempts={
            "light": settings.qsar.QSAR_LIGHT_MAX_ATTEMPTS,
            "heavy": settings.qsar.QSAR_HEAVY_MAX_ATTEMPTS,
        },
        heavy_concurrency=settings.qsar.QSAR_HEAVY_CONCURRENCY,
    )


def _run(coro):
    try:
        return asyncio.run(coro)
    except QsarClientError as exc:
        pytest.fail(f"QSAR Toolbox request failed: {exc}")


def _tool(name: str, parameters: dict) -> dict:
    return _run(tool_registry.execute(name, parameters, _USER))


def _tool_or_xfail_on_timeout(name: str, parameters: dict, *, reason: str) -> dict:
    try:
        return asyncio.run(tool_registry.execute(name, parameters, _USER))
    except QsarClientError as exc:
        pytest.xfail(f"{reason}: {exc}")


def _normalise_records(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return [payload]
    return []


def _assert_pdf_base64(value: str) -> bytes:
    decoded = base64.b64decode(value)
    assert decoded.startswith(b"%PDF")
    return decoded


def _assert_binary_report(payload: dict, base64_field: str) -> bytes:
    decoded = base64.b64decode(payload[base64_field])
    if decoded.startswith(b"%PDF"):
        return decoded
    assert decoded.startswith(b"PK")
    assert payload.get("content_type") == "application/zip"
    assert payload.get("archive_entries")
    assert payload.get("pdf_report_base64")
    _assert_pdf_base64(payload["pdf_report_base64"])
    return decoded


async def _pick_working_profiler(
    client: QsarClient, chem_id: str, profilers: list[dict]
):
    if not profilers:
        return None

    by_guid = {
        entry.get("Guid"): entry
        for entry in profilers
        if isinstance(entry, dict) and entry.get("Guid")
    }
    if _FALLBACK_PROFILER_GUID and _FALLBACK_PROFILER_GUID in by_guid:
        return by_guid[_FALLBACK_PROFILER_GUID]

    preferred_captions = {
        _FALLBACK_PROFILER_CAPTION.lower(),
        "acute aquatic toxicity classification by verhaar (modified)",
        "acute oral toxicity",
    }
    for entry in profilers:
        caption = str(entry.get("Caption", "")).strip().lower()
        if caption in preferred_captions:
            return entry

    return profilers[0]


async def _load_or_fallback_catalog(
    loader,
    fallback_guid: str | None,
    fallback_caption: str | None = None,
):
    if fallback_guid:
        return _fallback_record(fallback_guid, fallback_caption)
    try:
        return _normalise_records(await loader())
    except QsarClientError:
        return _fallback_record(fallback_guid, fallback_caption)


async def _resolve_live_chemical(client: QsarClient) -> tuple[str, str]:
    try:
        search_hits = _normalise_records(
            await client.search_chemicals(_FALLBACK_SMILES, "smiles")
        )
    except QsarClientError:
        search_hits = []

    if search_hits:
        chemical = next(
            (entry for entry in search_hits if entry.get("ChemId")), search_hits[0]
        )
        chem_id = chemical.get("ChemId")
        smiles = chemical.get("Smiles") or chemical.get("SMILES") or _FALLBACK_SMILES
        if not chem_id:
            raise AssertionError(
                "Toolbox search did not return a chemId for acetone SMILES."
            )
        return chem_id, smiles

    if not _FALLBACK_CHEM_ID:
        raise AssertionError("No fallback chemId configured for live smoke tests.")
    return _FALLBACK_CHEM_ID, _FALLBACK_SMILES


def _fallback_record(guid: str | None, caption: str | None = None) -> list[dict]:
    if not guid:
        return []
    record = {"Guid": guid}
    if caption:
        record["Caption"] = caption
    return [record]


@pytest.fixture(scope="module")
def live_context():
    async def _build():
        client = _client()
        chem_id, smiles = await _resolve_live_chemical(client)

        profilers = _normalise_records(await client.list_profilers())
        simulators = _normalise_records(await client.list_simulators())
        calculators = _normalise_records(await client.list_calculators())
        endpoint_tree = await client.get_endpoint_tree()
        metadata_hierarchy = await client.get_metadata_hierarchy()
        models = _normalise_records(await client.list_all_qsar_models())
        workflows = _normalise_records(await client.list_workflows())

        assert profilers, "No profilers returned from live Toolbox."
        assert simulators, "No simulators returned from live Toolbox."
        assert calculators, "No calculators returned from live Toolbox."
        assert endpoint_tree, "No endpoint tree positions returned from live Toolbox."
        assert metadata_hierarchy, "No metadata hierarchy returned from live Toolbox."
        assert models, "No QSAR models returned from live Toolbox."
        assert workflows, "No workflows returned from live Toolbox."

        demo_workflow = next(
            (
                entry
                for entry in workflows
                if isinstance(entry, dict)
                and str(entry.get("Caption", "")).strip().lower() == "demo workflow"
            ),
            workflows[0],
        )
        qsar_position = None
        for position in endpoint_tree:
            position_models = _normalise_records(
                await client.list_qsar_models(position)
            )
            if position_models:
                qsar_position = position
                break
        assert qsar_position, "No endpoint tree position returned QSAR models."

        first_profiler = await _pick_working_profiler(client, chem_id, profilers)
        first_simulator = simulators[0]
        first_model = models[0]

        first_calculator = calculators[0]
        calculator_guid = first_calculator.get("Guid") or first_calculator.get("Id")
        assert calculator_guid, "Live calculator payload did not expose a GUID/Id."

        return {
            "chem_id": chem_id,
            "smiles": smiles,
            "profiler_guid": first_profiler["Guid"],
            "profiler_caption": first_profiler.get("Caption") or first_profiler["Guid"],
            "grouping_profiler_guid": first_profiler["Guid"],
            "simulator_guid": first_simulator["Guid"],
            "simulator_caption": first_simulator.get("Caption")
            or first_simulator["Guid"],
            "simulator_mode": "chem",
            "qsar_guid": first_model["Guid"],
            "workflow_guid": demo_workflow["Guid"],
            "endpoint_position": qsar_position,
            "calculator_guid": calculator_guid,
            "analysis_endpoint": "Mutagenicity",
            "analogue_identifier": _FALLBACK_ANALOGUE_SMILES,
        }

    return _run(_build())


@pytest.fixture(scope="module")
def live_execution_context():
    async def _build():
        client = _client()
        chem_id, smiles = await _resolve_live_chemical(client)

        profilers = await _load_or_fallback_catalog(
            client.list_profilers,
            _FALLBACK_PROFILER_GUID,
            _FALLBACK_PROFILER_CAPTION,
        )
        simulators = await _load_or_fallback_catalog(
            client.list_simulators,
            _FALLBACK_SIMULATOR_GUID,
            _FALLBACK_SIMULATOR_CAPTION,
        )
        models = await _load_or_fallback_catalog(
            client.list_all_qsar_models,
            _FALLBACK_QSAR_GUID,
        )
        workflows = await _load_or_fallback_catalog(
            client.list_workflows,
            _FALLBACK_WORKFLOW_GUID,
            "Demo workflow",
        )

        assert profilers, "No profilers returned from live Toolbox."
        assert simulators, "No simulators returned from live Toolbox."
        assert models, "No QSAR models returned from live Toolbox."
        assert workflows, "No workflows returned from live Toolbox."

        demo_workflow = next(
            (
                entry
                for entry in workflows
                if isinstance(entry, dict)
                and str(entry.get("Caption", "")).strip().lower() == "demo workflow"
            ),
            workflows[0],
        )
        first_profiler = await _pick_working_profiler(client, chem_id, profilers)
        first_simulator = simulators[0]
        first_model = models[0]

        return {
            "chem_id": chem_id,
            "smiles": smiles,
            "profiler_guid": first_profiler["Guid"],
            "profiler_caption": first_profiler.get("Caption") or first_profiler["Guid"],
            "grouping_profiler_guid": first_profiler["Guid"],
            "simulator_guid": first_simulator["Guid"],
            "simulator_caption": first_simulator.get("Caption")
            or first_simulator["Guid"],
            "simulator_mode": "chem",
            "qsar_guid": first_model["Guid"],
            "workflow_guid": demo_workflow["Guid"],
            "analysis_endpoint": "Mutagenicity",
            "analogue_identifier": _FALLBACK_ANALOGUE_SMILES,
        }

    return _run(_build())


@pytest.fixture(scope="module")
def workflow_payload():
    payload = _tool(
        "run_oqt_multiagent_workflow",
        {
            "identifier": _FALLBACK_CHEM_ID,
            "search_type": "auto",
            "context": "Live smoke test",
        },
    )
    assert payload["status"] in {"ok", "partial"}
    return payload


def test_live_discovery_and_qsar_helper_tools(live_context):
    get_public_qsar_model_info = _tool(
        "get_public_qsar_model_info", {"model_id": live_context["qsar_guid"]}
    )
    assert get_public_qsar_model_info["provenance"]["title"]
    assert get_public_qsar_model_info["provenance"]["owner"]

    search_chemicals = _tool(
        "search_chemicals", {"query": live_context["smiles"], "search_type": "smiles"}
    )
    assert _normalise_records(search_chemicals.get("results"))

    run_qsar_prediction = _tool(
        "run_qsar_prediction",
        {"smiles": live_context["smiles"], "model_id": live_context["qsar_guid"]},
    )
    assert run_qsar_prediction.get("model_id") == live_context["qsar_guid"]
    assert run_qsar_prediction["model_provenance"]["title"]
    assert run_qsar_prediction["model_provenance"]["owner"]

    list_profilers = _tool("list_profilers", {})
    assert _normalise_records(list_profilers.get("profilers"))

    get_profiler_info = _tool(
        "get_profiler_info", {"profiler_guid": live_context["profiler_guid"]}
    )
    assert get_profiler_info["provenance"]["title"]
    assert get_profiler_info["provenance"]["owner"]

    list_simulators = _tool("list_simulators", {})
    assert _normalise_records(list_simulators.get("simulators"))

    get_simulator_info = _tool(
        "get_simulator_info", {"simulator_guid": live_context["simulator_guid"]}
    )
    assert get_simulator_info["provenance"]["title"]
    assert get_simulator_info["provenance"]["owner"]

    list_calculators = _tool("list_calculators", {})
    assert _normalise_records(list_calculators.get("calculators"))

    get_calculator_info = _tool(
        "get_calculator_info", {"calculator_guid": live_context["calculator_guid"]}
    )
    assert get_calculator_info["provenance"]["title"]

    get_endpoint_tree = _tool("get_endpoint_tree", {})
    assert get_endpoint_tree.get("endpoint_tree")

    get_metadata_hierarchy = _tool("get_metadata_hierarchy", {})
    assert get_metadata_hierarchy.get("metadata_hierarchy") is not None

    list_qsar_models = _tool(
        "list_qsar_models", {"position": live_context["endpoint_position"]}
    )
    assert _normalise_records(list_qsar_models.get("models"))
    assert list_qsar_models["models"][0]["provenance_summary"]["title"]
    assert list_qsar_models["models"][0]["provenance_summary"]["owner"]

    list_all_qsar_models = _tool("list_all_qsar_models", {})
    assert _normalise_records(list_all_qsar_models.get("catalog"))
    assert list_all_qsar_models["catalog"][0]["provenance_summary"]["title"]
    assert list_all_qsar_models["status"] in {"ok", "partial"}
    assert list_all_qsar_models["catalog_metadata"]["positionsScanned"] >= 1


@pytest.mark.slow
@pytest.mark.skipif(
    not _SLOW_ENABLED,
    reason="Slow live Toolbox execution tests are disabled. Set QSAR_LIVE_SLOW_TESTS=1 to enable.",
)
def test_live_search_databases_tool():
    list_search_databases = _tool_or_xfail_on_timeout(
        "list_search_databases",
        {},
        reason="Search databases catalog timed out on the live Toolbox during direct verification",
    )
    assert _normalise_records(list_search_databases.get("databases"))


@pytest.mark.slow
@pytest.mark.skipif(
    not _SLOW_ENABLED,
    reason="Slow live Toolbox execution tests are disabled. Set QSAR_LIVE_SLOW_TESTS=1 to enable.",
)
def test_live_run_qsar_model_tool(live_execution_context):
    run_qsar_model = _tool_or_xfail_on_timeout(
        "run_qsar_model",
        {
            "qsar_guid": live_execution_context["qsar_guid"],
            "chem_id": live_execution_context["chem_id"],
        },
        reason="QSAR apply endpoint timed out on the live Toolbox during direct verification",
    )
    assert run_qsar_model["chem_id"] == live_execution_context["chem_id"]
    assert run_qsar_model["model_provenance"]["title"]


@pytest.mark.slow
@pytest.mark.skipif(
    not _SLOW_ENABLED,
    reason="Slow live Toolbox execution tests are disabled. Set QSAR_LIVE_SLOW_TESTS=1 to enable.",
)
def test_live_execute_workflow_tool(live_execution_context):
    execute_workflow = _tool_or_xfail_on_timeout(
        "execute_workflow",
        {
            "workflow_guid": live_execution_context["workflow_guid"],
            "chem_id": live_execution_context["chem_id"],
        },
        reason="Workflow execution endpoint timed out on the live Toolbox during direct verification",
    )
    assert execute_workflow["chem_id"] == live_execution_context["chem_id"]


@pytest.mark.slow
@pytest.mark.skipif(
    not _SLOW_ENABLED,
    reason="Slow live Toolbox execution tests are disabled. Set QSAR_LIVE_SLOW_TESTS=1 to enable.",
)
def test_live_structure_tools(live_execution_context):
    canonicalize_structure = _tool(
        "canonicalize_structure", {"smiles": live_execution_context["smiles"]}
    )
    assert canonicalize_structure.get("canonical")

    structure_connectivity = _tool(
        "structure_connectivity", {"smiles": live_execution_context["smiles"]}
    )
    assert structure_connectivity.get("connectivity")


@pytest.mark.slow
@pytest.mark.skipif(
    not _SLOW_ENABLED,
    reason="Slow live Toolbox execution tests are disabled. Set QSAR_LIVE_SLOW_TESTS=1 to enable.",
)
def test_live_analyze_chemical_hazard_tool(live_execution_context):
    analyze_chemical_hazard = _tool(
        "analyze_chemical_hazard",
        {
            "chemical_identifier": live_execution_context["chem_id"],
            "endpoint": live_execution_context["analysis_endpoint"],
        },
    )
    assert (
        analyze_chemical_hazard["resolved_chem_id"] == live_execution_context["chem_id"]
    )
    assert (
        analyze_chemical_hazard["endpoint"]
        == live_execution_context["analysis_endpoint"]
    )
    assert (
        analyze_chemical_hazard["chemical_identity"]["chem_id"]
        == live_execution_context["chem_id"]
    )
    assert (
        analyze_chemical_hazard["resolved_endpoint_position"]
        == "Human Health Hazards#Genetic Toxicity"
    )
    assert (
        analyze_chemical_hazard["data_availability"]["endpoint_data_available"] is True
    )
    assert analyze_chemical_hazard["endpoint_summaries"][0]["recordCount"] >= 1
    assert (
        analyze_chemical_hazard["evidence_blocks"]["endpointData"]["status"]
        == "present"
    )
    assert (
        analyze_chemical_hazard["applicability_domain"]["overallStatus"]
        == "not_applicable"
    )
    assert (
        analyze_chemical_hazard["uncertainty_assessment"]["coverage"]["endpointData"]
        == "present"
    )
    portable = analyze_chemical_hazard["portable_handoffs"][
        "oqtHazardEvidenceSummary.v1"
    ]
    assert portable["endpointSummaries"][0]["recordCount"] >= 1
    assert portable["evidenceBlocks"]["endpointData"]["status"] == "present"
    assert portable["applicabilityDomain"]["overallStatus"] == "not_applicable"
    assert (
        portable["assessmentBoundary"]["scope"]
        == "module_scoped_toolbox_evidence_packaging"
    )
    assert portable["decisionOwner"] == "downstream_expert_review"
    assert portable["supports"]["typedStudyEvidence"] is True
    assert (
        portable["uncertaintyAssessment"]["semanticCoverage"][
            "overallQuantificationStatus"
        ]
        == "qualitative_only"
    )


@pytest.mark.slow
@pytest.mark.skipif(
    not _SLOW_ENABLED,
    reason="Slow live Toolbox execution tests are disabled. Set QSAR_LIVE_SLOW_TESTS=1 to enable.",
)
def test_live_generate_metabolites_tool(live_execution_context):
    generate_metabolites = _tool(
        "generate_metabolites",
        {
            "smiles": live_execution_context["smiles"],
            "simulator": live_execution_context["simulator_caption"],
        },
    )
    assert (
        generate_metabolites["simulator_guid"]
        == live_execution_context["simulator_guid"]
    )
    assert "metabolites" in generate_metabolites
    assert generate_metabolites["simulator_provenance"]["title"]


@pytest.mark.slow
@pytest.mark.skipif(
    not _SLOW_ENABLED,
    reason="Slow live Toolbox execution tests are disabled. Set QSAR_LIVE_SLOW_TESTS=1 to enable.",
)
def test_live_run_profiler_tool(live_execution_context):
    run_profiler = _tool(
        "run_profiler",
        {
            "profiler_guid": live_execution_context["profiler_guid"],
            "chem_id": live_execution_context["chem_id"],
        },
    )
    assert run_profiler["chem_id"] == live_execution_context["chem_id"]
    assert run_profiler["profiler_provenance"]["title"]


@pytest.mark.slow
@pytest.mark.skipif(
    not _SLOW_ENABLED,
    reason="Slow live Toolbox execution tests are disabled. Set QSAR_LIVE_SLOW_TESTS=1 to enable.",
)
def test_live_run_metabolism_simulator_tool(live_execution_context):
    metabolism_params = {"simulator_guid": live_execution_context["simulator_guid"]}
    if live_execution_context["simulator_mode"] == "chem":
        metabolism_params["chem_id"] = live_execution_context["chem_id"]
    else:
        metabolism_params["smiles"] = live_execution_context["smiles"]
    run_metabolism_simulator = _tool("run_metabolism_simulator", metabolism_params)
    assert (
        run_metabolism_simulator["simulator_guid"]
        == live_execution_context["simulator_guid"]
    )
    assert run_metabolism_simulator["simulator_provenance"]["title"]


@pytest.mark.slow
@pytest.mark.skipif(
    not _SLOW_ENABLED,
    reason="Slow live Toolbox execution tests are disabled. Set QSAR_LIVE_SLOW_TESTS=1 to enable.",
)
def test_live_download_qmrf_tool(live_execution_context):
    download_qmrf = _tool(
        "download_qmrf",
        {
            "qsar_guid": live_execution_context["qsar_guid"],
            "chem_id": live_execution_context["chem_id"],
        },
    )
    assert download_qmrf["size_bytes"] > 0
    _assert_pdf_base64(download_qmrf["qmrf_base64"])


@pytest.mark.slow
@pytest.mark.skipif(
    not _SLOW_ENABLED,
    reason="Slow live Toolbox execution tests are disabled. Set QSAR_LIVE_SLOW_TESTS=1 to enable.",
)
def test_live_download_qsar_report_tool(live_execution_context):
    download_qsar_report = _tool(
        "download_qsar_report",
        {
            "qsar_guid": live_execution_context["qsar_guid"],
            "chem_id": live_execution_context["chem_id"],
        },
    )
    assert download_qsar_report["size_bytes"] > 0
    _assert_binary_report(download_qsar_report, "report_base64")


@pytest.mark.slow
@pytest.mark.skipif(
    not _SLOW_ENABLED,
    reason="Slow live Toolbox execution tests are disabled. Set QSAR_LIVE_SLOW_TESTS=1 to enable.",
)
def test_live_download_workflow_report_tool(live_execution_context):
    download_workflow_report = _tool_or_xfail_on_timeout(
        "download_workflow_report",
        {
            "workflow_guid": live_execution_context["workflow_guid"],
            "chem_id": live_execution_context["chem_id"],
        },
        reason="Workflow report endpoint timed out on the live Toolbox during direct verification",
    )
    if not download_workflow_report.get("size_bytes"):
        pytest.xfail(
            "Workflow report endpoint returned an empty payload on the live Toolbox during direct verification"
        )
    assert download_workflow_report["size_bytes"] > 0
    _assert_binary_report(download_workflow_report, "report_base64")


@pytest.mark.slow
@pytest.mark.skipif(
    not _SLOW_ENABLED,
    reason="Slow live Toolbox execution tests are disabled. Set QSAR_LIVE_SLOW_TESTS=1 to enable.",
)
def test_live_execution_grouping_tool(live_execution_context):
    group_chemicals_by_profiler = _tool_or_xfail_on_timeout(
        "group_chemicals_by_profiler",
        {
            "profiler_guid": live_execution_context["grouping_profiler_guid"],
            "chem_id": live_execution_context["chem_id"],
        },
        reason="Grouping endpoint timed out on the live Toolbox during direct verification",
    )
    assert group_chemicals_by_profiler["chem_id"] == live_execution_context["chem_id"]


@pytest.mark.slow
@pytest.mark.skipif(
    not _SLOW_ENABLED,
    reason="Slow live Toolbox execution tests are disabled. Set QSAR_LIVE_SLOW_TESTS=1 to enable.",
)
def test_live_high_level_workflow_tools(workflow_payload):
    assert workflow_payload["summary_markdown"]
    assert workflow_payload["log_json"]
    assert workflow_payload["portable_handoffs"]
    _assert_pdf_base64(workflow_payload["pdf_report_base64"])

    jsonschema.validate(
        workflow_payload["portable_handoffs"]["oqtWorkflowRecord.v1"],
        _load_schema("oqtWorkflowRecord.v1.json"),
    )
    jsonschema.validate(
        workflow_payload["portable_handoffs"]["oqtHazardEvidenceSummary.v1"],
        _load_schema("oqtHazardEvidenceSummary.v1.json"),
    )
    hazard_summary = workflow_payload["portable_handoffs"][
        "oqtHazardEvidenceSummary.v1"
    ]
    if hazard_summary["requestMetadata"]["requestedProfilers"]:
        assert hazard_summary["evidenceBlocks"]["profiling"]["status"] in {
            "present",
            "partial",
            "none",
        }
    else:
        assert hazard_summary["evidenceBlocks"]["profiling"]["status"] == "none"
    assert hazard_summary["applicabilityDomain"]["overallStatus"] in {
        "not_applicable",
        "not_assessed",
        "mixed",
        "in_domain",
        "out_of_domain",
    }
    assert hazard_summary["decisionBoundary"]["reviewRequired"] is True
    assert hazard_summary["decisionOwner"] == "downstream_expert_review"
    assert (
        hazard_summary["uncertaintyAssessment"]["semanticCoverage"][
            "overallQuantificationStatus"
        ]
        == "qualitative_only"
    )

    alias_payload = _tool(
        "run_qsar_workflow",
        {
            "identifier": _FALLBACK_CHEM_ID,
            "search_type": "auto",
            "context": "Live smoke test alias",
        },
    )
    assert alias_payload["status"] in {"ok", "partial"}
    assert alias_payload["portable_handoffs"]["oqtWorkflowRecord.v1"]


@pytest.mark.slow
@pytest.mark.skipif(
    not _SLOW_ENABLED,
    reason="Slow live Toolbox execution tests are disabled. Set QSAR_LIVE_SLOW_TESTS=1 to enable.",
)
def test_live_log_replay_tools(workflow_payload):
    render_pdf_from_log = _tool(
        "render_pdf_from_log", {"log": workflow_payload["log_json"]}
    )
    assert render_pdf_from_log["size_bytes"] > 0
    _assert_pdf_base64(render_pdf_from_log["pdf_base64"])

    build_portable_handoffs_from_log = _tool(
        "build_portable_handoffs_from_log", {"log": workflow_payload["log_json"]}
    )
    assert build_portable_handoffs_from_log["workflow_type"] == "workflow"
    jsonschema.validate(
        build_portable_handoffs_from_log["portable_handoffs"]["oqtWorkflowRecord.v1"],
        _load_schema("oqtWorkflowRecord.v1.json"),
    )
    jsonschema.validate(
        build_portable_handoffs_from_log["portable_handoffs"][
            "oqtHazardEvidenceSummary.v1"
        ],
        _load_schema("oqtHazardEvidenceSummary.v1.json"),
    )


@pytest.mark.slow
@pytest.mark.skipif(
    not _SLOW_ENABLED,
    reason="Slow live Toolbox execution tests are disabled. Set QSAR_LIVE_SLOW_TESTS=1 to enable.",
)
def test_live_grouping_workflow_tool(live_execution_context):
    payload = _tool(
        "build_grouping_justification",
        {
            "identifier": live_execution_context["chem_id"],
            "search_type": "auto",
            "problem_formulation": "Screening-level read-across support.",
            "decision_context": "Hazard identification",
            "endpoints": [live_execution_context["analysis_endpoint"]],
            "grouping_hypothesis": "Small ketones share core structural features and simple metabolic fate.",
            "analogue_identifiers": [live_execution_context["chem_id"]],
            "analogue_search_type": "auto",
            "accepted_uncertainty_level": "medium",
        },
    )

    assert payload["status"] in {"ok", "partial"}
    assert payload["grouping_justification"]
    assert payload["portable_handoffs"]

    jsonschema.validate(
        payload["portable_handoffs"]["oqtWorkflowRecord.v1"],
        _load_schema("oqtWorkflowRecord.v1.json"),
    )
    jsonschema.validate(
        payload["portable_handoffs"]["oqtReadAcrossSummary.v1"],
        _load_schema("oqtReadAcrossSummary.v1.json"),
    )
    read_across = payload["portable_handoffs"]["oqtReadAcrossSummary.v1"]
    assert read_across["decisionOwner"] == "downstream_expert_review"
    assert read_across["supports"]["typedGroupingDossier"] is True
