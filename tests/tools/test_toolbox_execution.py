import asyncio

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
