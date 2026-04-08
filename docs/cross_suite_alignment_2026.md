# Cross-Suite Alignment Review (2026-04-08)

This note records the local cross-suite contract review used to harden O-QT MCP for auditability, verifiability, and regulated downstream use.

## Repos inspected locally

- `AOP_MCP`
- `comptox_mcp_clean_3568d68`
- `PBPK_MCP`

## Patterns adopted into O-QT MCP

### From AOP MCP

- Explicit evidence blocks instead of only free-form summaries.
- Provenance records that say which source populated which contract field and with what transformation confidence.
- Clear separation between evidence packaging and final decision logic.

### From CompTox MCP

- Explicit applicability-domain framing as a first-class review object.
- Stronger metadata and provenance packaging for downstream audit workflows.
- Preference for machine-readable review fields over narrative-only payloads.

### From PBPK MCP

- Machine-readable assessment and decision boundaries rather than only prose caveats.
- Explicit `supports` and `requiredExternalInputs` fields so downstream consumers can tell what the module does and does not claim to decide.
- Stronger uncertainty framing that distinguishes semantic coverage from quantitative confidence.

### From other contract-first modules

- Explicit `decisionOwner` language so handoff objects make ownership boundaries visible.
- Contract emphasis on fit-for-purpose review rather than implied finality.
- Preference for provenance-ready, typed records over narrative-only summaries.

## O-QT changes made from this review

- `oqtHazardEvidenceSummary.v1` now includes:
  - `assessmentBoundary`
  - `decisionBoundary`
  - `decisionOwner`
  - `supports`
  - `requiredExternalInputs`
  - `uncertaintyAssessment.semanticCoverage`
- `oqtReadAcrossSummary.v1` now includes:
  - `assessmentBoundary`
  - `decisionBoundary`
  - `decisionOwner`
  - `supports`
  - `requiredExternalInputs`
- Read-across provenance schemas now allow retry `attempts` in source records when Toolbox call metadata is available.

## What was intentionally not copied

- AOP draft-authoring semantics, because O-QT is not an authoring server.
- CompTox-style numeric applicability-domain confidence, because O-QT does not currently produce a scientifically defensible quantitative AD confidence estimate.
- PBPK qualification or model-trust governance objects, because O-QT should stay focused on OECD QSAR Toolbox evidence packaging rather than model-qualification workflow management.
- Point-of-departure decision objects, because O-QT should not claim ownership of final biological interpretation outside its module scope.
- Suite-level evidence synthesis, because O-QT should remain a module-scoped OECD QSAR Toolbox engine.
