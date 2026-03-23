# Downstream Orchestration Example

This note shows how O-QT MCP fits into a broader orchestrated suite workflow without collapsing module boundaries.

## Intended flow

1. A downstream orchestrator calls `run_oqt_multiagent_workflow` when it needs Toolbox-native hazard evidence for a substance.
2. The orchestrator calls `build_grouping_justification` when a read-across or grouping dossier is needed.
3. O-QT returns live MCP artifacts (`summary_markdown`, `log_json`, `pdf_report_base64`, and, for grouping, `grouping_justification`) plus `portable_handoffs`.
4. The orchestrator consumes the published O-QT handoff objects directly from `portable_handoffs`.
5. The orchestrator combines the O-QT handoff objects with other evidence before any suite-level synthesis or decision support step.

If the orchestrator stores the raw `log_json` and needs to re-materialize contracts later, it can call `build_portable_handoffs_from_log` instead of rerunning the Toolbox workflow.

## Recommended handoff usage

Use the portable schemas under `schemas/` as the stable boundary between O-QT and a downstream orchestrator:

- `oqtWorkflowRecord.v1` for workflow provenance and artifact bookkeeping.
- `oqtHazardEvidenceSummary.v1` for hazard-evidence handoff after `run_oqt_multiagent_workflow`.
- `oqtReadAcrossSummary.v1` for grouping/read-across handoff after `build_grouping_justification`.

## Practical field mapping

Suggested mapping if a downstream consumer wants to reconstruct or cross-check the handoff objects against the raw fields:

| Live O-QT field | Portable handoff target |
| --- | --- |
| `identifier` | `chemicalIdentity.inputIdentifier` or `inputIdentifier.value` |
| `log_json.selected_chemical` | `chemicalIdentity.*` |
| `log_json.profiler_results` | `profilers` or `supportingProfiler` |
| `log_json.simulator_results` | `metabolismFindings` |
| `log_json.qsar_results` | `qsarFindings` |
| `grouping_justification.source_analogues` | `analogues` |
| `grouping_justification.endpoint_justifications` | `justification.endpointConclusions` |
| `summary_markdown` / `pdf_report_base64` / `log_json` | `artifacts.*` in `oqtWorkflowRecord.v1` |

## Example suite packet

```json
{
  "suite_orchestrator": "downstream-orchestrator",
  "oqt_handoff": {
    "workflow": "oqtWorkflowRecord.v1",
    "hazard": "oqtHazardEvidenceSummary.v1",
    "read_across": "oqtReadAcrossSummary.v1"
  },
  "joined_with": [
    "hazardEvidenceSummary.v1",
    "aopLinkageSummary.v1",
    "pbpkContextBundle.v1"
  ],
  "final_synthesis_layer": "outside oqt-mcp"
}
```

The key point is simple: O-QT stays the OECD QSAR Toolbox specialist, while downstream orchestration stays outside this module.
