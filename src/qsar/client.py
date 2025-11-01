import logging
from typing import Any, Dict, Optional
from urllib.parse import quote

import httpx

log = logging.getLogger(__name__)


class QsarClientError(Exception):
    """Raised when the QSAR Toolbox API returns an error or cannot be reached."""


class QsarClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        headers: Optional[Dict[str, str]] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = headers or {}
        self.transport = transport

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Any:
        url_path = path if path.startswith("/") else f"/{path}"
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers=self.headers,
                transport=self.transport,
            ) as client:
                response = await client.request(
                    method, url_path, params=params, json=json
                )
        except httpx.RequestError as exc:
            log.error("QSAR client network error: %s", exc)
            raise QsarClientError("Failed to reach QSAR Toolbox API") from exc

        if response.status_code >= 400:
            log.error(
                "QSAR API error %s %s -> %s: %s",
                method,
                url_path,
                response.status_code,
                response.text[:200],
            )
            raise QsarClientError(f"QSAR API error ({response.status_code})")

        if not response.content:
            return None

        try:
            return response.json()
        except ValueError as exc:
            log.error("QSAR API returned invalid JSON for %s %s", method, url_path)
            raise QsarClientError("Invalid response from QSAR Toolbox API") from exc

    async def _get(self, path: str, *, params: Optional[Dict[str, Any]] = None) -> Any:
        return await self._request("GET", path, params=params)

    async def _post(
        self,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        return await self._request("POST", path, params=params, json=json)

    async def get_model_metadata(self, object_guid: str) -> Dict[str, Any]:
        encoded = quote(object_guid)
        return await self._get(f"/api/v6/about/object/{encoded}")

    async def list_calculators(self) -> Any:
        return await self._get("/api/v6/calculation")

    async def get_calculator_info(self, calculator_guid: str) -> Any:
        encoded = quote(calculator_guid)
        return await self._get(f"/api/v6/calculation/{encoded}/info")

    async def list_profilers(self) -> Any:
        return await self._get("/api/v6/profiling")

    async def get_profiler_info(self, profiler_guid: str) -> Any:
        encoded = quote(profiler_guid)
        return await self._get(f"/api/v6/profiling/{encoded}/info")

    async def list_simulators(self) -> Any:
        return await self._get("/api/v6/metabolism")

    async def get_simulator_info(self, simulator_guid: str) -> Any:
        encoded = quote(simulator_guid)
        return await self._get(f"/api/v6/metabolism/{encoded}/info")

    async def get_endpoint_tree(self) -> Any:
        return await self._get("/api/v6/data/endpointtree")

    async def get_metadata_hierarchy(self) -> Any:
        return await self._get("/api/v6/data/metadatahierarchy")

    async def search_chemicals(
        self, query: str, search_type: str = "auto", ignore_stereo: bool = False
    ) -> Dict[str, Any]:
        search_type = (search_type or "auto").lower()
        ignore_value = "true" if ignore_stereo else "false"
        encoded_query = quote(query)

        if search_type == "cas":
            path = f"/api/v6/search/cas/{encoded_query}/{ignore_value}"
            return await self._get(path)
        if search_type == "name":
            path = f"/api/v6/search/name/{encoded_query}/auto/{ignore_value}"
            return await self._get(path)
        if search_type == "smiles":
            payload = {"smiles": query, "ignoreStereo": ignore_value}
            return await self._post("/api/v6/search/smiles", json=payload)

        params = {"query": query, "type": search_type, "ignoreStereo": ignore_value}
        return await self._get("/api/v6/search", params=params)

    async def run_prediction(self, smiles: str, model_id: str) -> Dict[str, Any]:
        payload = {"smiles": smiles, "modelId": model_id}
        return await self._post("/api/v6/qsar/apply", json=payload)

    async def apply_qsar_model(self, qsar_guid: str, chem_id: str) -> Any:
        encoded_model = quote(qsar_guid)
        encoded_chem = quote(chem_id)
        return await self._get(f"/api/v6/qsar/apply/{encoded_model}/{encoded_chem}")

    async def get_qsar_domain(self, qsar_guid: str, chem_id: str) -> Any:
        encoded_model = quote(qsar_guid)
        encoded_chem = quote(chem_id)
        return await self._get(f"/api/v6/qsar/domain/{encoded_model}/{encoded_chem}")

    async def generate_qmrf(self, qsar_id: str) -> Any:
        encoded = quote(qsar_id)
        return await self._get(f"/api/v6/report/qmrf/{encoded}")

    async def generate_qsar_report(
        self, chem_id: str, qsar_id: str, comments: str
    ) -> Any:
        encoded_chem = quote(chem_id)
        encoded_qsar = quote(qsar_id)
        encoded_comments = quote(comments or "")
        return await self._get(
            f"/api/v6/report/qsar/{encoded_chem}/{encoded_qsar}/{encoded_comments}"
        )

    async def execute_workflow(self, workflow_guid: str, chem_id: str) -> Any:
        encoded_workflow = quote(workflow_guid)
        encoded_chem = quote(chem_id)
        return await self._get(f"/api/v6/workflows/{encoded_workflow}/{encoded_chem}")

    async def list_workflows(self) -> Any:
        return await self._get("/api/v6/workflows")

    async def workflow_report(
        self, chem_id: str, workflow_id: str, comments: str
    ) -> Any:
        encoded_chem = quote(chem_id)
        encoded_workflow = quote(workflow_id)
        encoded_comments = quote(comments or "")
        return await self._get(
            f"/api/v6/report/workflow/{encoded_chem}/{encoded_workflow}/{encoded_comments}"
        )

    async def group_by_profiler(self, chem_id: str, profiler_guid: str) -> Any:
        encoded_chem = quote(chem_id)
        encoded_prof = quote(profiler_guid)
        return await self._get(f"/api/v6/grouping/{encoded_chem}/{encoded_prof}")

    async def apply_qsar_model(self, qsar_guid: str, chem_id: str) -> Any:
        encoded_model = quote(qsar_guid)
        encoded_chem = quote(chem_id)
        return await self._get(f"/api/v6/qsar/apply/{encoded_model}/{encoded_chem}")

    async def get_qsar_domain(self, qsar_guid: str, chem_id: str) -> Any:
        encoded_model = quote(qsar_guid)
        encoded_chem = quote(chem_id)
        return await self._get(f"/api/v6/qsar/domain/{encoded_model}/{encoded_chem}")

    async def generate_qmrf(self, qsar_id: str) -> Any:
        encoded = quote(qsar_id)
        return await self._get(f"/api/v6/report/qmrf/{encoded}")

    async def generate_qsar_report(
        self, chem_id: str, qsar_id: str, comments: str
    ) -> Any:
        encoded_chem = quote(chem_id)
        encoded_qsar = quote(qsar_id)
        encoded_comments = quote(comments or "")
        return await self._get(
            f"/api/v6/report/qsar/{encoded_chem}/{encoded_qsar}/{encoded_comments}"
        )

    async def execute_workflow(self, workflow_guid: str, chem_id: str) -> Any:
        encoded_workflow = quote(workflow_guid)
        encoded_chem = quote(chem_id)
        return await self._get(f"/api/v6/workflows/{encoded_workflow}/{encoded_chem}")

    async def list_qsar_models(self, position: str) -> Any:
        encoded = quote(position, safe="")
        return await self._get(f"/api/v6/qsar/list/{encoded}")

    async def list_all_qsar_models(self) -> list[Dict[str, Any]]:
        catalog: list[Dict[str, Any]] = []
        seen: set[str] = set()

        try:
            positions = await self.get_endpoint_tree()
        except QsarClientError:
            positions = []

        if not isinstance(positions, list):
            positions = []

        for position in positions:
            if not isinstance(position, str):
                continue
            try:
                models = await self.list_qsar_models(position) or []
            except QsarClientError:
                continue

            if isinstance(models, dict):
                models = [models]

            for entry in models:
                if not isinstance(entry, dict):
                    continue
                guid = entry.get("Guid")
                if not guid or guid in seen:
                    continue
                seen.add(guid)
                record = dict(entry)
                record.setdefault("RequestedPosition", position)
                catalog.append(record)

        return catalog

    async def list_search_databases(self) -> Any:
        return await self._get("/api/v6/search/databases")

    async def canonicalize_structure(self, smiles: str) -> Any:
        return await self._get("/api/v6/structure/canonize", params={"smiles": smiles})

    async def get_connectivity(self, smiles: str) -> Any:
        return await self._get(
            "/api/v6/structure/connectivity", params={"smiles": smiles}
        )

    async def open_session(self) -> Any:
        return await self._get("/api/v6/session/open")

    async def signal_rid(self, connection_id: str) -> Any:
        return await self._get(
            "/api/v6/session/signalrid", params={"connectionId": connection_id}
        )

    async def get_applicability_domain(
        self, model_id: str, chem_id: str
    ) -> Dict[str, Any]:
        encoded_model = quote(model_id)
        encoded_chem = quote(chem_id)
        return await self._get(f"/api/v6/qsar/domain/{encoded_model}/{encoded_chem}")

    async def get_endpoint_data(
        self, chemical_identifier: str, endpoint: str
    ) -> Dict[str, Any]:
        encoded = quote(chemical_identifier)
        params = {"endpoint": endpoint}
        return await self._get(f"/api/v6/data/{encoded}", params=params)

    async def generate_metabolites(self, smiles: str, simulator: str) -> Dict[str, Any]:
        payload = {"smiles": smiles, "simulator": simulator}
        return await self._post("/api/v6/metabolism/generate", json=payload)

    async def profile_chemical(self, chemical_identifier: str) -> Dict[str, Any]:
        encoded = quote(chemical_identifier)
        return await self._get(f"/api/v6/profiling/{encoded}")

    async def profile_with_profiler(
        self, profiler_guid: str, chem_id: str, simulator_guid: Optional[str] = None
    ) -> Any:
        encoded_prof = quote(profiler_guid)
        encoded_chem = quote(chem_id)
        path = f"/api/v6/profiling/{encoded_prof}/{encoded_chem}"
        if simulator_guid:
            encoded_sim = quote(simulator_guid)
            path = f"{path}/{encoded_sim}"
        return await self._get(path)

    async def profile_all(self, chem_id: str) -> Any:
        encoded = quote(chem_id)
        return await self._get(f"/api/v6/profiling/all/{encoded}")

    async def profiler_literature(
        self, profiler_guid: str, category: Optional[str] = None
    ) -> Any:
        encoded_prof = quote(profiler_guid)
        params = {"category": category} if category else None
        return await self._get(
            f"/api/v6/profiling/{encoded_prof}/literature", params=params
        )

    async def simulate_metabolites_for_chem(
        self, simulator_guid: str, chem_id: str
    ) -> Any:
        encoded_sim = quote(simulator_guid)
        encoded_chem = quote(chem_id)
        return await self._get(f"/api/v6/metabolism/{encoded_sim}/{encoded_chem}")

    async def simulate_metabolites_for_smiles(
        self, simulator_guid: str, smiles: str
    ) -> Any:
        encoded_sim = quote(simulator_guid)
        return await self._get(
            f"/api/v6/metabolism/{encoded_sim}", params={"smiles": smiles}
        )


# Global client instance using application settings
from src.config.settings import settings  # noqa: E402 (import after class definition)

qsar_client = QsarClient(settings.qsar.QSAR_TOOLBOX_API_URL)
