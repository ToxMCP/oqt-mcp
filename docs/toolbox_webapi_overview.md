# Toolbox WebAPI Overview

This reference aligns the planned MCP tooling with the OECD QSAR Toolbox Web API (v6). It captures the primary endpoints, required identifiers, and representative payloads so the MCP server can surface predictable schemas to LLM hosts.

## Base URL, Auth, and Conventions
- **Base path:** `/api/v6` under the Toolbox host (for example `https://toolbox.example.org/api/v6`).
- **Authentication:** Production instances expect the OAuth2/OIDC bearer token propagated by the MCP server. Ensure the upstream HTTP client attaches `Authorization: Bearer <access_token>` and any Toolbox-issued cookies when session bootstrap is required.
- **Content type:** Most endpoints advertise `text/plain` but return JSON bodies. Treat them as UTF-8 JSON payloads.
- **Identifiers:** Toolbox resources rely heavily on GUID strings:
  - `chemId` – Toolbox chemical identifier used by prediction, profiling, and search endpoints.
  - `qsarGuid` – Identifier for a QSAR model.
  - `profilerGuid` – Identifier for a profiling scheme (hazard categorisation).
  - `simulatorGuid` – Identifier for metabolism simulators.
  - `position` – A `#` delimited path within the endpoint tree taxonomy.
- **Error surface:** Errors are conveyed via HTTP status codes with JSON bodies when available. Wrap calls with retries/timeouts because long-running QSAR/prediction calls can exceed 30s.

## Planned MCP Tools at a Glance

| MCP Tool | Core Endpoints | Purpose |
| --- | --- | --- |
| `get_public_qsar_model_info` | `GET /data/endpointtree`, `GET /qsar/list/{position}`, `GET /about/object/{objectGuid}` | Discover QSAR models available for an endpoint and expose metadata describing the model provenance. |
| `search_chemicals` | `GET /search/name/{name}/{options}/{ignoreStereo}`, `GET /search/cas/{cas}/{ignoreStereo}`, `GET /search/smiles/{registerUnknown}/{ignoreStereo}`, `GET /search/chemical/{chemId}` | Locate chemicals by identifier or structure and retrieve canonical descriptors (CAS, EC, SMILES, names). |
| `run_qsar_prediction` | `GET /qsar/apply/{qsarGuid}/{chemId}`, `GET /qsar/domain/{qsarGuid}/{chemId}`, `GET /report/qsar/{chemId}/{qsarId}/{comments}` | Execute a QSAR model for a chemical, evaluate applicability domain, and (optionally) request a QMRF prediction report. |
| `analyze_chemical_hazard` | `GET /profiling`, `GET /profiling/{profilerGuid}/{chemId}`, `GET /profiling/all/{chemId}`, `GET /profiling/{profilerGuid}/literature` | Run Toolbox profilers to return hazard categories, rationales, and supporting literature for a chemical. |
| `generate_metabolites` | `GET /metabolism/{simulatorGuid}`, `GET /metabolism/{simulatorGuid}/{chemId}`, `GET /metabolism/{simulatorGuid}/info` | Enumerate predicted metabolites for a chemical or raw SMILES using registered simulators. |

The sections below detail request patterns and representative payloads for each tool.

---

### `get_public_qsar_model_info`

**Primary flow**
1. Resolve an endpoint path (`position`) via `GET /data/endpointtree` or `GET /data/endpoint?position=...`.
2. Retrieve QSAR models for that position: `GET /qsar/list/{position}`.
3. Fetch additional metadata referencing the model object GUID via `GET /about/object/{objectGuid}` (model description, authorship, donor, external URLs).

**Example request**  
`GET /api/v6/qsar/list/ECOTOX#Aquatic#Daphnia`

**Example response**
```json
[
  {
    "Caption": "Daphnia Acute Toxicity (48h LC50)",
    "Guid": "11111111-2222-3333-4444-555555555555",
    "Position": "ECOTOX#Aquatic#Daphnia",
    "Type": "QSARModel",
    "Endpoint": "LC50 (mg/L)",
    "Donator": "OECD QSAR Toolbox Team"
  }
]
```

