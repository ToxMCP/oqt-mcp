import asyncio
import base64
import io
import json

import pytest

from src.tools.implementations import toolbox_execution as execution


def test_run_qsar_model(monkeypatch):
    async def fake_apply(qsar_guid, chem_id):
        return {"Value": 1.23}

    async def fake_domain(qsar_guid, chem_id):
        return "In Domain"

    monkeypatch.setattr(execution.qsar_client, "apply_qsar_model", fake_apply)
    monkeypatch.setattr(execution.qsar_client, "get_qsar_domain", fake_domain)

    result = asyncio.run(execution.run_qsar_model("model", "chem"))
    assert result["prediction"]["Value"] == 1.23
    assert result["domain"] == "In Domain"


def test_run_metabolism_simulator(monkeypatch):
    async def fake_sim(simulator_guid, chem_id):
        return ["metabolite"]

    monkeypatch.setattr(
        execution.qsar_client, "simulate_metabolites_for_chem", fake_sim
    )

    params = execution.SimulatorExecuteParams(
        simulator_guid="sim", chem_id="chem", smiles=None
    )
    result = asyncio.run(
        execution.run_metabolism_simulator(
            params.simulator_guid, params.chem_id, params.smiles
        )
    )
    assert result["result"] == ["metabolite"]


def test_canonicalize_structure(monkeypatch):
    async def fake_canon(smiles):
        return "C"  # canonical form

    monkeypatch.setattr(execution.qsar_client, "canonicalize_structure", fake_canon)

    result = asyncio.run(execution.canonicalize_structure("[CH3]"))
    assert result["canonical"] == "C"


def test_render_pdf_from_log(monkeypatch):
    fake_pdf = io.BytesIO(b"%PDF-1.4\n")

    monkeypatch.setattr(execution, "generate_pdf_report", lambda log: fake_pdf)

    result = asyncio.run(execution.render_pdf_from_log({"foo": "bar"}))
    assert result["size_bytes"] == len(b"%PDF-1.4\n")
    decoded = base64.b64decode(result["pdf_base64"])
    assert decoded == b"%PDF-1.4\n"


def test_run_profiler(monkeypatch):
    async def fake_profile(prof_guid, chem_id, simulator_guid=None):
        return {"result": "ok", "sim": simulator_guid}

    monkeypatch.setattr(execution.qsar_client, "profile_with_profiler", fake_profile)

    result = asyncio.run(execution.run_profiler("prof", "chem"))
    assert result["profiler_guid"] == "prof"
    assert result["result"]["result"] == "ok"


def test_run_profiler_with_simulator(monkeypatch):
    async def fake_profile(prof_guid, chem_id, simulator_guid=None):
        return {"sim": simulator_guid}

    monkeypatch.setattr(execution.qsar_client, "profile_with_profiler", fake_profile)

    result = asyncio.run(execution.run_profiler("prof", "chem", "sim"))
    assert result["simulator_guid"] == "sim"
    assert result["result"]["sim"] == "sim"


def test_run_metabolism_simulator_with_smiles(monkeypatch):
    async def fake_sim(simulator_guid, smiles):
        return ["metabolite"]

    monkeypatch.setattr(
        execution.qsar_client,
        "simulate_metabolites_for_smiles",
        fake_sim,
    )

    params = execution.SimulatorExecuteParams(
        simulator_guid="sim", chem_id=None, smiles="CCO"
    )
    result = asyncio.run(
        execution.run_metabolism_simulator(
            params.simulator_guid, params.chem_id, params.smiles
        )
    )
    assert result["smiles"] == "CCO"


def test_download_qmrf(monkeypatch):
    async def fake_qmrf(qsar_guid):
        return "QMRF"

    monkeypatch.setattr(execution.qsar_client, "generate_qmrf", fake_qmrf)

    result = asyncio.run(execution.download_qmrf("model", "chem"))
    assert result["qmrf"] == "QMRF"


def test_download_qsar_report(monkeypatch):
    async def fake_report(chem_id, qsar_guid, comments):
        return {"report": True, "comments": comments}

    monkeypatch.setattr(execution.qsar_client, "generate_qsar_report", fake_report)

    result = asyncio.run(execution.download_qsar_report("chem", "model", "note"))
    decoded = base64.b64decode(result["report_base64"]).decode("utf-8")
    payload = json.loads(decoded)
    assert payload["comments"] == "note"
    assert result["size_bytes"] > 0


def test_execute_workflow(monkeypatch):
    async def fake_workflow(workflow_guid, chem_id):
        return {"workflow": workflow_guid, "chem": chem_id}

    monkeypatch.setattr(execution.qsar_client, "execute_workflow", fake_workflow)

    result = asyncio.run(execution.execute_workflow("wf", "chem"))
    assert result["result"]["workflow"] == "wf"


def test_download_workflow_report(monkeypatch):
    async def fake_workflow_report(chem_id, workflow_guid, comments):
        return {"report": True, "comments": comments}

    monkeypatch.setattr(execution.qsar_client, "workflow_report", fake_workflow_report)

    result = asyncio.run(execution.download_workflow_report("chem", "wf", "note"))
    decoded = base64.b64decode(result["report_base64"]).decode("utf-8")
    payload = json.loads(decoded)
    assert payload["comments"] == "note"
    assert result["size_bytes"] > 0


def test_group_chemicals(monkeypatch):
    async def fake_group(chem_id, profiler_guid):
        return ["chemA", "chemB"]

    monkeypatch.setattr(execution.qsar_client, "group_by_profiler", fake_group)

    result = asyncio.run(execution.group_chemicals("chem", "prof"))
    assert result["group"] == ["chemA", "chemB"]


def test_structure_connectivity(monkeypatch):
    async def fake_conn(smiles):
        return "connect"

    monkeypatch.setattr(execution.qsar_client, "get_connectivity", fake_conn)

    result = asyncio.run(execution.structure_connectivity("CCO"))
    assert result["connectivity"] == "connect"
