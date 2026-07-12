import unittest

from biomed_workbench.capabilities.evaluation import (
    adjudicate_citation_resolution,
    evaluate_classification_gold_set,
)


def _outcome(source, status, queried_by):
    return {"source": source, "status": status, "queried_by": queried_by}


class EvaluationCapabilityTests(unittest.TestCase):
    def test_citation_matched_wins_over_identifier_and_title_misses(self):
        result = adjudicate_citation_resolution(
            [
                _outcome("crossref", "unmatched", "identifier"),
                _outcome("openalex", "matched", "title"),
                _outcome("arxiv", "skipped", None),
            ]
        )

        self.assertEqual(result["resolution_class"], "verified_match")
        self.assertEqual(result["matched_sources"], ["openalex"])

    def test_citation_identifier_miss_is_distinct_from_title_coverage_gap(self):
        identifier = adjudicate_citation_resolution(
            [_outcome("crossref", "unmatched", "identifier"), _outcome("openalex", "unreachable", None)]
        )
        title = adjudicate_citation_resolution(
            [_outcome("crossref", "unmatched", "title"), _outcome("openalex", "unreachable", None)]
        )

        self.assertEqual(identifier["resolution_class"], "identifier_not_found")
        self.assertEqual(title["resolution_class"], "unresolved")

    def test_citation_outcome_rejects_incoherent_query_modes(self):
        with self.assertRaises(ValueError):
            adjudicate_citation_resolution([_outcome("crossref", "unreachable", "identifier")])
        with self.assertRaises(ValueError):
            adjudicate_citation_resolution([_outcome("crossref", "matched", None)])

    def test_gold_set_reports_explicit_class_metrics_thresholds_and_regression(self):
        result = evaluate_classification_gold_set(
            cases=[
                {"id": "a", "expected_label": "verified", "observed_label": "verified", "expert_label": "verified"},
                {"id": "b", "expected_label": "verified", "observed_label": "unresolved"},
                {"id": "c", "expected_label": "unresolved", "observed_label": "unresolved"},
                {"id": "d", "expected_label": "unresolved", "observed_label": "verified"},
            ],
            labels=["verified", "unresolved"],
            thresholds=[
                {"scope": "aggregate", "class_name": "aggregate", "metric": "accuracy", "comparison": ">=", "threshold_value": 0.75, "minimum_support": 4},
                {"scope": "per_class", "class_name": "verified", "metric": "recall", "comparison": ">=", "threshold_value": 0.75, "minimum_support": 2},
            ],
            gold_provenance={
                "gold_set_id": "citation-resolution",
                "gold_set_version": "1.0.0",
                "annotation_source": "independent dual review",
                "adjudication_method": "consensus with third-reviewer arbitration",
                "independent_from_system": True,
                "leakage_reviewed": True,
            },
            baseline_metrics=[
                {"scope": "aggregate", "class_name": "aggregate", "metric": "accuracy", "value": 0.9, "direction": "higher_is_better"}
            ],
            regression_limit=0.05,
        )

        by_class = {item["class_name"]: item for item in result["class_metrics"]}
        self.assertEqual(result["aggregate_metrics"]["accuracy"], 0.5)
        self.assertEqual(by_class["verified"]["recall"], 0.5)
        self.assertEqual(result["overall_status"], "blocked")
        self.assertIn("aggregate:aggregate:accuracy", result["regression_ids"])
        self.assertEqual(result["expert_concordance"]["labeled_count"], 1)

    def test_gold_set_blocks_circular_or_unreviewed_gold_and_insufficient_support(self):
        result = evaluate_classification_gold_set(
            cases=[
                {"id": "a", "expected_label": "yes", "observed_label": "yes"},
                {"id": "b", "expected_label": "no", "observed_label": "no"},
            ],
            labels=["yes", "no"],
            thresholds=[
                {"scope": "per_class", "class_name": "yes", "metric": "recall", "comparison": ">=", "threshold_value": 0.9, "minimum_support": 2}
            ],
            gold_provenance={
                "gold_set_id": "circular",
                "gold_set_version": "1",
                "annotation_source": "same reducer",
                "adjudication_method": "rule output copied as gold",
                "independent_from_system": False,
                "leakage_reviewed": False,
            },
        )

        self.assertEqual(result["threshold_results"][0]["status"], "insufficient_support")
        self.assertEqual(result["provenance_gate_ids"], ["gold_not_independent", "leakage_not_reviewed"])
        self.assertEqual(result["overall_status"], "blocked")

    def test_gold_set_zero_baseline_improvement_is_not_a_regression(self):
        result = evaluate_classification_gold_set(
            cases=[
                {"id": "a", "expected_label": "yes", "observed_label": "yes"},
                {"id": "b", "expected_label": "no", "observed_label": "no"},
            ],
            labels=["yes", "no"],
            thresholds=[
                {"scope": "aggregate", "class_name": "aggregate", "metric": "accuracy", "comparison": ">=", "threshold_value": 0.9, "minimum_support": 2}
            ],
            gold_provenance={
                "gold_set_id": "independent",
                "gold_set_version": "1",
                "annotation_source": "independent reviewers",
                "adjudication_method": "consensus",
                "independent_from_system": True,
                "leakage_reviewed": True,
            },
            baseline_metrics=[
                {"scope": "aggregate", "class_name": "aggregate", "metric": "accuracy", "value": 0.0, "direction": "higher_is_better"}
            ],
        )

        row = next(item for item in result["baseline_comparisons"] if item["metric"] == "accuracy")
        self.assertEqual(row["change_type"], "improved_from_zero")
        self.assertFalse(row["regression"])
        self.assertEqual(result["overall_status"], "passed")

    def test_gold_set_never_silently_passes_an_empty_declared_class(self):
        result = evaluate_classification_gold_set(
            cases=[{"id": "a", "expected_label": "yes", "observed_label": "yes"}],
            labels=["yes", "no"],
            thresholds=[
                {"scope": "aggregate", "class_name": "aggregate", "metric": "accuracy", "comparison": ">=", "threshold_value": 0.9, "minimum_support": 1}
            ],
            gold_provenance={
                "gold_set_id": "missing-class",
                "gold_set_version": "1",
                "annotation_source": "independent reviewers",
                "adjudication_method": "consensus",
                "independent_from_system": True,
                "leakage_reviewed": True,
            },
        )

        self.assertEqual(result["structural_gate_ids"], ["empty_gold_class:no"])
        self.assertEqual(result["overall_status"], "blocked")


if __name__ == "__main__":
    unittest.main()