**Metadata augmentation**
```json
{
  "Name": "Daphnia Acute Toxicity (48h LC50)",
  "Description": "Public QSAR model trained on curated Daphnia acute toxicity studies.",
  "Donator": "OECD QSAR Toolbox Team",
  "Authors": "O-QT Consortium",
  "Url": "https://toolbox.oecd.org/models/1111",
  "AdditionalInfo": {
    "DatasetVersion": "2024.1",
    "DescriptorEngine": "3D-QSAR"
  }
}
```

**Implementation notes**
- `position` is required and case-sensitive; invalid paths return HTTP 404.
- Cache endpoint tree lookups (rarely changes) to avoid repeated large payloads.
- Some models expose QMRF report GUIDs; surface them for downstream documentation links.

---

### `search_chemicals`

**Supported query patterns**
- `GET /search/name/{name}/{options}/{ignoreStereo}` – string match where `options` ∈ `{ExactMatch, StartsWith, Contains}`.
- `GET /search/cas/{cas}/{ignoreStereo}` – numeric CAS identifier.
- `GET /search/ecnumber/{ecNumber}/{ignoreStereo}` – EC registry search.
- `GET /search/smiles/{registerUnknown}/{ignoreStereo}?smiles=...` – exact SMILES search with opt-in registration for unknowns.
- `GET /search/smarts/{ignoreStereo}?smarts=...` – substructure search.
- `GET /search/chemical/{chemId}` – hydrate cached search results by Toolbox chemical GUID.

**Example request**  
`GET /api/v6/search/name/Acetone/ExactMatch/false`

**Example response**
```json
[
  {
    "SubstanceType": "Organic",
    "ChemId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "Cas": 67641,
    "ECNumber": "200-662-2",
    "Smiles": "CC(=O)C",
    "Names": [
      "Acetone",
      "Propanone"
    ],
    "Sources": [
      {
        "SourceId": 12,
        "SourceName": "ECHA REACH",
        "Quality": "Curated"
      }
    ],
    "CasSmilesRelation": "Exact"
  }
]
```

**Implementation notes**
- Many search endpoints accept path booleans (`ignoreStereo`, `registerUnknown`); normalise booleans when constructing URLs.
- Substructure results can be large; limit/stream or convert into paged responses within the MCP tool.
- The `/search/databases` endpoint lists optional inventories and their `SourceId` values for filtering.

---

### `run_qsar_prediction`

**Primary flow**
1. Validate the chemical is in-domain: `GET /qsar/domain/{qsarGuid}/{chemId}`.
2. Execute the prediction: `GET /qsar/apply/{qsarGuid}/{chemId}`.
3. Optionally trigger a QMRF PDF report: `GET /report/qsar/{chemId}/{qsarId}/{comments}` (returns a download link or PDF stream).

**Example prediction response**
```json
{
  "DomainResult": "Inside",
  "DomainExplain": [
    "All key descriptors within model range.",
    "Chemical similarity threshold satisfied."
  ],
  "DataType": "Continuous",
  "ModelType": "Regression",
  "Value": "0.85",
  "Unit": "mg/L",
  "PredictionExplain": "Predicted LC50 (48h) for Daphnia magna.",
  "SupportingData": [
    {
      "Descriptor": "LogP",
      "Value": "0.3",
      "Range": "-1.0 – 2.5"
    }
  ]
}
```

**Implementation notes**
- Domain checks return plain strings (`"Inside"`, `"Outside"`, etc.). Combine with structured prediction results in MCP responses.
- Some models expect the chemical to be pre-registered; expose helpful errors when `chemId` is unknown (HTTP 404).
- QMRF report endpoint requires a comment path segment; pass URL-safe text (e.g., `"generated_via_mcp"`).

---

### `analyze_chemical_hazard`

