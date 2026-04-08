# Portable O-QT Schemas

The `schemas/` directory publishes portable evidence objects for cross-suite handoff.

- Live MCP tool responses are returned by the FastAPI JSON-RPC service, and the high-level workflow tools expose matching objects under `portable_handoffs`.
- `schemas/` contains portable objects that downstream MCPs and orchestrators can consume without depending on a specific transport call shape.

Current portable objects:

- `oqtHazardEvidenceSummary.v1.json`
- `oqtReadAcrossSummary.v1.json`
- `oqtWorkflowRecord.v1.json`

Design rules:

- Objects are lean, composable, and O-QT-scoped.
- These are handoff objects, not final decision objects.
- O-QT owns Toolbox-native evidence and provenance packaging, not suite-level synthesis.
- Workflow records carry package semantics, attachment manifests, and integrity metadata so downstream consumers can audit what was actually emitted.
- Hazard summaries carry request metadata, machine-readable assessment/decision boundaries, support claims, endpoint summaries, evidence blocks, applicability-domain summaries, source attribution, and a qualitative uncertainty block with explicit semantic coverage so downstream consumers can separate evidence completeness from decision logic.
- Read-across summaries carry machine-readable assessment/decision boundaries, applicability-domain, evidence-matrix, uncertainty-table, and required-external-input structures rather than only a top-level narrative.
- Example instances live under `schemas/examples/` and are validated in `tests/test_portable_schemas.py`.
