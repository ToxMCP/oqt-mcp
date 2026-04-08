# OECD 2025 Guidance Review for O-QT MCP

Reviewed sources:

- `Guidance on Grouping of Chemicals, Third Edition` (OECD, 2025), DOI `10.1787/b254a158-en`
- `Customisation Opportunities of IUCLID for the Management of Chemical Data, 4th edition` (OECD, 2025), DOI `10.1787/d8db13f7-en`

Objective:

- Check whether O-QT MCP should change its public contracts, payloads, or packaging semantics to remain aligned with current OECD grouping and data-management expectations.

## Executive judgment

O-QT MCP is still positioned correctly. The reviewed guidance does not argue for turning O-QT into a broader orchestrator or for embedding IUCLID itself inside the MCP. The main gaps are in contract richness and packaging semantics:

- the MCP already produces workflow outputs, grouping/read-across dossiers, uncertainty tables, provenance, and PDF artifacts
- the OECD grouping guidance expects that evidence, applicability domain, uncertainty, and study selection remain inspectable in a structured way
- the IUCLID customisation guidance expects clearer document/package semantics, especially attachments, endpoint summaries, and editable-vs-packaged data bundles

The correct response is an interoperability and reporting pass, not an architecture rewrite.

## What already aligns well

Current O-QT MCP behavior already fits a large part of the OECD guidance:

- `build_grouping_justification` already returns a dossier-shaped object with target resolution, selected analogues, excluded analogues, a data matrix, similarity assessment, endpoint justifications, and uncertainty reporting.
- `run_oqt_multiagent_workflow` already packages JSON, Markdown, and PDF artifacts in one MCP call.
- Provenance has been strengthened across QSAR models, profilers, simulators, and hazard analysis so model ownership, donors, citations, and study metadata can be surfaced when the Toolbox returns them.
- Portable handoff schemas already separate workflow provenance, hazard evidence, and read-across support instead of forcing downstream consumers to parse raw MCP payloads.
- Report tools already expose artifact metadata such as content type, archive members, and extracted PDFs when the Toolbox returns bundles.

This means the baseline scientific and architectural role of the module is sound.

## What the OECD grouping guidance adds

The `Guidance on Grouping of Chemicals` raises five contract-level expectations that should be reflected more explicitly in O-QT MCP.

### 1. Applicability domain and boundaries must be explicit

The guidance treats applicability domain as more than a short note. For analogue and category approaches it expects:

- inclusion and exclusion criteria
- allowed structural differences
- physicochemical boundaries
- metabolic or degradation boundaries
- explanation of why excluded candidates were rejected
- visibility into boundary or sentinel chemicals where relevant

Current O-QT output captures some of this implicitly through:

- `source_analogues`
- `excluded_analogues`
- `structure_comparison`
- `physicochemical_comparison`
- `similarity_assessment`

Recommended MCP change:

- add a first-class `applicability_domain` block to `grouping_justification`
- include `inclusion_criteria`, `exclusion_criteria`, `allowed_differences`, `boundary_notes`, `subcategories`, and `supporting_similarity_contexts`
- surface the same information in `oqtReadAcrossSummary.v1` instead of reducing it to a short free-text summary

### 2. The data matrix should be a portable contract, not just an internal row list

The guidance is very explicit that grouping/read-across reporting should include a matrix of:

- target plus source substances or category members
- endpoints
- physicochemical properties
- kinetics
- profiling
- supporting data tied to the target endpoints
- result type labels such as experimental, planned, QSAR, HTS/HCS/omics, or AOP

Current O-QT already creates a useful `data_matrix`, but it is still an internal workflow structure rather than a stable published contract.

Recommended MCP change:

- publish a new schema such as `oqtGroupingDataMatrix.v1`, or extend `oqtReadAcrossSummary.v1` with a stable `dataMatrix`
- define row-level fields like `substanceRole`, `endpoint`, `methodType`, `resultType`, `valueSummary`, `reference`, `studyReliability`, and `usedForGapFilling`
- ensure excluded candidates can be reported in a companion annex-style structure rather than only through free-text limitations