**Primary flow**
1. List profilers to expose to clients: `GET /profiling`.
2. Run a profiler against a chemical: `GET /profiling/{profilerGuid}/{chemId}` (optionally including simulator GUID when the profiler depends on prior metabolism).
3. For comprehensive coverage use `GET /profiling/all/{chemId}`.
4. Augment responses with `GET /profiling/{profilerGuid}/literature?category=...` for citations.

**Example profiler response**
```json
[
  {
    "ProfilerGuid": "bbbbbbbb-cccc-dddd-eeee-ffffffffffff",
    "ProfilerName": "Acute Aquatic Toxicity",
    "ProfilerType": "HazardCategorisation",
    "Categories": [
      "Category 3 (LC50 0.5–5 mg/L)",
      "Category 2 (LC50 0.1–0.5 mg/L)"
    ],
    "Rationale": [
      "Experimental value in ECHA dossier places substance in Category 3.",
      "QSAR consensus supports Category 2 boundary."
    ],
    "Metadata": {
      "LastUpdatedUtc": "2024-10-12T09:32:00Z",
      "RequiredDescriptors": [
        "WaterSolubility",
        "LogP"
      ]
    }
  }
]
```

**Implementation notes**
- Profiler payloads can include category enumerations and nested metadata; normalise to a consistent MCP schema with `categories`, `explanations`, and optional `literature`.
- Some profilers require pre-computed metabolism (e.g., `simulatorGuid` path parameter). Validate availability before calling.
- Use `/profiling/relevancies` with endpoint `position` to filter profilers surfaced in tool discovery.

---

### `generate_metabolites`

**Primary flow**
1. Enumerate available simulators via `GET /profiling` (returns profilers and simulators) or dedicated list endpoints when available.
2. Run simulator against a Toolbox chemical: `GET /metabolism/{simulatorGuid}/{chemId}`.
3. Support raw structures by using `GET /metabolism/{simulatorGuid}?smiles=...`.
4. Retrieve simulator metadata describing reaction rules: `GET /metabolism/{simulatorGuid}/info`.

**Example response**
```json
{
  "SimulatorGuid": "cccccccc-dddd-eeee-ffff-000000000000",
  "SimulatorName": "Rat Liver S9 (Phase I)",
  "Products": [
    {
      "ChemId": "dddddddd-eeee-ffff-0000-111111111111",
      "ProductName": "Hydroxylated derivative",
      "Smiles": "CC(O)C(=O)C",
      "Confidence": 0.76
    },
    {
      "ChemId": null,
      "ProductName": "Epoxide intermediate",
      "Smiles": "C1OC1C(=O)C",
      "Confidence": 0.42
    }
  ]
}
```

**Implementation notes**
- Responses in swagger examples are arrays of strings; real payloads often return richer JSON. Be prepared to merge string-only responses into structured objects using heuristics (reaction name, SMILES).
- When no `chemId` exists for a generated product, preserve SMILES so downstream workflows can hydrate via `search/smiles`.
- Simulators may be long-running; add MCP progress messaging if runtime exceeds latency thresholds.

---

## Additional Reference Endpoints
- `GET /data/metadatahierarchy` – preload metadata labels to support dynamic filtering in tool prompts.
- `GET /data/metadatavalues?rigidPath=...&metadataLabel=...` – suggest allowed metadata values when constructing endpoint queries.
- `GET /calculation` and `GET /calculation/{calculatorGuid}/{chemId}` – candidate endpoints for future calculator-based tools.
- `GET /workflows` and `GET /workflows/{workflowGuid}/{chemId}` – orchestrated sequences (potential stretch goal for assisted workflows).
- `GET /session/signalrid?connectionId=...` – session signalling helper leveraged by the Toolbox UI; usually unnecessary for server-side integrations.

## Next Steps
- Validate live responses against these examples using the Toolbox sandbox; update sample payloads if schema differences surface.
- Decide on pagination/streaming strategies for large result sets (search and profiling).
- Coordinate with security tasks to ensure RBAC aligns with profiler and simulator exposure.

