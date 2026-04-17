"""
Explicit, versioned threshold rules for mapping quantitative OECD QSAR Toolbox
metrics into the qualitative uncertainty bands used in O-QT MCP portable handoffs.

These rules are deterministic, fully auditable, and traceable via the
`thresholdRuleRef` field attached to every quantitative metric exported in the
`oqtReadAcrossSummary.v1` uncertainty table and data matrix.

Version history
---------------
oqt-uncertainty-v1.1 (current)
  - Added gradational thresholds for structural and physicochemical similarity.
  - Added raw metric capture for all similarity aspects.
  - Retained presence-based thresholds for profiler, simulator, and QSAR aspects
    where Toolbox APIs do not yet expose continuous confidence scores.
"""

from typing import Any, Dict, List, Optional

THRESHOLD_VERSION = "oqt-uncertainty-v1.1"


def _metric(
    name: str,
    value: float,
    unit: str = "",
    aspect: str = "",
    interpretation: str = "",
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "name": name,
        "value": round(value, 6) if isinstance(value, float) else value,
    }
    if unit:
        payload["unit"] = unit
    if aspect:
        payload["thresholdRuleRef"] = f"{THRESHOLD_VERSION}/{aspect}"
    if interpretation:
        payload["interpretation"] = interpretation
    return payload


# ---------------------------------------------------------------------------
# 1. Structural similarity
# ---------------------------------------------------------------------------
# Threshold rules:
#   assessed_pairs == 0                → not_assessed / low / low / high
#   canonical_ratio == 1.0 AND
#   connectivity_ratio == 1.0          → assessed / high / high / low
#   otherwise                          → assessed / medium / medium / medium
# ---------------------------------------------------------------------------
def assess_structural_similarity(
    structure_summary: Dict[str, Any],
) -> Dict[str, Any]:
    assessed = int(structure_summary.get("assessed_pairs", 0))
    canonical = int(structure_summary.get("canonical_exact_matches", 0))
    connectivity = int(structure_summary.get("connectivity_exact_matches", 0))
    canonical_ratio = canonical / assessed if assessed else 0.0
    connectivity_ratio = connectivity / assessed if assessed else 0.0

    metrics = [
        _metric("assessed_pairs", assessed, "count", "structural_similarity"),
        _metric(
            "canonical_exact_match_ratio",
            canonical_ratio,
            "ratio",
            "structural_similarity",
        ),
        _metric(
            "connectivity_exact_match_ratio",
            connectivity_ratio,
            "ratio",
            "structural_similarity",
        ),
    ]

    if assessed == 0:
        return {
            "status": "not_assessed",
            "data_quality": "low",
            "strength_of_evidence": "low",
            "uncertainty": "high",
            "comments": (
                "Source analogues were resolved, but comparable structure signatures "
                "were not available for the assessed pairs."
            ),
            "metrics": metrics,
        }

    if canonical == assessed and connectivity == assessed:
        return {
            "status": "assessed",
            "data_quality": "high",
            "strength_of_evidence": "high",
            "uncertainty": "low",
            "comments": (
                f"Assessed {assessed} target/source pair(s); all pairs have identical "
                f"canonical SMILES and connectivity."
            ),
            "metrics": metrics,
        }

    return {
        "status": "assessed",
        "data_quality": "medium",
        "strength_of_evidence": "medium",
        "uncertainty": "medium",
        "comments": (
            f"Assessed {assessed} target/source pair(s); "
            f"{canonical} canonical SMILES exact match(es) and "
            f"{connectivity} connectivity exact match(es)."
        ),
        "metrics": metrics,
    }


