# O-QT MCP Architecture and Boundary Notes

O-QT MCP is the ToxMCP suite's specialized OECD QSAR Toolbox engine. Its job is to expose Toolbox-native workflow execution, grouping/read-across support, and audit-ready artifacts through MCP without absorbing responsibilities that belong at the suite layer.

## Module role

O-QT MCP owns:

- OECD QSAR Toolbox search, profiling, metabolism, QSAR, and workflow execution.
- Workflow packaging through `run_oqt_multiagent_workflow`.
- Grouping/read-across dossier assembly through `build_grouping_justification`.
- Audit-ready JSON, Markdown, and PDF artifacts.
- Portable O-QT handoff schemas published under `schemas/`.

O-QT MCP does not own:

- Suite-wide orchestration across CompTox, AOP, PBPK, or future modules.
- Final BER/WoE synthesis or decision logic.
- Cross-domain semantics that properly belong to other MCPs.
- Async queueing or persistence infrastructure in v0.3.0.

## Public surface

The public surface is intentionally two-tiered:

- Primary mode: `run_oqt_multiagent_workflow` is the default entrypoint for downstream automation.
- Secondary mode: lower-level Toolbox tools remain public for expert users, debugging, and custom orchestration.
- Read-across packaging: `build_grouping_justification` stays within O-QT's domain by producing a dossier and uncertainty summary, not a final suite-level conclusion.

This keeps the module useful to power users without confusing the product boundary.

## Contract layers

O-QT publishes two different contract layers:

- Live MCP responses: tool payloads returned by the FastAPI JSON-RPC service.
- Portable handoff objects: versioned schemas under `schemas/` that downstream orchestrators can materialize and validate without coupling to a specific RPC call shape.

The portable schemas are intentionally narrow:

- `oqtWorkflowRecord.v1` captures workflow provenance and artifact references.
- `oqtHazardEvidenceSummary.v1` captures Toolbox-native hazard evidence.
- `oqtReadAcrossSummary.v1` captures grouping/read-across support.

They are handoff objects, not final decision objects.

## Orchestrator boundary

A downstream orchestrator sits above O-QT MCP. In a suite flow:

1. O-QT resolves the substance and produces Toolbox-native evidence.
2. O-QT emits structured artifacts plus schema-aligned objects under `portable_handoffs`.
3. The orchestrator combines O-QT output with other evidence sources.
4. Final multi-module synthesis happens at the orchestrator layer.

This boundary prevents O-QT from drifting into a general toxicology orchestrator.

## Deployment model

The current deployment model is synchronous and suited to controlled environments:

- FastAPI + JSON-RPC service exposed at `/mcp`.
- Reverse-proxy TLS termination and OIDC/RBAC in production.
- Direct connectivity to a licensed OECD QSAR Toolbox WebAPI instance.

An async job queue and persistence layer remain roadmap work, not part of the v0.3.0 contract.
