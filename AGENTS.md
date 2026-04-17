# Agent Guidance for O-QT MCP Server

## Scope
This file applies to the `o-qt-mcp-server-public` repository (canonical target).

## Critical Controls (Added 2026-04-16)

### 1. Applicability Domain (AD) Gating
- **Files:** `src/tools/implementations/o_qt_qsar_tools.py`, `src/tools/implementations/toolbox_execution.py`, `src/tools/implementations/workflow_runner.py`
- **Behavior:** `run_qsar_prediction` and `run_qsar_model` now inspect the domain result from the QSAR Toolbox. If the domain status is `"OutOfDomain"`, the result includes:
  - `"ad_status": "out_of_domain"`
  - `"ad_warning": true`
  - `"ad_recommendation": "..."`
- **Rule:** Do NOT remove these fields. The workflow runner surfaces AD warnings in the Markdown summary.

### 2. Human Review Checkpoints (OQT-02)
- **Files:** `src/utils/review.py`, `src/tools/implementations/workflow_runner.py`, `config/tool_permissions.default.json`
- **Behavior:** When `require_human_review=true` is passed to `run_oqt_multiagent_workflow`, the workflow creates up to three checkpoints:
  1. `chemical_identity` — after resolving the input identifier to a Toolbox record
  2. `ad_assessment` — when any QSAR prediction reports `ad_warning=true`
  3. `final_report` — before generating the PDF artifact
- If checkpoints are pending, the workflow returns `status: "review_required"` with `workflow_id` and `review_checkpoints`. No PDF is generated.
- Clients can approve/reject checkpoints via the `approve_workflow_checkpoint` tool, then resume by passing the same `workflow_id` (and optionally `checkpoint_approvals`) to the workflow.
- **Rule:** Do NOT auto-generate artifacts when `require_human_review=true` and checkpoints are pending. Do NOT skip the `ad_assessment` checkpoint for out-of-domain predictions.

### 3. LLM Prompt-Boundary Sanitization
- **File:** `src/utils/sanitization.py`, `src/integrations/oqt_assistant.py`
- **Behavior:** All user-supplied identifiers and context strings are sanitized with `sanitize_for_llm()` before entering the oqt_assistant LLM pipeline.
- **Rule:** If you add new LLM-facing inputs, pipe them through `sanitize_for_llm()`.

### 4. Privacy-Aware Audit Logging
- **Files:** `src/utils/privacy.py`, `src/tools/registry.py`, `src/api/server.py`, `src/utils/logging.py`
- **Behavior:**
  - Audit events hash SMILES, CAS numbers, chemical names, and API keys before logging.
  - The HTTP audit middleware parses query strings into dictionaries so parameter keys remain readable while values are hashed.
  - The `PrivacyLogFilter` scrubs SMILES/CAS patterns from free-text log messages and URL query parameters, and hashes whole-value identifiers in structured log extra fields.
- **Rule:** Do NOT log raw chemical identifiers or secrets. Use `scrub_dict()` on params before audit emit.

### 5. Fallback PDF Provenance
- **File:** `src/utils/pdf_generator.py`
- **Behavior:** The fallback PDF includes:
  - A prominent disclaimer on the first page
  - An "Applicability Domain Warnings" section when out-of-domain predictions are present
  - A "Provenance" section showing model count and AD status
- **Rule:** Keep the disclaimer visible. Do not remove the AD-warning block.

### 6. Search Defaults
- **File:** `src/tools/implementations/workflow_runner.py`, `src/tools/implementations/o_qt_qsar_tools.py`
- **Behavior:** `search_type` default is now `"name"` instead of `"auto"` to reduce silent wrong-chemical resolution.
- **Rule:** Do not revert the default to `"auto"` without explicit user confirmation logic.

## Testing Expectations
- Any change to AD logic must pass `test_run_qsar_prediction_ad_warning_out_of_domain`.
- Any change to privacy logic must pass `tests/utils/test_privacy.py`.
- Any change to sanitization must pass `tests/utils/test_sanitization.py`.
- Any change to PDF generation must pass `test_generate_pdf_report_includes_disclaimer_and_ad_warnings`.
