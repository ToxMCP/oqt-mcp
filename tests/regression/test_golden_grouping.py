import asyncio
import io

import pytest

from src.tools.implementations import workflow_runner
from tests.regression._helpers import load_snapshot, normalize_for_snapshot, save_snapshot


def _stub_pdf(*_args, **_kwargs):
    return io.BytesIO(b"%PDF-1.4\n")


@pytest.fixture
def monkeypatch_qsar_client(monkeypatch):
    async def fake_search(identifier, search_type, with_meta=False):
        payload_map = {
            "Benzene": {
                "ChemId": "chem-benzene",
                "Cas": "71-43-2",
                "Names": ["Benzene"],
                "Smiles": "c1ccccc1",
            },
            "Toluene": {
                "ChemId": "chem-toluene",
                "Cas": "108-88-3",
                "Names": ["Toluene"],
                "Smiles": "Cc1ccccc1",
            },
            "Ethylbenzene": {
                "ChemId": "chem-ethylbenzene",
                "Cas": "100-41-4",
                "Names": ["Ethylbenzene"],
                "Smiles": "CCc1ccccc1",
            },
        }
        payload = [payload_map.get(identifier, {"ChemId": "chem-unknown", "Names": [identifier]})]
        meta = {"duration_ms": 12.0, "status_code": 200, "api_versions": "6.0", "server_date": "Mon, 16 Apr 2026 10:00:00 GMT"}
        return (payload, meta) if with_meta else payload

    async def fake_canonicalize(smiles, with_meta=False):
        payload = smiles
        meta = {"duration_ms": 3.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    async def fake_connectivity(smiles, with_meta=False):
        payload = f"connectivity:{smiles}"
        meta = {"duration_ms": 4.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    async def fake_profile(profiler_guid, chem_id, simulator_guid=None, with_meta=False):
        payload = {"classification": "aromatic hydrocarbon", "chem_id": chem_id}
        meta = {"duration_ms": 10.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    async def fake_group_by_profiler(chem_id, profiler_guid, with_meta=False):
        payload = {"members": [chem_id], "profiler_guid": profiler_guid}
        meta = {"duration_ms": 9.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    async def fake_simulator(simulator_guid, chem_id, with_meta=False):
        payload = [{"name": "Metabolite A", "chem_id": chem_id}]
        meta = {"duration_ms": 8.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    async def fake_qsar(qsar_guid, chem_id, with_meta=False):
        payload = {"value": 0.77, "chem_id": chem_id}
        meta = {"duration_ms": 11.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    async def fake_domain(qsar_guid, chem_id, with_meta=False):
        payload = {"status": "in_domain", "chem_id": chem_id}
        meta = {"duration_ms": 5.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    async def fake_profiler_info(profiler_guid, with_meta=False):
        payload = {"Guid": profiler_guid, "_name": "Grouping profiler", "_donator": "OECD"}
        meta = {"duration_ms": 4.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    async def fake_simulator_info(simulator_guid, with_meta=False):
        payload = {"Guid": simulator_guid, "_name": "Rat liver", "_donator": "OECD"}
        meta = {"duration_ms": 4.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    async def fake_model_info(qsar_guid, with_meta=False):
        payload = {"Guid": qsar_guid, "Name": "Repeated-dose model", "Donator": "EPA"}
        meta = {"duration_ms": 4.0, "status_code": 200}
        return (payload, meta) if with_meta else payload

    monkeypatch.setattr(workflow_runner, "generate_pdf_report", _stub_pdf)
    monkeypatch.setattr(workflow_runner.qsar_client, "search_chemicals", fake_search)
    monkeypatch.setattr(
        workflow_runner.qsar_client, "canonicalize_structure", fake_canonicalize
    )
    monkeypatch.setattr(
        workflow_runner.qsar_client, "get_connectivity", fake_connectivity
    )
    monkeypatch.setattr(
        workflow_runner.qsar_client, "profile_with_profiler", fake_profile
    )
    monkeypatch.setattr(
        workflow_runner.qsar_client, "group_by_profiler", fake_group_by_profiler
    )
    monkeypatch.setattr(
        workflow_runner.qsar_client,
        "simulate_metabolites_for_chem",
        fake_simulator,
    )
    monkeypatch.setattr(workflow_runner.qsar_client, "apply_qsar_model", fake_qsar)
    monkeypatch.setattr(workflow_runner.qsar_client, "get_qsar_domain", fake_domain)
    monkeypatch.setattr(
        workflow_runner.qsar_client, "get_profiler_info", fake_profiler_info
    )
    monkeypatch.setattr(
        workflow_runner.qsar_client, "get_simulator_info", fake_simulator_info
    )
    monkeypatch.setattr(
        workflow_runner.qsar_client, "get_model_metadata", fake_model_info
    )


def test_golden_grouping_benzene(monkeypatch_qsar_client, monkeypatch):
    result = asyncio.run(
        workflow_runner.build_grouping_justification(
            identifier="Benzene",
            search_type="name",
            problem_formulation="Assess exploratory repeated-dose toxicity read-across.",
            decision_context="hazard_identification",
            endpoints=["Repeated dose toxicity"],
            route_of_exposure="oral",
            grouping_hypothesis="Simple aromatic hydrocarbons are expected to share relevant structural and mechanistic features.",
            analogue_identifiers=["Toluene", "Ethylbenzene"],
            analogue_search_type="name",
            profiler_guids=["prof-1"],
            simulator_guids=["sim-1"],
            qsar_guids=["qsar-1"],
            accepted_uncertainty_level="medium",
            context="Exploratory grouping dossier",
        )
    )
    workflow_record = result["portable_handoffs"]["oqtWorkflowRecord.v1"]
    normalized = normalize_for_snapshot(workflow_record)

    snapshot = load_snapshot("grouping_benzene")
    if snapshot is None:
        save_snapshot("grouping_benzene", normalized)
        pytest.fail("Snapshot grouping_benzene did not exist; it has been created. Re-run tests.")

    assert normalized == snapshot