# ---------------------------------------------------------------------------
# 2. Physicochemical similarity
# ---------------------------------------------------------------------------
# Threshold rules:
#   assessed_pairs == 0                → not_assessed / low / low / high
#   mean_relative_delta <= 0.05        → assessed / high / high / low
#   mean_relative_delta <= 0.20        → assessed / medium / medium / medium
#   otherwise                          → assessed / low / low / high
#
# The 0.05 bound is derived from the existing approx_match rule in
# `_compare_descriptor_values`. The 0.20 bound is a defensible medium-risk
# cutoff for read-across support.
# ---------------------------------------------------------------------------
def assess_physicochemical_similarity(
    physicochemical_comparison: Dict[str, Any],
) -> Dict[str, Any]:
    summary = physicochemical_comparison.get("summary", {})
    assessed = int(summary.get("assessed_pairs", 0))
    shared_count = int(summary.get("shared_descriptor_count", 0))

    # Collect relative deltas across all pair-wise descriptor comparisons
    deltas: List[float] = []
    approx_matches = 0
    total_comparisons = 0
    for comp in physicochemical_comparison.get("comparisons", []) or []:
        for desc_name, desc_val in comp.get("shared_descriptors", {}).items():
            total_comparisons += 1
            if isinstance(desc_val, dict):
                rd = desc_val.get("relative_delta")
                if isinstance(rd, (int, float)):
                    deltas.append(float(rd))
                if desc_val.get("comparison") == "approx_match":
                    approx_matches += 1

    mean_delta = sum(deltas) / len(deltas) if deltas else None
    approx_ratio = approx_matches / total_comparisons if total_comparisons else 0.0

    metrics: List[Dict[str, Any]] = [
        _metric("assessed_pairs", assessed, "count", "physicochemical_similarity"),
        _metric(
            "shared_descriptor_count", shared_count, "count", "physicochemical_similarity"
        ),
        _metric(
            "descriptor_comparison_count", total_comparisons, "count", "physicochemical_similarity"
        ),
        _metric(
            "approx_match_ratio",
            approx_ratio,
            "ratio",
            "physicochemical_similarity",
        ),
    ]
    if mean_delta is not None:
        metrics.append(
            _metric(
                "mean_relative_delta",
                mean_delta,
                "ratio",
                "physicochemical_similarity",
            )
        )

    if assessed == 0:
        return {
            "status": "not_assessed",
            "data_quality": "low",
            "strength_of_evidence": "low",
            "uncertainty": "high",
            "comments": (
                "Target and source substances were resolved, but no overlapping "
                "physicochemical descriptors were exposed in the available records."
            ),
            "metrics": metrics,
        }

    if mean_delta is not None:
        if mean_delta <= 0.05:
            return {
                "status": "assessed",
                "data_quality": "high",
                "strength_of_evidence": "high",
                "uncertainty": "low",
                "comments": (
                    f"Compared {shared_count} shared physicochemical descriptor(s) across "
                    f"{assessed} target/source pair(s); mean relative delta {mean_delta:.4f} "
                    f"(<= 0.05 threshold)."
                ),
                "metrics": metrics,
            }
        if mean_delta <= 0.20:
            return {
                "status": "assessed",
                "data_quality": "medium",
                "strength_of_evidence": "medium",
                "uncertainty": "medium",
                "comments": (
                    f"Compared {shared_count} shared physicochemical descriptor(s) across "
                    f"{assessed} target/source pair(s); mean relative delta {mean_delta:.4f} "
                    f"(0.05–0.20 range)."
                ),
                "metrics": metrics,
            }

    _delta_str = f"{mean_delta:.4f}" if mean_delta is not None else "N/A"
    return {
        "status": "assessed",
        "data_quality": "low",
        "strength_of_evidence": "low",
        "uncertainty": "high",
        "comments": (
            f"Compared {shared_count} shared physicochemical descriptor(s) across "
            f"{assessed} target/source pair(s); mean relative delta "
            f"{_delta_str} (> 0.20 threshold)."
        ),
        "metrics": metrics,
    }


# ---------------------------------------------------------------------------
# 3. Reactivity profile similarity (profiler evidence)
# ---------------------------------------------------------------------------
# Threshold rules:
#   target_profiles == 0               → not_assessed / low / low / high
#   target_profiles > 0 AND
#   source_profiles > 0                → assessed / medium / medium / medium
#   target_profiles > 0                → limited / medium / low / high
# ---------------------------------------------------------------------------
def assess_reactivity_profile_similarity(
    target_profiles: int,
    source_profiles: int,
    grouping_hypothesis: str,
) -> Dict[str, Any]:
    metrics = [
        _metric("target_profile_count", target_profiles, "count", "reactivity_profile_similarity"),
        _metric(
            "source_profile_count", source_profiles, "count", "reactivity_profile_similarity"
        ),
    ]

    if target_profiles == 0:
        return {
            "status": "not_assessed",
            "data_quality": "low",
            "strength_of_evidence": "low",
            "uncertainty": "high",
            "comments": "No profiler evidence was collected for the selected substances.",
            "metrics": metrics,
        }

    if source_profiles > 0:
        return {
            "status": "assessed",
            "data_quality": "medium",
            "strength_of_evidence": "medium",
            "uncertainty": "medium",
            "comments": (
                f"Profiler evidence was gathered under the hypothesis: {grouping_hypothesis}"
            ),
            "metrics": metrics,
        }

    return {
        "status": "limited",
        "data_quality": "medium",
        "strength_of_evidence": "low",
        "uncertainty": "high",
        "comments": (
            "Profiler evidence is only available for the target substance; "
            "source analogue coverage is missing."
        ),
        "metrics": metrics,
    }


