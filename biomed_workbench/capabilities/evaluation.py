"""Deterministic scientific evaluation and evidence-adjudication capabilities."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from typing import Any


_RESOLUTION_STATUSES = {"matched", "unmatched", "unreachable", "skipped"}
_QUERY_MODES = {"identifier", "title"}
_AGGREGATE_METRICS = {"accuracy", "balanced_accuracy", "macro_precision", "macro_recall", "macro_f1"}
_CLASS_METRICS = {"precision", "recall", "f1", "one_vs_rest_accuracy"}
_COMPARISONS = {">=", ">", "<=", "<"}


def adjudicate_citation_resolution(resolver_outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    """Reduce independently observed resolver outcomes without overstating nonexistence."""
    if not isinstance(resolver_outcomes, list) or not 1 <= len(resolver_outcomes) <= 32:
        raise ValueError("resolver_outcomes must contain 1 to 32 records")
    seen_sources = set()
    normalized = []
    counts: Counter[str] = Counter()
    for index, outcome in enumerate(resolver_outcomes, start=1):
        if not isinstance(outcome, dict) or set(outcome) != {"source", "status", "queried_by"}:
            raise ValueError(f"resolver outcome {index} must contain exactly source, status, and queried_by")
        source = outcome["source"]
        status = outcome["status"]
        queried_by = outcome["queried_by"]
        if not isinstance(source, str) or source != source.strip() or not 1 <= len(source) <= 128 or source in seen_sources:
            raise ValueError("resolver sources must be nonempty, normalized, and unique")
        if status not in _RESOLUTION_STATUSES:
            raise ValueError(f"resolver {source} has an unsupported status")
        if status in {"matched", "unmatched"} and queried_by not in _QUERY_MODES:
            raise ValueError(f"resolver {source} requires identifier or title queried_by")
        if status in {"unreachable", "skipped"} and queried_by is not None:
            raise ValueError(f"resolver {source} must use null queried_by when not executed")
        seen_sources.add(source)
        counts[status] += 1
        normalized.append({"source": source, "status": status, "queried_by": queried_by})

    matched_sources = [item["source"] for item in normalized if item["status"] == "matched"]
    identifier_unmatched_sources = [
        item["source"]
        for item in normalized
        if item["status"] == "unmatched" and item["queried_by"] == "identifier"
    ]
    title_only_unmatched_sources = [
        item["source"]
        for item in normalized
        if item["status"] == "unmatched" and item["queried_by"] == "title"
    ]
    if matched_sources:
        resolution_class = "verified_match"
        interpretation_status = "eligible_after_identity_and_claim_support_review"
    elif identifier_unmatched_sources:
        resolution_class = "identifier_not_found"
        interpretation_status = "blocked_pending_manual_resolution"
    else:
        resolution_class = "unresolved"
        interpretation_status = "blocked_pending_additional_resolution"
    return {
        "resolution_class": resolution_class,
        "interpretation_status": interpretation_status,
        "resolver_count": len(normalized),
        "status_counts": dict(sorted(counts.items())),
        "matched_sources": matched_sources,
        "identifier_unmatched_sources": identifier_unmatched_sources,
        "title_only_unmatched_sources": title_only_unmatched_sources,
        "resolver_outcomes": normalized,
        "quality_gates": [
            "A matched record still requires work-identity, version, and claim-support review before citation use.",
            "Identifier-not-found means the declared identifier failed in at least one supplied resolver; it is not proof that no work exists.",
            "Title-only misses, outages, and policy skips remain unresolved because source coverage cannot establish nonexistence.",
        ],
    }


def _finite_unit(value: Any, location: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{location} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not 0 <= result <= 1:
        raise ValueError(f"{location} must be finite and between 0 and 1")
    return result


def _passes(value: float, comparison: str, threshold: float) -> bool:
    return {
        ">=": value >= threshold,
        ">": value > threshold,
        "<=": value <= threshold,
        "<": value < threshold,
    }[comparison]


def evaluate_classification_gold_set(
    cases: list[dict[str, Any]],
    labels: list[str],
    thresholds: list[dict[str, Any]],
    gold_provenance: dict[str, Any],
    baseline_metrics: list[dict[str, Any]] | None = None,
    regression_limit: float = 0.05,
) -> dict[str, Any]:
    """Evaluate a closed-label gold set with provenance, support, and regression gates."""
    if not isinstance(labels, list) or not 2 <= len(labels) <= 64:
        raise ValueError("labels must contain 2 to 64 values")
    if any(not isinstance(label, str) or label != label.strip() or not 1 <= len(label) <= 128 for label in labels):
        raise ValueError("labels must be normalized meaningful strings")
    if len(set(labels)) != len(labels):
        raise ValueError("labels must be unique")
    label_set = set(labels)
    if not isinstance(cases, list) or not 1 <= len(cases) <= 100000:
        raise ValueError("cases must contain 1 to 100000 records")
    if not isinstance(gold_provenance, dict) or set(gold_provenance) != {
        "gold_set_id", "gold_set_version", "annotation_source", "adjudication_method",
        "independent_from_system", "leakage_reviewed",
    }:
        raise ValueError("gold_provenance has an invalid field set")
    for field in ("gold_set_id", "gold_set_version", "annotation_source", "adjudication_method"):
        value = gold_provenance[field]
        if not isinstance(value, str) or value != value.strip() or not 1 <= len(value) <= 500:
            raise ValueError(f"gold_provenance.{field} must be normalized meaningful text")
    if not isinstance(gold_provenance["independent_from_system"], bool) or not isinstance(gold_provenance["leakage_reviewed"], bool):
        raise ValueError("gold provenance independence and leakage fields must be boolean")
    regression_limit = _finite_unit(regression_limit, "regression_limit")

    seen_ids = set()
    normalized_cases = []
    expert_count = expert_agreements = 0
    confusion: Counter[tuple[str, str]] = Counter()
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict) or not {"id", "expected_label", "observed_label"} <= set(case) <= {
            "id", "expected_label", "observed_label", "expert_label"
        }:
            raise ValueError(f"case {index} has an invalid field set")
        identifier = case["id"]
        expected = case["expected_label"]
        observed = case["observed_label"]
        expert = case.get("expert_label")
        if not isinstance(identifier, str) or identifier != identifier.strip() or not 1 <= len(identifier) <= 128 or identifier in seen_ids:
            raise ValueError("case IDs must be normalized and unique")
        if expected not in label_set or observed not in label_set or (expert is not None and expert not in label_set):
            raise ValueError(f"case {identifier} contains an undeclared label")
        seen_ids.add(identifier)
        confusion[(expected, observed)] += 1
        if expert is not None:
            expert_count += 1
            expert_agreements += int(expert == expected)
        normalized_cases.append({"id": identifier, "expected_label": expected, "observed_label": observed, "expert_label": expert})

    sample_n = len(normalized_cases)
    correct = sum(confusion[(label, label)] for label in labels)
    class_metrics = []
    for label in labels:
        tp = confusion[(label, label)]
        gold_support = sum(confusion[(label, observed)] for observed in labels)
        predicted_count = sum(confusion[(expected, label)] for expected in labels)
        fp = predicted_count - tp
        fn = gold_support - tp
        tn = sample_n - tp - fp - fn
        precision = tp / predicted_count if predicted_count else 0.0
        recall = tp / gold_support if gold_support else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        class_metrics.append(
            {
                "class_name": label,
                "gold_support": gold_support,
                "predicted_count": predicted_count,
                "true_positive": tp,
                "false_positive": fp,
                "false_negative": fn,
                "true_negative": tn,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "one_vs_rest_accuracy": (tp + tn) / sample_n,
            }
        )
    aggregate_metrics = {
        "accuracy": correct / sample_n,
        "balanced_accuracy": sum(item["recall"] for item in class_metrics) / len(labels),
        "macro_precision": sum(item["precision"] for item in class_metrics) / len(labels),
        "macro_recall": sum(item["recall"] for item in class_metrics) / len(labels),
        "macro_f1": sum(item["f1"] for item in class_metrics) / len(labels),
    }
    class_index = {item["class_name"]: item for item in class_metrics}

    if not isinstance(thresholds, list) or not thresholds:
        raise ValueError("thresholds must be a nonempty list")
    threshold_results = []
    threshold_keys = set()
    failed_gates = []
    for index, threshold in enumerate(thresholds, start=1):
        required = {"scope", "class_name", "metric", "comparison", "threshold_value", "minimum_support"}
        if not isinstance(threshold, dict) or set(threshold) != required:
            raise ValueError(f"threshold {index} has an invalid field set")
        scope = threshold["scope"]
        class_name = threshold["class_name"]
        metric = threshold["metric"]
        comparison = threshold["comparison"]
        value_threshold = _finite_unit(threshold["threshold_value"], f"threshold {index} value")
        minimum_support = threshold["minimum_support"]
        if comparison not in _COMPARISONS or not isinstance(minimum_support, int) or isinstance(minimum_support, bool) or minimum_support < 1:
            raise ValueError(f"threshold {index} comparison or support is invalid")
        if scope == "aggregate":
            if class_name != "aggregate" or metric not in _AGGREGATE_METRICS:
                raise ValueError(f"threshold {index} aggregate metric is invalid")
            observed_value = aggregate_metrics[metric]
            support = sample_n
        elif scope == "per_class":
            if class_name not in label_set or metric not in _CLASS_METRICS:
                raise ValueError(f"threshold {index} class metric is invalid")
            observed_value = class_index[class_name][metric]
            if metric == "precision":
                support = class_index[class_name]["predicted_count"]
            elif metric == "recall":
                support = class_index[class_name]["gold_support"]
            elif metric == "f1":
                support = min(class_index[class_name]["gold_support"], class_index[class_name]["predicted_count"])
            else:
                support = sample_n
        else:
            raise ValueError(f"threshold {index} scope is invalid")
        key = f"{scope}:{class_name}:{metric}"
        if key in threshold_keys:
            raise ValueError("threshold keys must be unique")
        threshold_keys.add(key)
        if support < minimum_support:
            status = "insufficient_support"
            passed = False
        else:
            passed = _passes(observed_value, comparison, value_threshold)
            status = "passed" if passed else "failed"
        if not passed:
            failed_gates.append(key)
        threshold_results.append(
            {
                "key": key,
                "scope": scope,
                "class_name": class_name,
                "metric": metric,
                "observed_value": observed_value,
                "comparison": comparison,
                "threshold_value": value_threshold,
                "support": support,
                "minimum_support": minimum_support,
                "status": status,
                "passed": passed,
            }
        )

    current_metric_map: dict[tuple[str, str, str], float] = {
        ("aggregate", "aggregate", metric): value for metric, value in aggregate_metrics.items()
    }
    for item in class_metrics:
        for metric in _CLASS_METRICS:
            current_metric_map[("per_class", item["class_name"], metric)] = item[metric]
    baseline_rows = [] if baseline_metrics is None else baseline_metrics
    if not isinstance(baseline_rows, list) or len(baseline_rows) > 10000:
        raise ValueError("baseline_metrics must be a list with at most 10000 records")
    baseline_map = {}
    for index, row in enumerate(baseline_rows, start=1):
        if not isinstance(row, dict) or set(row) != {"scope", "class_name", "metric", "value", "direction"}:
            raise ValueError(f"baseline metric {index} has an invalid field set")
        key = (row["scope"], row["class_name"], row["metric"])
        if key in baseline_map or row["direction"] not in {"higher_is_better", "lower_is_better"}:
            raise ValueError("baseline metric keys must be unique and directions valid")
        baseline_map[key] = {"value": _finite_unit(row["value"], f"baseline metric {index} value"), "direction": row["direction"]}

    comparisons = []
    regressions = []
    for key in sorted(set(baseline_map) | set(current_metric_map)):
        scope, class_name, metric = key
        if key not in baseline_map:
            comparisons.append({"scope": scope, "class_name": class_name, "metric": metric, "baseline": None, "current": current_metric_map[key], "signed_lift": None, "change_type": "new_metric", "regression": False})
            continue
        baseline = baseline_map[key]["value"]
        direction = baseline_map[key]["direction"]
        if key not in current_metric_map:
            row = {"scope": scope, "class_name": class_name, "metric": metric, "baseline": baseline, "current": None, "signed_lift": None, "change_type": "dropped_metric", "regression": True}
        else:
            current = current_metric_map[key]
            if direction != "higher_is_better":
                raise ValueError("classification metrics require higher_is_better baselines")
            if baseline == 0:
                signed_lift = None
                change_type = "unchanged_zero" if current == 0 else "improved_from_zero"
                regression = False
            else:
                signed_lift = (current - baseline) / abs(baseline)
                regression = signed_lift < -regression_limit - 1e-12
                change_type = "regression" if regression else ("improvement" if signed_lift > 0 else "within_tolerance")
            row = {"scope": scope, "class_name": class_name, "metric": metric, "baseline": baseline, "current": current, "signed_lift": signed_lift, "change_type": change_type, "regression": regression}
        comparisons.append(row)
        if row["regression"]:
            regressions.append(f"{scope}:{class_name}:{metric}")

    provenance_gates = []
    if not gold_provenance["independent_from_system"]:
        provenance_gates.append("gold_not_independent")
    if not gold_provenance["leakage_reviewed"]:
        provenance_gates.append("leakage_not_reviewed")
    structural_gates = [f"empty_gold_class:{item['class_name']}" for item in class_metrics if item["gold_support"] == 0]
    blocked_reasons = failed_gates + regressions + provenance_gates + structural_gates
    basis = {"cases": normalized_cases, "labels": labels, "gold_provenance": gold_provenance}
    dataset_digest = hashlib.sha256(json.dumps(basis, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "gold_set_id": gold_provenance["gold_set_id"],
        "gold_set_version": gold_provenance["gold_set_version"],
        "dataset_digest": dataset_digest,
        "sample_count": sample_n,
        "labels": list(labels),
        "confusion_matrix": [
            {"expected_label": expected, "observed_label": observed, "count": confusion[(expected, observed)]}
            for expected in labels
            for observed in labels
        ],
        "aggregate_metrics": aggregate_metrics,
        "class_metrics": class_metrics,
        "threshold_results": threshold_results,
        "failed_gate_ids": failed_gates,
        "baseline_comparisons": comparisons,
        "regression_ids": regressions,
        "provenance_gate_ids": provenance_gates,
        "structural_gate_ids": structural_gates,
        "expert_concordance": {"labeled_count": expert_count, "agreement_count": expert_agreements, "agreement_rate": expert_agreements / expert_count if expert_count else None, "gates": False},
        "regression_limit": regression_limit,
        "overall_status": "blocked" if blocked_reasons else "passed",
        "quality_gates": [
            "Gold annotations must be independent from the evaluated system and reviewed for train, prompt, fixture, and benchmark leakage.",
            "Per-class gates use explicit precision or recall terminology and require declared minimum support; empty classes never silently pass.",
            "Expert concordance is advisory unless separately declared as adjudicated gold, and metric improvements from a zero baseline are not regressions.",
            "A passing benchmark supports only the declared task, population, label policy, version, and sampled cases; it is not general scientific validity.",
        ],
    }
