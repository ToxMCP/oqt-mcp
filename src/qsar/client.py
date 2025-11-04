import asyncio
import logging
import random
import re
import time
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote

import httpx

log = logging.getLogger(__name__)


class QsarClientError(Exception):
    """Raised when the QSAR Toolbox API returns an error or cannot be reached."""


NO_SIMULATOR_GUID = "00000000-0000-0000-0000-000000000000"


class QsarClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        headers: Optional[Dict[str, str]] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        timeout_profiles: Optional[Dict[str, httpx.Timeout]] = None,
        max_attempts: Optional[Dict[str, int]] = None,
        heavy_concurrency: int = 3,
        limits: Optional[httpx.Limits] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout  # Backwards-compatible default (light profile)
        self.headers = headers or {}
        self.transport = transport
        self._timeout_profiles = timeout_profiles or {
            "light": httpx.Timeout(connect=5.0, read=30.0, write=15.0, pool=10.0),
            "heavy": httpx.Timeout(connect=10.0, read=300.0, write=60.0, pool=15.0),
        }
        # Ensure legacy callers using only `timeout` still respect that value for light profile
        if "light" not in self._timeout_profiles:
            self._timeout_profiles["light"] = httpx.Timeout(
                connect=5.0, read=timeout, write=timeout, pool=10.0
            )
        self._max_attempts = max_attempts or {"light": 2, "heavy": 3}
        self._retry_status_codes = {500, 502, 503, 504}
        self._initial_backoff = 0.5
        self._heavy_semaphore = asyncio.Semaphore(max(1, heavy_concurrency))
        self._limits = limits or httpx.Limits(
            max_connections=20, max_keepalive_connections=10
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        timeout_profile: str = "light",
        with_meta: bool = False,
    ) -> Any:
        url_path = path if path.startswith("/") else f"/{path}"
        profile = timeout_profile if timeout_profile in self._timeout_profiles else "light"
        timeout_config = self._timeout_profiles[profile]
        max_attempts = max(1, self._max_attempts.get(profile, 2))

        async def _execute_request() -> Tuple[Any, Dict[str, Any]]:
            attempts = 0
            backoff = self._initial_backoff
            last_exception: Optional[Exception] = None
            response: Optional[httpx.Response] = None
            total_start = time.perf_counter()

            while attempts < max_attempts:
                attempts += 1
                attempt_start = time.perf_counter()
                try:
                    async with httpx.AsyncClient(
                        base_url=self.base_url,
                        timeout=timeout_config,
                        headers=self.headers,
                        transport=self.transport,
                        limits=self._limits,
                    ) as client:
                        response = await client.request(
                            method, url_path, params=params, json=json
                        )
                except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.WriteTimeout) as exc:
                    last_exception = exc
                    log.warning(
                        "QSAR client timeout (%s) for %s %s attempt %s/%s",
                        type(exc).__name__,
                        method,
                        url_path,
                        attempts,
                        max_attempts,
                    )
                except httpx.RequestError as exc:
                    last_exception = exc
                    log.warning(
                        "QSAR client network error (%s) for %s %s attempt %s/%s",
                        type(exc).__name__,
                        method,
                        url_path,
                        attempts,
                        max_attempts,
                    )
                else:
                    if response.status_code >= 400:
                        is_retryable = response.status_code in self._retry_status_codes
                        log_message = (
                            "QSAR API error %s %s -> %s: %s"
                            % (
                                method,
                                url_path,
                                response.status_code,
                                response.text[:200],
                            )
                        )
                        if is_retryable and attempts < max_attempts:
                            log.warning("%s (retrying)", log_message)
                        else:
                            log.error(log_message)
                        if not is_retryable or attempts >= max_attempts:
                            raise QsarClientError(
                                f"QSAR API error ({response.status_code})"
                            )
                        last_exception = None
                    else:
                        elapsed_total = (time.perf_counter() - total_start) * 1000
                        elapsed_attempt = (time.perf_counter() - attempt_start) * 1000
                        data = self._parse_response_content(response, method, url_path)
                        meta = {
                            "attempts": attempts,
                            "duration_ms": round(elapsed_total, 3),
                            "last_attempt_ms": round(elapsed_attempt, 3),
                            "timeout_profile": profile,
                            "status_code": response.status_code,
                        }
                        return data, meta

                if attempts >= max_attempts:
                    break

                sleep_for = backoff * (1 + random.random())
                await asyncio.sleep(sleep_for)
                backoff *= 2

            raise QsarClientError(
                f"Failed to reach QSAR Toolbox API after {attempts} attempts"
            ) from last_exception

        if profile == "heavy":
            async with self._heavy_semaphore:
                data, meta = await _execute_request()
        else:
            data, meta = await _execute_request()

        return (data, meta) if with_meta else data

    def _parse_response_content(
        self, response: httpx.Response, method: str, url_path: str
    ) -> Any:
        if not response.content:
            return None

        content_type = response.headers.get("content-type", "").lower()
        if "application/json" in content_type or "+json" in content_type:
            try:
                return response.json()
            except ValueError as exc:
                log.error("QSAR API returned invalid JSON for %s %s", method, url_path)
                raise QsarClientError("Invalid response from QSAR Toolbox API") from exc

        if content_type.startswith("text/") or content_type == "":
            return response.text

        return response.content

    async def _get(
        self,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        timeout_profile: str = "light",
        with_meta: bool = False,
    ) -> Any:
        return await self._request(
            "GET",
            path,
            params=params,
            timeout_profile=timeout_profile,
            with_meta=with_meta,
        )

    async def _post(
        self,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        timeout_profile: str = "light",
        with_meta: bool = False,
    ) -> Any:
        return await self._request(
            "POST",
            path,
            params=params,
            json=json,
            timeout_profile=timeout_profile,
            with_meta=with_meta,
        )

    async def get_model_metadata(self, object_guid: str) -> Dict[str, Any]:
        encoded = quote(object_guid)
        return await self._get(f"/api/v6/about/object/{encoded}")

    async def list_calculators(self, *, with_meta: bool = False) -> Any:
        return await self._get("/api/v6/calculation", with_meta=with_meta)

    async def get_calculator_info(
        self, calculator_guid: str, *, with_meta: bool = False
    ) -> Any:
        encoded = quote(calculator_guid)
        return await self._get(
            f"/api/v6/calculation/{encoded}/info", with_meta=with_meta
        )

    async def list_profilers(self, *, with_meta: bool = False) -> Any:
        return await self._get("/api/v6/profiling", with_meta=with_meta)

    async def get_profiler_info(
        self, profiler_guid: str, *, with_meta: bool = False
    ) -> Any:
        encoded = quote(profiler_guid)
        return await self._get(
            f"/api/v6/profiling/{encoded}/info", with_meta=with_meta
        )

    async def list_simulators(self, *, with_meta: bool = False) -> Any:
        return await self._get("/api/v6/metabolism", with_meta=with_meta)

    async def get_simulator_info(
        self, simulator_guid: str, *, with_meta: bool = False
    ) -> Any:
        encoded = quote(simulator_guid)
        return await self._get(
            f"/api/v6/metabolism/{encoded}/info", with_meta=with_meta
        )

    async def get_endpoint_tree(self, *, with_meta: bool = False) -> Any:
        return await self._get("/api/v6/data/endpointtree", with_meta=with_meta)

    async def get_metadata_hierarchy(self, *, with_meta: bool = False) -> Any:
        return await self._get(
            "/api/v6/data/metadatahierarchy", with_meta=with_meta
        )

    async def search_chemicals(
        self,
        query: str,
        search_type: str = "auto",
        ignore_stereo: bool = False,
        *,
        with_meta: bool = False,
    ) -> Any:
        """
        Normalised wrapper for the Toolbox search endpoints. Handles the current
        API contract which exposes separate routes for CAS, name, and SMILES searches.
        """
        if not query or not query.strip():
            raise QsarClientError("Search query must not be empty.")

        lookup = query.strip()
        mode = (search_type or "auto").lower()
        ignore_value = "true" if ignore_stereo else "false"

        # CAS lookup expects only digits in the Toolbox HTTP API.
        if mode == "cas":
            encoded_original = quote(lookup)
            digits = re.sub(r"[^0-9]", "", lookup)
            paths = [f"/api/v6/search/cas/{encoded_original}/{ignore_value}"]
            if digits and digits != lookup:
                paths.append(f"/api/v6/search/cas/{digits}/{ignore_value}")
            last_error: Optional[Exception] = None
            for cas_path in paths:
                try:
                    raw = await self._get(cas_path, with_meta=with_meta)
                except QsarClientError as exc:
                    last_error = exc
                    continue
                if with_meta:
                    data, meta = raw
                else:
                    data, meta = raw, None
                if data:
                    return (data, meta) if with_meta else data
            if last_error:
                raise last_error
            return ([], None) if with_meta else []

        # SMILES lookup is a dedicated GET endpoint with registerUnknown toggle.
        if mode in {"smiles", "structure"}:
            path = f"/api/v6/search/smiles/false/{ignore_value}"
            result = await self._get(
                path, params={"smiles": lookup}, with_meta=with_meta
            )
            if with_meta:
                return result
            return result

        # Name-based searches use the options enumeration (ExactMatch/StartWith/Contains).
        option_map = {
            "name": ["ExactMatch", "StartWith", "Contains"],
            "auto": ["ExactMatch", "StartWith", "Contains"],
            "exact": ["ExactMatch"],
            "name_exact": ["ExactMatch"],
            "contains": ["Contains"],
            "name_contains": ["Contains"],
            "starts_with": ["StartWith"],
            "startswith": ["StartWith"],
            "prefix": ["StartWith"],
        }
        options = option_map.get(mode, ["ExactMatch", "StartWith", "Contains"])
        encoded = quote(lookup)
        last_error: Optional[Exception] = None

        for option in options:
            try:
                raw = await self._get(
                    f"/api/v6/search/name/{encoded}/{option}/{ignore_value}",
                    with_meta=with_meta,
                )
            except QsarClientError as exc:
                last_error = exc
                continue
            if with_meta:
                result, meta = raw
            else:
                result, meta = raw, None

            if result:
                return (result, meta) if with_meta else result

        if last_error:
            raise last_error
        return ([], None) if with_meta else []

    async def run_prediction(self, smiles: str, model_id: str) -> Dict[str, Any]:
        payload = {"smiles": smiles, "modelId": model_id}
        return await self._post("/api/v6/qsar/apply", json=payload)

    async def apply_qsar_model(
        self, qsar_guid: str, chem_id: str, *, with_meta: bool = False
    ) -> Any:
        encoded_model = quote(qsar_guid)
        encoded_chem = quote(chem_id)
        return await self._get(
            f"/api/v6/qsar/apply/{encoded_model}/{encoded_chem}",
            with_meta=with_meta,
        )

    async def get_qsar_domain(
        self, qsar_guid: str, chem_id: str, *, with_meta: bool = False
    ) -> Any:
        encoded_model = quote(qsar_guid)
        encoded_chem = quote(chem_id)
        return await self._get(
            f"/api/v6/qsar/domain/{encoded_model}/{encoded_chem}",
            with_meta=with_meta,
        )

    async def generate_qmrf(self, qsar_id: str, *, with_meta: bool = False) -> Any:
        encoded = quote(qsar_id)
        return await self._get(
            f"/api/v6/report/qmrf/{encoded}",
            timeout_profile="heavy",
            with_meta=with_meta,
        )

    async def generate_qsar_report(
        self, chem_id: str, qsar_id: str, comments: str, *, with_meta: bool = False
    ) -> Any:
        encoded_chem = quote(chem_id)
        encoded_qsar = quote(qsar_id)
        encoded_comments = quote(comments or "")
        return await self._get(
            f"/api/v6/report/qsar/{encoded_chem}/{encoded_qsar}/{encoded_comments}",
            timeout_profile="heavy",
            with_meta=with_meta,
        )

    async def execute_workflow(
        self, workflow_guid: str, chem_id: str, *, with_meta: bool = False
    ) -> Any:
        encoded_workflow = quote(workflow_guid)
        encoded_chem = quote(chem_id)
        return await self._get(
            f"/api/v6/workflows/{encoded_workflow}/{encoded_chem}",
            timeout_profile="heavy",
            with_meta=with_meta,
        )

    async def list_workflows(self) -> Any:
        return await self._get("/api/v6/workflows")

    async def workflow_report(
        self, chem_id: str, workflow_id: str, comments: str, *, with_meta: bool = False
    ) -> Any:
        encoded_chem = quote(chem_id)
        encoded_workflow = quote(workflow_id)
        encoded_comments = quote(comments or "")
        return await self._get(
            f"/api/v6/report/workflow/{encoded_chem}/{encoded_workflow}/{encoded_comments}",
            timeout_profile="heavy",
            with_meta=with_meta,
        )

    async def group_by_profiler(
        self, chem_id: str, profiler_guid: str, *, with_meta: bool = False
    ) -> Any:
        encoded_chem = quote(chem_id)
        encoded_prof = quote(profiler_guid)
        return await self._get(
            f"/api/v6/grouping/{encoded_chem}/{encoded_prof}",
            timeout_profile="heavy",
            with_meta=with_meta,
        )

    async def list_qsar_models(self, position: str, *, with_meta: bool = False) -> Any:
        encoded = quote(position, safe="")
        return await self._get(f"/api/v6/qsar/list/{encoded}", with_meta=with_meta)

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

    async def list_search_databases(self, *, with_meta: bool = False) -> Any:
        return await self._get("/api/v6/search/databases", with_meta=with_meta)

    async def canonicalize_structure(
        self, smiles: str, *, with_meta: bool = False
    ) -> Any:
        return await self._get(
            "/api/v6/structure/canonize",
            params={"smiles": smiles},
            with_meta=with_meta,
        )

    async def get_connectivity(self, smiles: str, *, with_meta: bool = False) -> Any:
        return await self._get(
            "/api/v6/structure/connectivity",
            params={"smiles": smiles},
            with_meta=with_meta,
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
        self,
        chem_id: str,
        *,
        endpoint: Optional[str] = None,
        position: Optional[str] = None,
        include_metadata: bool = False,
        with_meta: bool = False,
    ) -> Any:
        encoded = quote(chem_id)
        params: Dict[str, Any] = {}
        if endpoint:
            params["endpoint"] = endpoint
        if position:
            params["position"] = position
        if include_metadata:
            params["includeMetadata"] = "true"
        return await self._get(
            f"/api/v6/data/{encoded}",
            params=params or None,
            timeout_profile="heavy",
            with_meta=with_meta,
        )

    async def generate_metabolites(
        self, smiles: str, simulator_guid: str, *, with_meta: bool = False
    ) -> Any:
        if not simulator_guid:
            raise QsarClientError("A simulator GUID is required to generate metabolites.")
        return await self.simulate_metabolites_for_smiles(
            simulator_guid, smiles, with_meta=with_meta
        )

    async def profile_chemical(
        self, chem_id: str, *, with_meta: bool = False
    ) -> Any:
        encoded = quote(chem_id)
        return await self._get(
            f"/api/v6/profiling/all/{encoded}",
            timeout_profile="heavy",
            with_meta=with_meta,
        )

    async def profile_with_profiler(
        self,
        profiler_guid: str,
        chem_id: str,
        simulator_guid: Optional[str] = None,
        *,
        with_meta: bool = False,
    ) -> Any:
        encoded_prof = quote(profiler_guid)
        encoded_chem = quote(chem_id)
        encoded_sim = (
            quote(simulator_guid) if simulator_guid else NO_SIMULATOR_GUID
        )
        path = f"/api/v6/profiling/{encoded_prof}/{encoded_chem}/{encoded_sim}"
        return await self._get(path, with_meta=with_meta)

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
        self, simulator_guid: str, chem_id: str, *, with_meta: bool = False
    ) -> Any:
        encoded_sim = quote(simulator_guid)
        encoded_chem = quote(chem_id)
        return await self._get(
            f"/api/v6/metabolism/{encoded_sim}/{encoded_chem}",
            timeout_profile="heavy",
            with_meta=with_meta,
        )

    async def simulate_metabolites_for_smiles(
        self, simulator_guid: str, smiles: str, *, with_meta: bool = False
    ) -> Any:
        encoded_sim = quote(simulator_guid)
        return await self._get(
            f"/api/v6/metabolism/{encoded_sim}",
            params={"smiles": smiles},
            timeout_profile="heavy",
            with_meta=with_meta,
        )


# Global client instance using application settings
from src.config.settings import settings  # noqa: E402 (import after class definition)

qsar_client = QsarClient(settings.qsar.QSAR_TOOLBOX_API_URL)