# ---------------------------------------------------------------------------
# 4. ADME/TK similarity (metabolism simulator evidence)
# ---------------------------------------------------------------------------
# Threshold rules: same pattern as reactivity profile similarity.
# ---------------------------------------------------------------------------
def assess_adme_tk_similarity(
    target_simulators: int, source_simulators: int
) -> Dict[str, Any]:
    metrics = [
        _metric(
            "target_simulator_count", target_simulators, "count", "adme_tk_similarity"
        ),
        _metric(
            "source_simulator_count", source_simulators, "count", "adme_tk_similarity"
        ),
    ]

    if target_simulators == 0:
        return {
            "status": "not_assessed",
            "data_quality": "low",
            "strength_of_evidence": "low",
            "uncertainty": "high",
            "comments": "No metabolism simulator evidence was collected.",
            "metrics": metrics,
        }

    if source_simulators > 0:
        return {
            "status": "assessed",
            "data_quality": "medium",
            "strength_of_evidence": "medium",
            "uncertainty": "medium",
            "comments": (
                "Metabolism simulator output is available for the target and at least "
                "one source analogue."
            ),
            "metrics": metrics,
        }

    return {
        "status": "limited",
        "data_quality": "medium",
        "strength_of_evidence": "low",
        "uncertainty": "high",
        "comments": "Metabolism simulation is only available for the target substance.",
        "metrics": metrics,
    }


# ---------------------------------------------------------------------------
# 5. Bioactivity similarity
# ---------------------------------------------------------------------------
# Threshold rules:
#   profiler_results or qsar_results present → limited / medium / low / high
#   otherwise                                → not_assessed / low / low / high
# ---------------------------------------------------------------------------
def assess_bioactivity_similarity(
    profiler_results: List[Dict[str, Any]], qsar_results: List[Dict[str, Any]]
) -> Dict[str, Any]:
    has_evidence = bool(profiler_results or qsar_results)
    metrics = [
        _metric(
            "profiler_result_count",
            len(profiler_results),
            "count",
            "bioactivity_similarity",
        ),
        _metric(
            "qsar_result_count", len(qsar_results), "count", "bioactivity_similarity"
        ),
    ]

    if has_evidence:
        return {
            "status": "limited",
            "data_quality": "medium",
            "strength_of_evidence": "low",
            "uncertainty": "high",
            "comments": (
                "Bioactivity support is limited to profiler and QSAR outputs "
                "collected in this dossier."
            ),
            "metrics": metrics,
        }

    return {
        "status": "not_assessed",
        "data_quality": "low",
        "strength_of_evidence": "low",
        "uncertainty": "high",
        "comments": "No bioactivity-oriented evidence was collected.",
        "metrics": metrics,
    }


# ---------------------------------------------------------------------------
# 6. Mechanistic similarity
# ---------------------------------------------------------------------------
# Threshold rules:
#   profiler_groupings or simulator_results present → limited / medium / medium / medium
#   otherwise                                       → not_assessed / low / low / high
# ---------------------------------------------------------------------------
def assess_mechanistic_similarity(
    profiler_groupings: List[Dict[str, Any]], simulator_results: List[Dict[str, Any]]
) -> Dict[str, Any]:
    grouping_count = len(profiler_groupings)
    simulator_count = len(simulator_results)
    has_evidence = bool(grouping_count or simulator_count)

    metrics = [
        _metric(
            "profiler_grouping_count",
            grouping_count,
            "count",
            "mechanistic_similarity",
        ),
        _metric(
            "simulator_result_count",
            simulator_count,
            "count",
            "mechanistic_similarity",
        ),
    ]

    if has_evidence:
        return {
            "status": "limited",
            "data_quality": "medium" if grouping_count else "low",
            "strength_of_evidence": "medium" if grouping_count else "low",
            "uncertainty": "medium" if grouping_count else "high",
            "comments": (
                "Mechanistic support is based on profiler grouping and/or metabolism evidence."
            ),
            "metrics": metrics,
        }

    return {
        "status": "not_assessed",
        "data_quality": "low",
        "strength_of_evidence": "low",
        "uncertainty": "high",
        "comments": "No mechanistic support was collected.",
        "metrics": metrics,
    }


