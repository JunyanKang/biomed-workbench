"""Research-grade clinical summaries with explicit non-clinical-use boundaries."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any


_DIRECT_IDENTIFIERS = {
    "address", "date_of_birth", "dob", "email", "full_name", "medical_record_number",
    "mrn", "patient_id", "patient_name", "phone", "social_security_number", "ssn",
}
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(r"(?<!\w)(?:\+?\d{1,3}[ .-]?)?(?:\(?\d{3}\)?[ .-]?)\d{3}[ .-]\d{4}(?!\w)")
_STANDARDS = {
    "CARE": {
        "title": ("title",), "abstract": ("abstract",), "introduction": ("introduction",),
        "patient information": ("patient information", "case presentation"), "clinical findings": ("clinical findings", "physical examination"),
        "timeline": ("timeline",), "diagnostic assessment": ("diagnostic assessment", "diagnosis"),
        "therapeutic intervention": ("therapeutic intervention", "treatment"), "follow-up": ("follow-up", "outcome"),
        "discussion": ("discussion",), "patient perspective": ("patient perspective",), "informed consent": ("informed consent", "consent"),
    },
    "CONSORT": {
        "title": ("title",), "abstract": ("abstract",), "background": ("background", "introduction"),
        "trial design": ("trial design",), "participants": ("participants",), "interventions": ("interventions",),
        "outcomes": ("outcomes",), "sample size": ("sample size",), "randomisation": ("randomisation", "randomization"),
        "blinding": ("blinding", "masking"), "statistical methods": ("statistical methods",), "participant flow": ("participant flow",),
        "harms": ("harms", "adverse events"), "registration": ("registration", "trial registration"),
    },
    "ICH-E3": {
        "title page": ("title page", "study title"), "synopsis": ("synopsis",), "ethics": ("ethics",),
        "investigators": ("investigators",), "objectives": ("objectives",), "investigational plan": ("investigational plan",),
        "study patients": ("study patients", "participants"), "efficacy evaluation": ("efficacy evaluation",),
        "safety evaluation": ("safety evaluation",), "statistical methods": ("statistical methods",),
        "conclusions": ("conclusions",), "tables": ("tables",), "references": ("references",),
    },
}


def deidentify_record(record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ValueError("record must be an object")
    count = 0

    def clean(value: Any, key: str | None = None) -> Any:
        nonlocal count
        normalized_key = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_") if key else None
        if normalized_key in _DIRECT_IDENTIFIERS:
            count += 1
            return "[REDACTED]"
        if isinstance(value, dict):
            return {str(child_key): clean(child_value, str(child_key)) for child_key, child_value in value.items()}
        if isinstance(value, list):
            return [clean(item) for item in value]
        if isinstance(value, str):
            redacted, email_count = _EMAIL.subn("[REDACTED_EMAIL]", value)
            redacted, phone_count = _PHONE.subn("[REDACTED_PHONE]", redacted)
            count += email_count + phone_count
            return redacted
        return value

    return {
        "record": clean(record),
        "redaction_count": count,
        "limitations": [
            "Rule-based de-identification is not certification of HIPAA, GDPR, or institutional compliance.",
            "Free-text dates, locations, rare events, quasi-identifiers, images, and linkage risk require expert review.",
        ],
    }


def _quantile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = fraction * (len(ordered) - 1)
    lower, upper = math.floor(position), math.ceil(position)
    return ordered[lower] if lower == upper else ordered[lower] + (position - lower) * (ordered[upper] - ordered[lower])


def cohort_summary(records: list[dict[str, Any]], continuous: list[str], categorical: list[str]) -> dict[str, Any]:
    if any(not isinstance(record, dict) for record in records) or set(continuous) & set(categorical):
        raise ValueError("records must be objects and variable roles must not overlap")
    continuous_result = {}
    for variable in continuous:
        raw = [record.get(variable) for record in records]
        values = [float(value) for value in raw if value is not None and value != ""]
        if any(not math.isfinite(value) for value in values):
            raise ValueError(f"continuous variable {variable} contains non-finite values")
        continuous_result[variable] = {
            "n": len(values), "missing": len(raw) - len(values),
            "mean": math.fsum(values) / len(values) if values else None,
            "standard_deviation": math.sqrt(math.fsum((value - math.fsum(values) / len(values)) ** 2 for value in values) / (len(values) - 1)) if len(values) > 1 else None,
            "median": _quantile(values, 0.5) if values else None,
            "q1": _quantile(values, 0.25) if values else None,
            "q3": _quantile(values, 0.75) if values else None,
            "minimum": min(values) if values else None, "maximum": max(values) if values else None,
        }
    categorical_result = {}
    for variable in categorical:
        raw = [record.get(variable) for record in records]
        observed = [str(value) for value in raw if value is not None and value != ""]
        counts = Counter(observed)
        categorical_result[variable] = {
            "n": len(observed), "missing": len(raw) - len(observed), "counts": dict(sorted(counts.items())),
            "fractions": {key: value / len(observed) for key, value in sorted(counts.items())} if observed else {},
        }
    return {"record_count": len(records), "continuous": continuous_result, "categorical": categorical_result}


def _average_ranks(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        rank = (index + 1 + end) / 2.0
        for position in range(index, end):
            ranks[ordered[position][0]] = rank
        index = end
    return ranks


def biomarker_performance(labels: list[int], scores: list[float], threshold: float) -> dict[str, Any]:
    if len(labels) != len(scores) or not labels or set(labels) - {0, 1}:
        raise ValueError("labels must be nonempty binary values aligned with scores")
    scores = [float(value) for value in scores]
    if any(not math.isfinite(value) for value in scores) or not math.isfinite(float(threshold)):
        raise ValueError("scores and threshold must be finite")
    predicted = [int(value >= threshold) for value in scores]
    tp = sum(label == prediction == 1 for label, prediction in zip(labels, predicted))
    tn = sum(label == prediction == 0 for label, prediction in zip(labels, predicted))
    fp = sum(label == 0 and prediction == 1 for label, prediction in zip(labels, predicted))
    fn = sum(label == 1 and prediction == 0 for label, prediction in zip(labels, predicted))
    positives, negatives = sum(labels), len(labels) - sum(labels)
    if positives == 0 or negatives == 0:
        auc = None
    else:
        ranks = _average_ranks(scores)
        positive_rank_sum = math.fsum(rank for rank, label in zip(ranks, labels) if label == 1)
        auc = (positive_rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)
    ratio = lambda numerator, denominator: numerator / denominator if denominator else None
    return {
        "threshold": threshold,
        "confusion": {"true_positive": tp, "false_positive": fp, "true_negative": tn, "false_negative": fn},
        "sensitivity": ratio(tp, tp + fn), "specificity": ratio(tn, tn + fp),
        "positive_predictive_value": ratio(tp, tp + fp), "negative_predictive_value": ratio(tn, tn + fn),
        "accuracy": ratio(tp + tn, len(labels)), "roc_auc": auc,
        "limitations": ["Threshold metrics and AUC require external validation, uncertainty estimates, calibration, and clinically representative prevalence."],
    }


def kaplan_meier(durations: list[float], events: list[int]) -> dict[str, Any]:
    if len(durations) != len(events) or not durations or set(events) - {0, 1}:
        raise ValueError("durations and binary event indicators must align")
    pairs = [(float(duration), event) for duration, event in zip(durations, events)]
    if any(not math.isfinite(duration) or duration < 0 for duration, _event in pairs):
        raise ValueError("durations must be finite and non-negative")
    grouped: dict[float, Counter[int]] = defaultdict(Counter)
    for duration, event in pairs:
        grouped[duration][event] += 1
    at_risk = len(pairs)
    survival = 1.0
    greenwood = 0.0
    curve = []
    median = None
    for time in sorted(grouped):
        event_count = grouped[time][1]
        censored = grouped[time][0]
        if event_count:
            survival *= 1.0 - event_count / at_risk
            if at_risk > event_count:
                greenwood += event_count / (at_risk * (at_risk - event_count))
        standard_error = survival * math.sqrt(greenwood)
        curve.append({"time": time, "at_risk": at_risk, "events": event_count, "censored": censored, "survival": survival, "standard_error": standard_error})
        if median is None and survival <= 0.5:
            median = time
        at_risk -= event_count + censored
    return {"n": len(pairs), "events": sum(events), "curve": curve, "median_survival": median, "method": "Kaplan-Meier product-limit estimate with Greenwood standard error"}


def audit_report(text: str, standard: str = "CARE") -> dict[str, Any]:
    if standard not in _STANDARDS or not text.strip():
        raise ValueError(f"standard must be one of {', '.join(sorted(_STANDARDS))} and text must be nonempty")
    normalized = re.sub(r"\s+", " ", text.lower())
    present, missing = [], []
    for section, markers in _STANDARDS[standard].items():
        (present if any(marker in normalized for marker in markers) else missing).append(section)
    return {
        "standard": standard, "present_sections": present, "missing_sections": missing,
        "completeness_fraction": len(present) / len(_STANDARDS[standard]),
        "limitations": ["This lexical structure audit is not a substitute for scientific, ethical, statistical, regulatory, or editorial review."],
    }