### 3. Uncertainty should stay inspectable by evidence line

The current implementation is already close here. The guidance expects uncertainty to remain visible by similarity rationale, data quality, strength of evidence, and what is not addressed.

Current O-QT already includes:

- `uncertainty_assessment.assessment_table`
- `accepted_level`
- `overall_level`
- `acceptable_for_context`
- `what_is_not_addressed`

Recommended MCP change:

- keep the current table shape stable and promote it into the portable read-across handoff
- add explicit `decision_context_fit` wording to make it obvious whether residual uncertainty is tolerable for the stated use
- add optional `uncertainty_reduction_actions` so a downstream client can tell whether the next step is more data, narrower scope, or expert review

### 4. Endpoint-specific justification should be closer to an endpoint summary

The guidance requires endpoint-by-endpoint justification, not only an overall narrative. The IUCLID guidance separately highlights that Endpoint Summaries have become part of the OECD Harmonised Templates and include:

- administrative and regulatory flags
- linked studies
- key information
- key values for assessment
- classification or non-classification justification
- attachments

Current O-QT endpoint justifications are useful but still lighter than an OHT-style summary.

Recommended MCP change:

- add an OHT-inspired export layer rather than a full OHT implementation
- introduce a schema such as `oqtEndpointSummary.v1` with:
  - `endpoint`
  - `keyValues`
  - `linkedStudies`
  - `classificationRationale`
  - `supportingEvidence`
  - `attachments`
  - `provenance`
- allow `analyze_chemical_hazard` and `build_grouping_justification` to emit endpoint summaries when the underlying Toolbox response contains enough detail

This would satisfy the reporting direction without forcing the MCP to become an IUCLID clone.

### 5. Bioactivity, AOP, and omics evidence need better placeholders even when not fully implemented

The guidance repeatedly treats HTS/HCS, omics, bioactivity similarity, and AOPs as legitimate supporting lines of evidence for grouping. O-QT today can represent profiler, simulator, and QSAR evidence, but it does not yet provide a clearly named slot for:

- bioactivity-profile evidence
- AOP linkage
- omics-specific metadata
- anchor chemicals or bridging studies

Recommended MCP change:

- extend similarity contexts so they can declare `support_type` values such as `qsar`, `profiler`, `metabolism`, `bioactivity`, `omics`, `aop`, `bridging_study`
- add optional placeholders rather than pretending the Toolbox provides all of these today
- document clearly when a context is `not_assessed` because the MCP lacks source evidence, not because similarity was disproven

## What the IUCLID customisation guidance adds

The `Customisation Opportunities of IUCLID` document is mainly about packaging, document structure, and system integration. It implies four concrete changes for O-QT MCP.

### 1. Attachments should be first-class, not implied

IUCLID treats attachments as standalone files attached either in data fields or in document metadata. O-QT already returns PDFs, archive bundles, JSON, and Markdown, but the portable schema only describes the three primary artifacts at a high level.

Recommended MCP change:

- add an `attachment_manifest` or `attachments` array to `oqtWorkflowRecord.v1`
- include `name`, `role`, `fieldName`, `mediaType`, `encoding`, `sizeBytes`, `sha256`, and `source`
- use the same manifest for ZIP members extracted from Toolbox reports

This makes the MCP output easier to map into dossier-style systems and easier to verify in downstream automation.

### 2. Working bundle vs packaged dossier should be explicit

IUCLID draws a clear distinction between an editable dataset and a packaged, read-only dossier. O-QT today returns assembled responses, but does not declare whether the output is best interpreted as:

- a working evidence bundle still open to extension
- a read-only packaged report for exchange

Recommended MCP change:

- add `package_semantics` to `oqtWorkflowRecord.v1`
- define fields like `mode`, `rootEntityType`, `isReadOnly`, and `containsExternalReferences`
- use values such as `working_bundle` for live MCP responses and `packaged_dossier` for frozen export bundles

This is a small change with high interoperability value.

### 3. Root entity semantics should be declared

