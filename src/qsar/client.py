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
                response = await client.request(method, url_path, params=params, json=json)
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
        self, path: str, *, json: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None
    ) -> Any:
        return await self._request("POST", path, params=params, json=json)

    async def get_model_metadata(self, object_guid: str) -> Dict[str, Any]:
        encoded = quote(object_guid)
        return await self._get(f"/api/v6/about/object/{encoded}")

    async def search_chemicals(self, query: str, search_type: str = "auto", ignore_stereo: bool = False) -> Dict[str, Any]:
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

    async def get_applicability_domain(self, model_id: str, chem_id: str) -> Dict[str, Any]:
        encoded_model = quote(model_id)
        encoded_chem = quote(chem_id)
        return await self._get(f"/api/v6/qsar/domain/{encoded_model}/{encoded_chem}")

    async def get_endpoint_data(self, chemical_identifier: str, endpoint: str) -> Dict[str, Any]:
        encoded = quote(chemical_identifier)
        params = {"endpoint": endpoint}
        return await self._get(f"/api/v6/data/{encoded}", params=params)

    async def generate_metabolites(self, smiles: str, simulator: str) -> Dict[str, Any]:
        payload = {"smiles": smiles, "simulator": simulator}
        return await self._post("/api/v6/metabolism/generate", json=payload)

    async def profile_chemical(self, chemical_identifier: str) -> Dict[str, Any]:
        encoded = quote(chemical_identifier)
        return await self._get(f"/api/v6/profiling/{encoded}")


# Global client instance using application settings
from src.config.settings import settings  # noqa: E402 (import after class definition)

qsar_client = QsarClient(settings.qsar.QSAR_TOOLBOX_API_URL)