# ---------------------------------------------------------------------------
# 7. Toxicological profile similarity (QSAR predictions)
# ---------------------------------------------------------------------------
# Threshold rules:
#   qsar_result_count == 0             → not_assessed / low / low / high
#   in_domain_ratio == 1.0             → limited / medium / medium / medium
#   otherwise                          → limited / low / low / high
# ---------------------------------------------------------------------------
def assess_toxicological_profile_similarity(
    qsar_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    result_count = len(qsar_results)
    in_domain_count = sum(
        1
        for r in qsar_results
        if isinstance(r, dict)
        and str(r.get("ad_status", "")).lower() in {"indomain", "in_domain"}
    )
    in_domain_ratio = in_domain_count / result_count if result_count else 0.0

    metrics = [
        _metric(
            "qsar_result_count", result_count, "count", "toxicological_profile_similarity"
        ),
        _metric(
            "in_domain_count", in_domain_count, "count", "toxicological_profile_similarity"
        ),
        _metric(
            "in_domain_ratio",
            in_domain_ratio,
            "ratio",
            "toxicological_profile_similarity",
        ),
    ]

    if result_count == 0:
        return {
            "status": "not_assessed",
            "data_quality": "low",
            "strength_of_evidence": "low",
            "uncertainty": "high",
            "comments": "No QSAR model support was included in this dossier.",
            "metrics": metrics,
        }

    if in_domain_ratio == 1.0:
        return {
            "status": "limited",
            "data_quality": "medium",
            "strength_of_evidence": "medium",
            "uncertainty": "medium",
            "comments": (
                f"All {result_count} QSAR prediction(s) are inside the applicability domain."
            ),
            "metrics": metrics,
        }

    return {
        "status": "limited",
        "data_quality": "low",
        "strength_of_evidence": "low",
        "uncertainty": "high",
        "comments": (
            f"{result_count} QSAR prediction(s) collected; only {in_domain_count} "
            f"are in-domain ({in_domain_ratio:.2f} ratio)."
        ),
        "metrics": metrics,
    }


# ---------------------------------------------------------------------------
# 8. Overall uncertainty aggregation
# ---------------------------------------------------------------------------
# Threshold rules (arithmetic mean of per-aspect rank scores):
#   average <= 1.4                     → low
#   average <= 2.2                     → medium
#   average > 2.2                      → high
#
# Aspects that are not_assessed contribute "high" (rank 3).
# ---------------------------------------------------------------------------
def compute_overall_uncertainty(
    similarity_assessment: Dict[str, Dict[str, Any]],
    source_analogue_count: int,
) -> Dict[str, Any]:
    ranks = {"low": 1, "medium": 2, "high": 3}
    scores: List[int] = []
    missing_aspects: List[str] = []
    aspect_metrics: List[Dict[str, Any]] = []

    for aspect, context in similarity_assessment.items():
        uncertainty = str(context.get("uncertainty", "high"))
        score = ranks.get(uncertainty, 3)
        scores.append(score)
        if context.get("status") == "not_assessed":
            missing_aspects.append(aspect)
        # Copy aspect-level metrics into the overall assessment for traceability
        for m in context.get("metrics", []):
            aspect_metrics.append({**m, "name": f"{aspect}:{m['name']}"})

    average = sum(scores) / len(scores) if scores else 3.0
    if average <= 1.4:
        overall_level = "low"
    elif average <= 2.2:
        overall_level = "medium"
    else:
        overall_level = "high"

    if source_analogue_count == 0:
        overall_level = "high"

    metrics = [
        _metric(
            "aspect_count",
            len(scores),
            "count",
            "overall_uncertainty",
        ),
        _metric(
            "average_uncertainty_score",
            average,
            "score",
            "overall_uncertainty",
            interpretation=(
                f"Arithmetic mean of per-aspect ranks (low=1, medium=2, high=3). "
                f"Thresholds: <=1.4 → low, <=2.2 → medium, >2.2 → high."
            ),
        ),
        _metric(
            "band_threshold_low",
            1.4,
            "score",
            "overall_uncertainty",
        ),
        _metric(
            "band_threshold_medium",
            2.2,
            "score",
            "overall_uncertainty",
        ),
    ] + aspect_metrics

    return {
        "overall_level": overall_level,
        "average_score": average,
        "missing_aspects": missing_aspects,
        "metrics": metrics,
    }
