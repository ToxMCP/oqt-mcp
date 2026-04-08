from typing import Any, Dict, List, Optional

from src.tools.provenance import build_endpoint_study_records


def _normalise_scalar(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return str(value)


def _unique(values: List[Any]) -> List[str]:
    seen: set[str] = set()
    items: List[str] = []
    for value in values:
        candidate = _normalise_scalar(value)
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        items.append(candidate)
    return items


def build_source_attribution(provenance: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(provenance, dict):
        return None

    field_map = {
        "title": "title",
        "guid": "guid",
        "caption": "caption",
        "authors": "authors",
        "owner": "owner",
        "description": "description",
        "source_url": "sourceUrl",
        "citation": "citation",
        "study": "study",
        "disclaimer": "disclaimer",
        "help_file": "helpFile",
        "position": "position",
        "additional_info": "additionalInfo",
    }

    payload: Dict[str, Any] = {}
    for source_key, target_key in field_map.items():
        if source_key not in provenance:
            continue
        value = provenance.get(source_key)
        if isinstance(value, dict):
            if value:
                payload[target_key] = value
            continue
        normalised = _normalise_scalar(value)
        if normalised:
            payload[target_key] = normalised

    return payload or None


def build_request_metadata(
    *,
    requested_at: str,
    requested_endpoints: Optional[List[str]] = None,
    requested_profilers: Optional[List[str]] = None,
    requested_simulators: Optional[List[str]] = None,
    requested_qsar_models: Optional[List[str]] = None,
    summary_only: bool,
) -> Dict[str, Any]:
    return {
        "requestedAt": requested_at,
        "requestedEndpoints": _unique(requested_endpoints or []),
        "requestedProfilers": _unique(requested_profilers or []),
        "requestedSimulators": _unique(requested_simulators or []),
        "requestedQsarModels": _unique(requested_qsar_models or []),
        "summaryOnly": bool(summary_only),
    }


def _coverage_status(
    present_count: int,
    *,
    requested_total: Optional[int] = None,
    requested: bool = False,
) -> str:
    if requested_total is not None and requested_total > 0:
        if present_count >= requested_total:
            return "present"
        if present_count > 0:
            return "partial"
        return "none"
    if present_count > 0:
        return "present"
    return "none" if requested else "none"


def build_hazard_uncertainty_assessment(
    *,
    endpoint_record_count: int = 0,
    endpoint_requested: bool = False,
    profiling_record_count: int = 0,
    profiling_requested_total: Optional[int] = None,
    profiling_requested: bool = False,
    metabolism_record_count: int = 0,
    metabolism_requested_total: Optional[int] = None,
    metabolism_requested: bool = False,
    qsar_record_count: int = 0,
    qsar_requested_total: Optional[int] = None,
    qsar_requested: bool = False,
    extra_gaps: Optional[List[str]] = None,
    extra_notes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    coverage = {
        "endpointData": _coverage_status(
            endpoint_record_count, requested=endpoint_requested
        ),
        "profiling": _coverage_status(
            profiling_record_count,
            requested_total=profiling_requested_total,
            requested=profiling_requested,
        ),
        "metabolism": _coverage_status(
            metabolism_record_count,
            requested_total=metabolism_requested_total,
            requested=metabolism_requested,
        ),
        "qsar": _coverage_status(
            qsar_record_count,
            requested_total=qsar_requested_total,
            requested=qsar_requested,
        ),
    }

    gaps: List[str] = []
    if endpoint_requested and coverage["endpointData"] == "none":
        gaps.append("No endpoint study records were returned for the requested endpoint scope.")
    if profiling_requested_total:
        if coverage["profiling"] == "none":
            gaps.append("No requested profiler outputs were returned.")
        elif coverage["profiling"] == "partial":
            gaps.append("Only a subset of the requested profilers returned results.")
    elif profiling_requested and coverage["profiling"] == "none":
        gaps.append("No profiling results were returned for the selected chemical.")
    if metabolism_requested_total:
        if coverage["metabolism"] == "none":
            gaps.append("No requested metabolism simulator outputs were returned.")
        elif coverage["metabolism"] == "partial":
            gaps.append("Only a subset of the requested metabolism simulators returned results.")
    if qsar_requested_total:
        if coverage["qsar"] == "none":
            gaps.append("No requested QSAR model outputs were returned.")
        elif coverage["qsar"] == "partial":
            gaps.append("Only a subset of the requested QSAR models returned results.")

    gaps.extend(_unique(extra_gaps or []))

    confidence_drivers: List[str] = []
    if coverage["endpointData"] == "present":
        confidence_drivers.append("Endpoint study records were retrieved from the Toolbox.")
    if coverage["profiling"] in {"present", "partial"}:
        confidence_drivers.append("Profiling evidence was retrieved for the selected chemical.")
    if coverage["metabolism"] in {"present", "partial"}:
        confidence_drivers.append("Metabolism simulation results were retrieved.")
    if coverage["qsar"] in {"present", "partial"}:
        confidence_drivers.append("QSAR predictions and applicability-domain outputs were retrieved.")

    present_count = sum(1 for value in coverage.values() if value == "present")
    partial_count = sum(1 for value in coverage.values() if value == "partial")
    if present_count >= 3 and not gaps:
        overall_level = "low"
    elif present_count >= 1 or partial_count >= 1:
        overall_level = "medium"
    else:
        overall_level = "high"

    notes = _unique(
        [
            "This uncertainty block characterizes evidence completeness and applicability-domain support, not a probabilistic confidence estimate.",
            *list(extra_notes or []),
        ]
    )

    return {
        "method": "qualitative_evidence_completeness",
        "supportsQuantitativeMetrics": False,
        "overallLevel": overall_level,
        "coverage": coverage,
        "dataGaps": _unique(gaps),
        "confidenceDrivers": _unique(confidence_drivers),
        "notes": notes,
    }


def _block_confidence(status: str) -> str:
    if status == "present":
        return "high"
    if status == "partial":
        return "medium"
    return "low"


def _append_reference(
    records: List[Dict[str, Any]],
    seen: set[tuple[Any, ...]],
    entry: Dict[str, Any],
) -> None:
    key = (
        entry.get("kind"),
        entry.get("label"),
        entry.get("citation"),
        entry.get("study"),
        entry.get("recordId"),
        entry.get("endpoint"),
        entry.get("referenceId"),
    )
    if key in seen:
        return
    seen.add(key)
    records.append(entry)


def _build_reference_records_from_endpoint_summaries(
    endpoint_summaries: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for summary in endpoint_summaries or []:
        if not isinstance(summary, dict):
            continue
        endpoint = _normalise_scalar(summary.get("endpoint"))
        for study_record in summary.get("studyRecords", []) or []:
            if not isinstance(study_record, dict):
                continue
            label = (
                _normalise_scalar(study_record.get("study"))
                or _normalise_scalar(study_record.get("citation"))
                or _normalise_scalar(study_record.get("recordId"))
                or endpoint
                or "Endpoint study record"
            )
            entry: Dict[str, Any] = {
                "kind": "study_record",
                "label": label,
            }
            citation = _normalise_scalar(study_record.get("citation"))
            if citation:
                entry["citation"] = citation
            study = _normalise_scalar(study_record.get("study"))
            if study:
                entry["study"] = study
            record_id = _normalise_scalar(study_record.get("recordId"))
            if record_id:
                entry["recordId"] = record_id
            if endpoint:
                entry["endpoint"] = endpoint
            source_url = _normalise_scalar(
                (study_record.get("metadata") or {}).get("Source URL")
                if isinstance(study_record.get("metadata"), dict)
                else None
            )
            if source_url:
                entry["sourceUrl"] = source_url
            author = _normalise_scalar(study_record.get("author"))
            if author:
                entry["authors"] = author
            owner = _normalise_scalar(
                study_record.get("referenceSource") or study_record.get("database")
            )
            if owner:
                entry["owner"] = owner
            _append_reference(records, seen, entry)
    return records


def _build_reference_records_from_findings(
    findings: Optional[List[Dict[str, Any]]],
    *,
    kind: str,
    identifier_field: str,
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for item in findings or []:
        if not isinstance(item, dict):
            continue
        source = item.get("source")
        source_dict = source if isinstance(source, dict) else {}
        label = (
            _normalise_scalar(source_dict.get("title"))
            or _normalise_scalar(source_dict.get("caption"))
            or _normalise_scalar(item.get(identifier_field))
        )
        if not label:
            continue
        entry: Dict[str, Any] = {"kind": kind, "label": label}
        source_url = _normalise_scalar(source_dict.get("sourceUrl"))
        if source_url:
            entry["sourceUrl"] = source_url
        citation = _normalise_scalar(source_dict.get("citation"))
        if citation:
            entry["citation"] = citation
        study = _normalise_scalar(source_dict.get("study"))
        if study:
            entry["study"] = study
        endpoint = _normalise_scalar(item.get("endpoint"))
        if endpoint:
            entry["endpoint"] = endpoint
        reference_id = _normalise_scalar(item.get(identifier_field))
        if reference_id:
            entry["referenceId"] = reference_id
        authors = _normalise_scalar(source_dict.get("authors"))
        if authors:
            entry["authors"] = authors
        owner = _normalise_scalar(source_dict.get("owner"))
        if owner:
            entry["owner"] = owner
        _append_reference(records, seen, entry)
    return records


def _build_reference_records_from_provenance(
    provenance_items: Optional[List[Dict[str, Any]]],
    *,
    kind: str,
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for item in provenance_items or []:
        if not isinstance(item, dict):
            continue
        label = (
            _normalise_scalar(item.get("title"))
            or _normalise_scalar(item.get("study"))
            or _normalise_scalar(item.get("citation"))
            or _normalise_scalar(item.get("owner"))
        )
        if not label:
            continue
        entry: Dict[str, Any] = {"kind": kind, "label": label}
        citation = _normalise_scalar(item.get("citation"))
        if citation:
            entry["citation"] = citation
        study = _normalise_scalar(item.get("study"))
        if study:
            entry["study"] = study
        source_url = _normalise_scalar(item.get("source_url"))
        if source_url:
            entry["sourceUrl"] = source_url
        authors = _normalise_scalar(item.get("authors"))
        if authors:
            entry["authors"] = authors
        owner = _normalise_scalar(item.get("owner"))
        if owner:
            entry["owner"] = owner
        reference_id = _normalise_scalar(item.get("guid"))
        if reference_id:
            entry["referenceId"] = reference_id
        _append_reference(records, seen, entry)
    return records


def _build_provenance_records(
    *,
    source_name: str,
    field_name: str,
    transformation: str,
    status: str,
    supporting_sources: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    confidence = _block_confidence(status)
    records: List[Dict[str, Any]] = [
        {
            "source": source_name,
            "field": field_name,
            "transformation": transformation,
            "confidence": confidence,
        }
    ]
    seen = {(source_name, field_name, transformation, confidence)}
    for item in supporting_sources or []:
        if not isinstance(item, dict):
            continue
        label = (
            _normalise_scalar(item.get("label"))
            or _normalise_scalar(item.get("title"))
            or _normalise_scalar(item.get("study"))
            or _normalise_scalar(item.get("citation"))
            or _normalise_scalar(item.get("owner"))
        )
        if not label:
            continue
        key = (label, field_name, transformation, confidence)
        if key in seen:
            continue
        seen.add(key)
        records.append(
            {
                "source": label,
                "field": field_name,
                "transformation": transformation,
                "confidence": confidence,
            }
        )
    return records


def build_hazard_evidence_blocks(
    *,
    endpoint_summaries: Optional[List[Dict[str, Any]]] = None,
    profiler_findings: Optional[List[Dict[str, Any]]] = None,
    metabolism_findings: Optional[List[Dict[str, Any]]] = None,
    qsar_findings: Optional[List[Dict[str, Any]]] = None,
    endpoint_provenance: Optional[List[Dict[str, Any]]] = None,
    profiling_provenance: Optional[List[Dict[str, Any]]] = None,
    uncertainty_assessment: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    coverage = (uncertainty_assessment or {}).get("coverage", {}) or {}
    endpoint_status = str(coverage.get("endpointData") or "none")
    profiling_status = str(coverage.get("profiling") or "none")
    metabolism_status = str(coverage.get("metabolism") or "none")
    qsar_status = str(coverage.get("qsar") or "none")

    endpoint_record_count = sum(
        int(summary.get("recordCount") or 0)
        for summary in endpoint_summaries or []
        if isinstance(summary, dict)
    )
    endpoint_key_findings = _unique(
        [
            finding
            for summary in endpoint_summaries or []
            if isinstance(summary, dict)
            for finding in summary.get("keyFindings", []) or []
        ]
    )
    profiler_ok_count = sum(
        1
        for item in profiler_findings or []
        if isinstance(item, dict) and item.get("status") == "ok"
    )
    metabolism_ok_count = sum(
        1
        for item in metabolism_findings or []
        if isinstance(item, dict) and item.get("status") == "ok"
    )
    qsar_ok_count = sum(
        1
        for item in qsar_findings or []
        if isinstance(item, dict) and item.get("status") == "ok"
    )

    endpoint_references = _build_reference_records_from_endpoint_summaries(
        endpoint_summaries
    )
    profiling_references = _build_reference_records_from_findings(
        profiler_findings, kind="profiler", identifier_field="profilerGuid"
    ) or _build_reference_records_from_provenance(
        profiling_provenance, kind="profiling_catalog"
    )
    metabolism_references = _build_reference_records_from_findings(
        metabolism_findings, kind="simulator", identifier_field="simulatorGuid"
    )
    qsar_references = _build_reference_records_from_findings(
        qsar_findings, kind="qsar_model", identifier_field="qsarGuid"
    )

    return {
        "endpointData": {
            "summary": (
                f"Normalized {endpoint_record_count} endpoint study record(s) into "
                f"{len(endpoint_summaries or [])} endpoint summary block(s)."
                if endpoint_record_count
                else "No endpoint study records were retrieved for the requested scope."
            ),
            "status": endpoint_status,
            "basis": "Direct Toolbox endpoint payloads and study metadata were normalized into endpoint summaries.",
            "keyEvidence": endpoint_key_findings,
            "references": endpoint_references,
            "provenanceRecords": _build_provenance_records(
                source_name="OECD QSAR Toolbox WebAPI:data/endpoint",
                field_name="endpointSummaries",
                transformation="Normalized endpoint payloads and MetaData into endpoint study records and endpoint summaries.",
                status=endpoint_status,
                supporting_sources=endpoint_references,
            ),
        },
        "profiling": {
            "summary": (
                f"Structured profiler evidence was retrieved for {profiler_ok_count} requested profiler(s)."
                if profiler_ok_count
                else (
                    "Generic Toolbox profiling output was retrieved without explicit per-profiler findings."
                    if profiling_references
                    else "No profiling evidence was returned."
                )
            ),
            "status": profiling_status,
            "basis": "Toolbox profiling outputs were summarized for alert-oriented evidence and expert review.",
            "keyEvidence": _unique(
                [
                    item.get("summary")
                    for item in profiler_findings or []
                    if isinstance(item, dict)
                ]
            ),
            "references": profiling_references,
            "provenanceRecords": _build_provenance_records(
                source_name="OECD QSAR Toolbox WebAPI:profiling/all",
                field_name="profilers",
                transformation="Normalized profiling outputs into portable profiler evidence summaries.",
                status=profiling_status,
                supporting_sources=profiling_references,
            ),
        },
        "metabolism": {
            "summary": (
                f"Metabolism simulation outputs were retrieved for {metabolism_ok_count} simulator run(s)."
                if metabolism_ok_count
                else "No metabolism simulation evidence was returned."
            ),
            "status": metabolism_status,
            "basis": "Toolbox simulator outputs were summarized to capture metabolite-generation context.",
            "keyEvidence": _unique(
                [
                    item.get("summary")
                    for item in metabolism_findings or []
                    if isinstance(item, dict)
                ]
            ),
            "references": metabolism_references,
            "provenanceRecords": _build_provenance_records(
                source_name="OECD QSAR Toolbox WebAPI:metabolism/simulate",
                field_name="metabolismFindings",
                transformation="Normalized simulator outputs into portable metabolism findings.",
                status=metabolism_status,
                supporting_sources=metabolism_references,
            ),
        },
        "qsar": {
            "summary": (
                f"QSAR predictions were retrieved for {qsar_ok_count} model run(s), including applicability-domain context."
                if qsar_ok_count
                else "No QSAR model evidence was returned."
            ),
            "status": qsar_status,
            "basis": "Toolbox QSAR outputs and domain checks were normalized into portable QSAR findings.",
            "keyEvidence": _unique(
                [
                    item.get("predictionSummary")
                    for item in qsar_findings or []
                    if isinstance(item, dict)
                ]
                + [
                    item.get("domainSummary")
                    for item in qsar_findings or []
                    if isinstance(item, dict)
                ]
            ),
            "references": qsar_references,
            "provenanceRecords": _build_provenance_records(
                source_name="OECD QSAR Toolbox WebAPI:qsar/apply",
                field_name="qsarFindings",
                transformation="Normalized QSAR predictions and domain checks into portable QSAR findings and applicability-domain summaries.",
                status=qsar_status,
                supporting_sources=qsar_references,
            ),
        },
    }


def _interpret_domain_status(value: Any) -> str:
    candidate = (_normalise_scalar(value) or "").lower()
    if not candidate:
        return "not_assessed"
    compact = candidate.replace(" ", "").replace("-", "").replace("_", "")
    if compact in {"indomain", "insideapplicabilitydomain", "withinapplicabilitydomain"}:
        return "in_domain"
    if "out" in compact and "domain" in compact:
        return "out_of_domain"
    if compact in {"notassessed", "unknown", "na", "n/a"}:
        return "not_assessed"
    return "not_assessed"


def build_hazard_applicability_domain(
    qsar_findings: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    assessments: List[Dict[str, Any]] = []
    interpreted_statuses: List[str] = []
    for item in qsar_findings or []:
        if not isinstance(item, dict):
            continue
        raw_status = _normalise_scalar(item.get("domainStatus") or item.get("domainSummary"))
        status = _interpret_domain_status(raw_status)
        if status != "not_assessed":
            interpreted_statuses.append(status)
        assessment: Dict[str, Any] = {
            "status": status,
            "summary": _normalise_scalar(item.get("domainSummary"))
            or _normalise_scalar(item.get("predictionSummary"))
            or "No applicability-domain summary was returned.",
        }
        qsar_guid = _normalise_scalar(item.get("qsarGuid"))
        if qsar_guid:
            assessment["qsarGuid"] = qsar_guid
        endpoint = _normalise_scalar(item.get("endpoint"))
        if endpoint:
            assessment["endpoint"] = endpoint
        if raw_status:
            assessment["domainStatusRaw"] = raw_status
        source = item.get("source")
        if isinstance(source, dict) and source:
            assessment["source"] = source
        assessments.append(assessment)

    if not assessments:
        return {
            "overallStatus": "not_applicable",
            "supportsQuantitativeConfidence": False,
            "confidenceLevel": "low",
            "modelAssessments": [],
            "notes": [
                "No QSAR model outputs were included, so applicability-domain review is not applicable for this hazard summary."
            ],
        }

    has_in = any(status == "in_domain" for status in interpreted_statuses)
    has_out = any(status == "out_of_domain" for status in interpreted_statuses)
    if has_in and has_out:
        overall_status = "mixed"
        confidence_level = "medium"
    elif has_in:
        overall_status = "in_domain"
        confidence_level = "high"
    elif has_out:
        overall_status = "out_of_domain"
        confidence_level = "medium"
    else:
        overall_status = "not_assessed"
        confidence_level = "low"

    notes = [
        "Applicability-domain status reflects Toolbox model-domain outputs only; it is not a probabilistic confidence score."
    ]
    if overall_status == "mixed":
        notes.append(
            "At least one QSAR model was reported in-domain and at least one was not, so downstream review should inspect model-level assessments individually."
        )
    if overall_status == "not_assessed":
        notes.append(
            "One or more QSAR results were returned without a machine-interpretable domain status."
        )

    return {
        "overallStatus": overall_status,
        "supportsQuantitativeConfidence": False,
        "confidenceLevel": confidence_level,
        "modelAssessments": assessments,
        "notes": notes,
    }


def build_hazard_semantic_coverage(
    *,
    endpoint_summaries: Optional[List[Dict[str, Any]]] = None,
    applicability_domain: Optional[Dict[str, Any]] = None,
    uncertainty_assessment: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    coverage = (uncertainty_assessment or {}).get("coverage", {}) or {}
    endpoint_status = str(coverage.get("endpointData") or "none")
    profiling_status = str(coverage.get("profiling") or "none")
    metabolism_status = str(coverage.get("metabolism") or "none")
    qsar_status = str(coverage.get("qsar") or "none")
    typed_study_records = (
        "present"
        if any(
            isinstance(item, dict) and (item.get("studyRecords") or [])
            for item in endpoint_summaries or []
        )
        else "none"
    )
    typed_applicability = (
        "present"
        if (applicability_domain or {}).get("overallStatus") not in {None, "not_applicable"}
        else "not_applicable"
    )

    qualitative_components = [
        name
        for name, status in (
            ("endpoint_data", endpoint_status),
            ("profiling", profiling_status),
            ("metabolism", metabolism_status),
            ("qsar", qsar_status),
            ("applicability_domain", typed_applicability),
        )
        if status not in {"none", "not_applicable"}
    ]

    return {
        "overallQuantificationStatus": "qualitative_only",
        "probabilisticConfidenceStatus": "not_supported",
        "typedStudyRecordStatus": typed_study_records,
        "typedApplicabilityDomainStatus": typed_applicability,
        "qualitativeComponents": qualitative_components,
        "quantifiedComponents": [],
    }


def build_decision_owner() -> str:
    return "downstream_expert_review"


def build_hazard_assessment_boundary() -> Dict[str, Any]:
    return {
        "scope": "module_scoped_toolbox_evidence_packaging",
        "includes": [
            "OECD QSAR Toolbox endpoint-study normalization and evidence packaging.",
            "Module-local profiler, metabolism, and QSAR evidence normalization when requested.",
            "Module-local applicability-domain review for Toolbox QSAR outputs.",
        ],
        "excludes": [
            "Cross-module synthesis with non-O-QT evidence sources.",
            "Final hazard classification, labeling, or regulatory decision text.",
            "Exposure, PBPK, or risk-characterization judgments.",
        ],
    }


def build_hazard_decision_boundary() -> Dict[str, Any]:
    return {
        "supportedDecisions": [
            "Use as typed hazard evidence input for downstream review.",
            "Use to audit which Toolbox evidence and provenance records were packaged.",
        ],
        "prohibitedDecisions": [
            "Do not treat as a final hazard classification or regulatory conclusion.",
            "Do not treat qualitative uncertainty as a probabilistic confidence estimate.",
        ],
        "reviewRequired": True,
    }


def build_hazard_supports(
    *,
    endpoint_summaries: Optional[List[Dict[str, Any]]] = None,
    profiler_findings: Optional[List[Dict[str, Any]]] = None,
    applicability_domain: Optional[Dict[str, Any]] = None,
) -> Dict[str, bool]:
    has_study_evidence = any(
        isinstance(item, dict) and (item.get("studyRecords") or [])
        for item in endpoint_summaries or []
    )
    has_profiler_evidence = any(
        isinstance(item, dict) and item.get("status") in {"ok", "partial"}
        for item in profiler_findings or []
    )
    has_applicability_review = (
        (applicability_domain or {}).get("overallStatus") not in {None, "not_applicable"}
    )
    return {
        "typedStudyEvidence": has_study_evidence,
        "typedProfilerEvidence": has_profiler_evidence,
        "typedApplicabilityDomainReview": bool(has_applicability_review),
        "crossModuleSynthesis": False,
        "finalDecisionRecommendation": False,
    }


def build_hazard_required_external_inputs() -> List[str]:
    return [
        "Downstream cross-module evidence synthesis and expert review.",
        "Final hazard interpretation or classification policy.",
        "Exposure or internal-dose context when the decision requires it.",
    ]


def build_read_across_assessment_boundary() -> Dict[str, Any]:
    return {
        "scope": "module_scoped_grouping_dossier_packaging",
        "includes": [
            "OECD QSAR Toolbox grouping/read-across dossier packaging.",
            "Module-local analogue normalization, applicability-domain packaging, and uncertainty-table export.",
            "Portable evidence-matrix packaging for downstream audit and review.",
        ],
        "excludes": [
            "Final regulatory acceptance of read-across.",
            "Cross-module synthesis with non-O-QT evidence sources.",
            "Final hazard, exposure, or risk decisions.",
        ],
    }


def build_read_across_decision_boundary() -> Dict[str, Any]:
    return {
        "supportedDecisions": [
            "Use as typed grouping or read-across evidence input for downstream review.",
            "Use to audit analogue selection, evidence rows, and aspect-level uncertainty packaging.",
        ],
        "prohibitedDecisions": [
            "Do not treat as final regulatory acceptance of read-across.",
            "Do not treat as a complete evidence-of-record without expert review.",
        ],
        "reviewRequired": True,
    }


def build_read_across_supports() -> Dict[str, bool]:
    return {
        "typedGroupingDossier": True,
        "typedApplicabilityDomain": True,
        "typedUncertaintyTable": True,
        "finalReadAcrossAcceptance": False,
        "finalDecisionRecommendation": False,
    }


def build_read_across_required_external_inputs() -> List[str]:
    return [
        "Expert review of analogue suitability and endpoint relevance.",
        "Endpoint-specific regulatory acceptance criteria.",
        "Downstream evidence synthesis and final decision policy.",
    ]


def build_endpoint_summaries_from_payload(
    endpoint_payload: Any,
    *,
    requested_endpoint: Optional[str] = None,
    resolved_position: Optional[str] = None,
) -> List[Dict[str, Any]]:
    study_records = build_endpoint_study_records(endpoint_payload)
    if not study_records:
        if not requested_endpoint and not resolved_position:
            return []
        summary: Dict[str, Any] = {
            "endpoint": requested_endpoint or resolved_position or "Unspecified endpoint",
            "recordCount": 0,
            "summaryLevel": "none",
            "evidenceBasis": "experimental_data",
            "keyFindings": ["No endpoint study records were returned."],
            "studyRecords": [],
        }
        if resolved_position:
            summary["rigidPath"] = resolved_position
        return [summary]

    grouped: Dict[str, Dict[str, Any]] = {}
    for record in study_records:
        endpoint = record.get("endpoint") or requested_endpoint or "Unspecified endpoint"
        bucket = grouped.setdefault(
            endpoint,
            {
                "endpoint": endpoint,
                "recordCount": 0,
                "summaryLevel": "detail",
                "evidenceBasis": "experimental_data",
                "keyFindings": [],
                "studyRecords": [],
            },
        )
        bucket["recordCount"] += 1
        bucket["studyRecords"].append(record)
        rigid_path = record.get("rigidPath") or resolved_position
        if rigid_path and "rigidPath" not in bucket:
            bucket["rigidPath"] = rigid_path

        overall_result = _normalise_scalar(record.get("overallResult"))
        value = _normalise_scalar(record.get("value"))
        unit = _normalise_scalar(record.get("unit"))
        if overall_result:
            bucket["keyFindings"].append(f"Overall result: {overall_result}")
        elif value:
            finding = f"Reported value: {value}"
            if unit:
                finding = f"{finding} {unit}"
            bucket["keyFindings"].append(finding)

    for bucket in grouped.values():
        bucket["keyFindings"] = _unique(bucket["keyFindings"])

    return list(grouped.values())


def build_endpoint_summaries_from_qsar_results(
    results: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for item in results or []:
        if not isinstance(item, dict):
            continue
        prediction = item.get("prediction")
        if not isinstance(prediction, dict):
            continue

        endpoint = _normalise_scalar(prediction.get("Endpoint"))
        if not endpoint:
            provenance = item.get("model_provenance")
            endpoint = _normalise_scalar(
                provenance.get("title") if isinstance(provenance, dict) else None
            )
        if not endpoint:
            endpoint = _normalise_scalar(item.get("qsar_guid")) or "Unspecified endpoint"

        bucket = grouped.setdefault(
            endpoint,
            {
                "endpoint": endpoint,
                "recordCount": 0,
                "summaryLevel": "summary",
                "evidenceBasis": "qsar_prediction",
                "keyFindings": [],
                "studyRecords": [],
            },
        )
        bucket["recordCount"] += 1

        rigid_path = _normalise_scalar(prediction.get("RigidPath"))
        if rigid_path and "rigidPath" not in bucket:
            bucket["rigidPath"] = rigid_path

        value = _normalise_scalar(prediction.get("Value"))
        unit = _normalise_scalar(prediction.get("Unit"))
        if value:
            finding = f"Predicted value: {value}"
            if unit:
                finding = f"{finding} {unit}"
            bucket["keyFindings"].append(finding)

        domain = _normalise_scalar(
            prediction.get("DomainResult")
            or prediction.get("Domain")
            or item.get("domain")
        )
        if domain:
            bucket["keyFindings"].append(f"Applicability domain: {domain}")

    for bucket in grouped.values():
        bucket["keyFindings"] = _unique(bucket["keyFindings"])

    return list(grouped.values())
