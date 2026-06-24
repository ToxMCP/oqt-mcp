"""Tests for explicit, versioned uncertainty threshold rules."""

import pytest

from src.tools.implementations import uncertainty_thresholds as ut


class TestStructuralSimilarity:
    def test_not_assessed_when_zero_pairs(self):
        result = ut.assess_structural_similarity({"assessed_pairs": 0})
        assert result["status"] == "not_assessed"
        assert result["uncertainty"] == "high"
        assert any(m["name"] == "assessed_pairs" and m["value"] == 0 for m in result["metrics"])

    def test_high_when_all_exact_matches(self):
        result = ut.assess_structural_similarity(
            {"assessed_pairs": 2, "canonical_exact_matches": 2, "connectivity_exact_matches": 2}
        )
        assert result["status"] == "assessed"
        assert result["data_quality"] == "high"
        assert result["strength_of_evidence"] == "high"
        assert result["uncertainty"] == "low"

    def test_medium_when_partial_matches(self):
        result = ut.assess_structural_similarity(
            {"assessed_pairs": 2, "canonical_exact_matches": 1, "connectivity_exact_matches": 0}
        )
        assert result["status"] == "assessed"
        assert result["data_quality"] == "medium"
        assert result["strength_of_evidence"] == "medium"
        assert result["uncertainty"] == "medium"


class TestPhysicochemicalSimilarity:
    def test_not_assessed_when_no_pairs(self):
        result = ut.assess_physicochemical_similarity(
            {"summary": {"assessed_pairs": 0}, "comparisons": []}
        )
        assert result["status"] == "not_assessed"
        assert result["uncertainty"] == "high"

    def test_low_uncertainty_for_tight_delta(self):
        result = ut.assess_physicochemical_similarity(
            {
                "summary": {"assessed_pairs": 1, "shared_descriptor_count": 3},
                "comparisons": [
                    {
                        "shared_descriptors": {
                            "mw": {"relative_delta": 0.02, "comparison": "approx_match"},
                            "logp": {"relative_delta": 0.03, "comparison": "approx_match"},
                        }
                    }
                ],
            }
        )
        assert result["uncertainty"] == "low"
        assert result["data_quality"] == "high"

    def test_medium_uncertainty_for_moderate_delta(self):
        result = ut.assess_physicochemical_similarity(
            {
                "summary": {"assessed_pairs": 1, "shared_descriptor_count": 2},
                "comparisons": [
                    {
                        "shared_descriptors": {
                            "mw": {"relative_delta": 0.10, "comparison": "different"},
                            "logp": {"relative_delta": 0.15, "comparison": "different"},
                        }
                    }
                ],
            }
        )
        assert result["uncertainty"] == "medium"
        assert result["data_quality"] == "medium"

    def test_high_uncertainty_for_large_delta(self):
        result = ut.assess_physicochemical_similarity(
            {
                "summary": {"assessed_pairs": 1, "shared_descriptor_count": 2},
                "comparisons": [
                    {
                        "shared_descriptors": {
                            "mw": {"relative_delta": 0.50, "comparison": "different"},
                            "logp": {"relative_delta": 0.60, "comparison": "different"},
                        }
                    }
                ],
            }
        )
        assert result["uncertainty"] == "high"
        assert result["data_quality"] == "low"


class TestReactivityProfileSimilarity:
    def test_not_assessed_without_target_profiles(self):
        result = ut.assess_reactivity_profile_similarity(0, 0, "h")
        assert result["status"] == "not_assessed"
        assert result["uncertainty"] == "high"

    def test_medium_with_target_and_source(self):
        result = ut.assess_reactivity_profile_similarity(1, 1, "h")
        assert result["status"] == "assessed"
        assert result["uncertainty"] == "medium"

    def test_high_with_target_only(self):
        result = ut.assess_reactivity_profile_similarity(1, 0, "h")
        assert result["status"] == "limited"
        assert result["uncertainty"] == "high"


class TestToxicologicalProfileSimilarity:
    def test_not_assessed_without_qsar(self):
        result = ut.assess_toxicological_profile_similarity([])
        assert result["status"] == "not_assessed"
        assert result["uncertainty"] == "high"

    def test_medium_when_all_in_domain(self):
        result = ut.assess_toxicological_profile_similarity(
            [{"ad_status": "in_domain"}, {"ad_status": "in_domain"}]
        )
        assert result["status"] == "limited"
        assert result["uncertainty"] == "medium"
        assert any(m["name"] == "in_domain_ratio" and m["value"] == 1.0 for m in result["metrics"])

    def test_high_when_some_out_of_domain(self):
        result = ut.assess_toxicological_profile_similarity(
            [{"ad_status": "in_domain"}, {"ad_status": "out_of_domain"}]
        )
        assert result["status"] == "limited"
        assert result["uncertainty"] == "high"
        assert any(m["name"] == "in_domain_ratio" and m["value"] == 0.5 for m in result["metrics"])


class TestOverallUncertainty:
    def test_low_when_all_aspects_low(self):
        assessment = {
            "a1": {"status": "assessed", "uncertainty": "low", "metrics": []},
            "a2": {"status": "assessed", "uncertainty": "low", "metrics": []},
        }
        result = ut.compute_overall_uncertainty(assessment, 2)
        assert result["overall_level"] == "low"
        assert result["average_score"] == 1.0

    def test_medium_for_mixed_scores(self):
        assessment = {
            "a1": {"status": "assessed", "uncertainty": "low", "metrics": []},
            "a2": {"status": "assessed", "uncertainty": "medium", "metrics": []},
            "a3": {"status": "assessed", "uncertainty": "high", "metrics": []},
        }
        result = ut.compute_overall_uncertainty(assessment, 3)
        assert result["overall_level"] == "medium"
        assert result["average_score"] == 2.0

    def test_high_for_all_high(self):
        assessment = {
            "a1": {"status": "not_assessed", "uncertainty": "high", "metrics": []},
            "a2": {"status": "not_assessed", "uncertainty": "high", "metrics": []},
        }
        result = ut.compute_overall_uncertainty(assessment, 2)
        assert result["overall_level"] == "high"
        assert result["average_score"] == 3.0

    def test_forced_high_when_no_source_analogues(self):
        assessment = {
            "a1": {"status": "assessed", "uncertainty": "low", "metrics": []},
        }
        result = ut.compute_overall_uncertainty(assessment, 0)
        assert result["overall_level"] == "high"

    def test_metrics_include_thresholds(self):
        assessment = {
            "a1": {"status": "assessed", "uncertainty": "low", "metrics": [{"name": "x", "value": 1}]},
        }
        result = ut.compute_overall_uncertainty(assessment, 1)
        assert any(m["name"] == "band_threshold_low" and m["value"] == 1.4 for m in result["metrics"])
        assert any(m["name"] == "band_threshold_medium" and m["value"] == 2.2 for m in result["metrics"])
        assert any(m["name"] == "a1:x" and m["value"] == 1 for m in result["metrics"])
