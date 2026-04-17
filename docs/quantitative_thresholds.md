# O-QT MCP Quantitative Uncertainty Thresholds

**Version:** `oqt-uncertainty-v1.1`  
**Scope:** `build_grouping_justification` portable handoffs (`oqtReadAcrossSummary.v1`)  
**Goal:** Make the mapping from raw OECD QSAR Toolbox metrics to qualitative uncertainty bands fully explicit, versioned, auditable, and scientifically defensible.

## Why this matters

Regulatory frameworks (ECHA RAAF, OECD Grouping Guidance) expect that uncertainty assessments can be reconstructed by an independent reviewer. A bare `low` / `medium` / `high` label is not enough unless the reviewer can also see:

1. **Which raw numbers were used.**
2. **Which threshold rule produced the band.**
3. **When the rule was applied (version).**

This document defines the threshold rule set. Every quantitative metric emitted in an O-QT MCP portable handoff carries a `thresholdRuleRef` field pointing back to this version.

## Rule architecture

Each similarity aspect evaluated in a grouping dossier has its own rule sub-section. The rules are **deterministic**: given the same raw Toolbox payload, they will always produce the same qualitative band.

The qualitative bands are encoded as ranks for arithmetic aggregation:

| Band   | Rank | Meaning in this context                                    |
|--------|------|------------------------------------------------------------|
| `low`  | 1    | Strong support, high confidence, well-covered evidence     |
| `medium`| 2   | Partial support, moderate confidence, some gaps remain     |
| `high` | 3    | Weak support, low confidence, major gaps or missing data   |

---

## 1. Structural similarity

**Rule ref:** `oqt-uncertainty-v1.1/structural_similarity`

### Raw metrics captured
- `assessed_pairs` — number of target/source pairs with comparable structure signatures
- `canonical_exact_match_ratio` — pairs with identical canonical SMILES / assessed_pairs
- `connectivity_exact_match_ratio` — pairs with identical connectivity strings / assessed_pairs

### Threshold rules
| Condition | Status | Data quality | Strength of evidence | Uncertainty |
|-----------|--------|--------------|----------------------|-------------|
| `assessed_pairs == 0` | `not_assessed` | `low` | `low` | `high` |
| `canonical_ratio == 1.0` **and** `connectivity_ratio == 1.0` | `assessed` | `high` | `high` | `low` |
| Otherwise | `assessed` | `medium` | `medium` | `medium` |

### Scientific rationale
Exact canonical SMILES equality guarantees identical atom connectivity and stereochemistry (where encoded). Exact connectivity equality further guarantees the same bond graph. When **all** assessed pairs match on both measures, the structural read-across basis is very strong. When only some pairs match, structural similarity is plausible but not guaranteed across the entire analogue set.

---

## 2. Physicochemical similarity

**Rule ref:** `oqt-uncertainty-v1.1/physicochemical_similarity`

### Raw metrics captured
- `assessed_pairs` — pairs with at least one overlapping descriptor
- `shared_descriptor_count` — total overlapping descriptors found
- `descriptor_comparison_count` — individual descriptor comparisons performed
- `approx_match_ratio` — comparisons flagged as `approx_match` / total comparisons
- `mean_relative_delta` — arithmetic mean of `relative_delta` across all numeric descriptor comparisons

### Threshold rules
| Condition | Status | Data quality | Strength of evidence | Uncertainty |
|-----------|--------|--------------|----------------------|-------------|
| `assessed_pairs == 0` | `not_assessed` | `low` | `low` | `high` |
| `mean_relative_delta <= 0.05` | `assessed` | `high` | `high` | `low` |
| `mean_relative_delta <= 0.20` | `assessed` | `medium` | `medium` | `medium` |
| `mean_relative_delta > 0.20` | `assessed` | `low` | `low` | `high` |

### Scientific rationale
The `0.05` bound is derived from the existing O-QT MCP `_compare_descriptor_values` approx-match rule (`absolute_delta <= 0.01` **or** `relative_delta <= 0.05`). A mean relative delta below this threshold indicates that the analogue set is physicochemically tightly clustered. The `0.20` bound is a conservative medium-risk cutoff: larger differences may still be acceptable for some endpoints, but they materially weaken the read-across justification unless bridged by other evidence.

---

## 3. Reactivity profile similarity (profiler evidence)

**Rule ref:** `oqt-uncertainty-v1.1/reactivity_profile_similarity`

### Raw metrics captured
- `target_profile_count` — profiler runs on the target substance
- `source_profile_count` — profiler runs on source analogues

### Threshold rules
| Condition | Status | Data quality | Strength of evidence | Uncertainty |
|-----------|--------|--------------|----------------------|-------------|
| `target_profiles == 0` | `not_assessed` | `low` | `low` | `high` |
| `target_profiles > 0` **and** `source_profiles > 0` | `assessed` | `medium` | `medium` | `medium` |
| `target_profiles > 0` only | `limited` | `medium` | `low` | `high` |

### Scientific rationale
Profiler evidence is currently treated as presence-based because the OECD QSAR Toolbox WebAPI returns discrete classifications rather than continuous similarity scores. When both target and source profiles are available, the reactivity hypothesis can be checked for consistency. When only the target is profiled, the analogue set cannot be validated for the same reactivity mechanism.

---

## 4. ADME / TK similarity (metabolism simulator evidence)

**Rule ref:** `oqt-uncertainty-v1.1/adme_tk_similarity`

### Raw metrics captured
- `target_simulator_count` — metabolism simulations for the target
- `source_simulator_count` — metabolism simulations for source analogues