IUCLID makes the root entity explicit, with linked sub-entities and documents below it. O-QT does not need IUCLID entity complexity, but it would benefit from declaring the root object in each workflow package.

Recommended MCP change:

- let workflow-style outputs declare a `root_entity`
- support simple values such as `substance_workflow`, `grouping_dossier`, or `hazard_summary`
- allow attachments, endpoint summaries, and study references to point back to that root entity

This keeps the package navigable for clients that need to persist or transform it.

### 4. Public-API style adaptation belongs in a mapping layer, not the core engine

The IUCLID document strongly separates public REST integration from deeper extension work. For O-QT, that means:

- do not build IUCLID customisation logic into the core workflow runner
- do build a clean export or adapter layer that can map O-QT evidence into dossier-oriented structures

Recommended MCP change:

- keep the current MCP response shapes as the execution layer
- add optional export helpers later, for example `export_grouping_bundle` or `build_endpoint_summaries`
- reserve any future IUCLID-specific mapping for a separate adapter module

## Specific gaps in the current published schemas

The existing published schemas are a good baseline, but after reviewing the OECD guidance they are missing a few things:

### `oqtWorkflowRecord.v1`

Needs:

- attachment manifest
- package semantics
- root entity identifier/type
- optional external reference inventory
- optional method catalog for report generation and data extraction

### `oqtReadAcrossSummary.v1`

Needs:

- applicability domain block
- richer analogue selection rationale
- boundary or sentinel chemical notes
- uncertainty table instead of only overall residual uncertainty
- optional data matrix reference or embedded summary
- optional endpoint-summary references

### `oqtHazardEvidenceSummary.v1`

Needs:

- optional endpoint summaries
- optional study reference collection
- explicit evidence-source typing for profiler, QSAR, metabolism, empirical study, or literature
- optional attachment references for generated reports

## What should remain out of scope

These documents do not justify expanding O-QT MCP into the following:

- a suite orchestrator
- a full IUCLID replacement
- a complete implementation of OECD Harmonised Templates
- nanomaterial-specific or UVCB-specific scientific logic that the Toolbox does not already provide in a usable way
- final risk conclusions or cross-module BER/WoE synthesis

Those would increase surface area without improving the current module boundary.

## Recommended implementation sequence

The highest-leverage path is a small contract-focused sequence.

### PR 1. Package semantics and attachment manifest

Files likely affected:

- `schemas/oqtWorkflowRecord.v1.json`
- `src/tools/implementations/workflow_runner.py`
- `src/tools/implementations/toolbox_execution.py`
- tests for schema and runtime payloads

Goal:

- publish a stable artifact/attachment manifest and declare whether the returned package is a working bundle or packaged dossier

### PR 2. Promote the grouping data matrix into a public contract

Files likely affected:

- `schemas/oqtReadAcrossSummary.v1.json`
- possibly a new `schemas/oqtGroupingDataMatrix.v1.json`
- `src/tools/implementations/workflow_runner.py`
- tests and examples

Goal:

- make the current `data_matrix` portable and stable enough for downstream ingestion

### PR 3. Add applicability-domain and boundary semantics

Files likely affected:

- `src/tools/implementations/workflow_runner.py`
- `schemas/oqtReadAcrossSummary.v1.json`
- README and docs

Goal:

- expose inclusion rules, exclusion rules, allowed differences, and subcategory or boundary notes directly in the handoff contract

### PR 4. Add endpoint-summary exports

Files likely affected:

- new schema file for endpoint summaries
- hazard-analysis and grouping outputs
- docs describing the OHT-inspired mapping

Goal:

- provide a compact endpoint summary format that is richer than the current endpoint justification but intentionally lighter than full IUCLID/OHT authoring

## Immediate conclusion

The reviewed OECD documents do not require a redesign of O-QT MCP. They do justify one more reporting-contract pass:

- make evidence packaging more dossier-like
- make attachments and bundle semantics explicit
- publish the data matrix and uncertainty structures as stable portable contracts
- add endpoint-summary style exports where the Toolbox returns enough information

That would materially improve interoperability while preserving the module's current role as a specialized OECD QSAR Toolbox MCP.