### Threshold rules
| Condition | Status | Data quality | Strength of evidence | Uncertainty |
|-----------|--------|--------------|----------------------|-------------|
| `target_simulators == 0` | `not_assessed` | `low` | `low` | `high` |
| `target_simulators > 0` **and** `source_simulators > 0` | `assessed` | `medium` | `medium` | `medium` |
| `target_simulators > 0` only | `limited` | `medium` | `low` | `high` |

### Scientific rationale
Same presence-based logic as profiler evidence. Metabolite overlap or metabolic pathway similarity can only be evaluated when both target and at least one source analogue have been simulated.

---

## 5. Bioactivity similarity

**Rule ref:** `oqt-uncertainty-v1.1/bioactivity_similarity`

### Raw metrics captured
- `profiler_result_count`
- `qsar_result_count`

### Threshold rules
| Condition | Status | Data quality | Strength of evidence | Uncertainty |
|-----------|--------|--------------|----------------------|-------------|
| No profiler or QSAR results | `not_assessed` | `low` | `low` | `high` |
| Any results present | `limited` | `medium` | `low` | `high` |

### Scientific rationale
Bioactivity evidence in O-QT MCP is currently indirect (profiler classifications and QSAR predictions). Because it does not yet incorporate direct HTS/HCS assay readouts with dose-response data, the framework assigns a conservative `low` strength of evidence and `high` uncertainty even when results are present.

---

## 6. Mechanistic similarity

**Rule ref:** `oqt-uncertainty-v1.1/mechanistic_similarity`

### Raw metrics captured
- `profiler_grouping_count` — `group_by_profiler` results
- `simulator_result_count` — metabolism simulator results

### Threshold rules
| Condition | Status | Data quality | Strength of evidence | Uncertainty |
|-----------|--------|--------------|----------------------|-------------|
| No groupings and no simulations | `not_assessed` | `low` | `low` | `high` |
| Profiler groupings present | `limited` | `medium` | `medium` | `medium` |
| Only simulator results present | `limited` | `medium` | `low` | `high` |

### Scientific rationale
Profiler groupings provide explicit mechanistic category assignments, which are stronger than mere presence/absence of simulator output. Simulator output alone supports metabolic plausibility but does not directly confirm a shared mechanism of action.

---

## 7. Toxicological profile similarity (QSAR predictions)

**Rule ref:** `oqt-uncertainty-v1.1/toxicological_profile_similarity`

### Raw metrics captured
- `qsar_result_count` — number of QSAR predictions included
- `in_domain_count` — predictions inside the model applicability domain
- `in_domain_ratio` — `in_domain_count / qsar_result_count`

### Threshold rules
| Condition | Status | Data quality | Strength of evidence | Uncertainty |
|-----------|--------|--------------|----------------------|-------------|
| `qsar_result_count == 0` | `not_assessed` | `low` | `low` | `high` |
| `in_domain_ratio == 1.0` | `limited` | `medium` | `medium` | `medium` |
| `in_domain_ratio < 1.0` | `limited` | `low` | `low` | `high` |

### Scientific rationale
QSAR predictions are only scientifically defensible when the substance falls inside the model's applicability domain. A ratio of `1.0` means every included prediction is domain-valid. Any out-of-domain prediction degrades the toxicological profile support because the model's training space no longer covers the substance.

---

## 8. Overall uncertainty aggregation

**Rule ref:** `oqt-uncertainty-v1.1/overall_uncertainty`

### Raw metrics captured
- `aspect_count` — number of similarity aspects evaluated (always 7)
- `average_uncertainty_score` — arithmetic mean of per-aspect rank scores
- `band_threshold_low` — `1.4`
- `band_threshold_medium` — `2.2`

### Threshold rules
| `average_uncertainty_score` | Overall level |
|-----------------------------|---------------|
| `<= 1.4` | `low` |
| `<= 2.2` | `medium` |
| `> 2.2` | `high` |

**Additional hard rule:** If `source_analogue_count == 0`, overall level is forced to `high` regardless of the average score, because read-across without analogues is not defensible.

### Scientific rationale
The aggregation is a simple arithmetic mean of ordinal ranks. This is intentionally conservative: a single `high`-uncertainty aspect pulls the average upward quickly. The thresholds (`1.4` and `2.2`) were chosen so that:
- All 7 aspects at `low` (score 1.0) → overall `low`
- A roughly even mix of `low`, `medium`, and `high` → overall `medium`
- Any majority of `high` aspects → overall `high`

Because the scale is ordinal, not interval, the mean is used as a **pragmatic ordering device** rather than a rigorous probabilistic calculation. The raw per-aspect scores are always exposed in `quantitativeMetrics`, allowing downstream reviewers to substitute their own aggregation logic if desired.

---

## Traceability in portable handoffs

Every metric object in `oqtReadAcrossSummary.v1` contains:

```json
{
  "name": "canonical_exact_match_ratio",
  "value": 1.0,
  "unit": "ratio",
  "thresholdRuleRef": "oqt-uncertainty-v1.1/structural_similarity",
  "interpretation": "All assessed pairs have identical canonical SMILES"
}
```

This means an auditor can:
1. Look up the rule version in this document.
2. Re-run the exact threshold logic independently.
3. Contest the band assignment using the raw numbers provided.

## Version history

| Version | Date | Changes |
|---------|------|---------|
| `oqt-uncertainty-v1.1` | 2026-04-16 | Added gradational thresholds for structural and physicochemical similarity; added raw metric capture for all aspects; documented all threshold rules. |
