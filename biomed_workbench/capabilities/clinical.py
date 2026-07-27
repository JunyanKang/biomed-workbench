"""Research-grade clinical summaries with explicit non-clinical-use boundaries."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any

from biomed_workbench.services.public_databases import (
    cbioportal_gene_copy_number_evidence as fetch_cbioportal_gene_copy_number_evidence,
    cbioportal_gene_mutation_evidence as fetch_cbioportal_gene_mutation_evidence,
    cbioportal_study_evidence as fetch_cbioportal_study_evidence,
)


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
_CLINICAL_DECISION_BLOCKERS = {
    "diagnosis": (
        "diagnose", "diagnosis", "diagnostic decision", "rule out", "confirmed disease",
        "确诊", "诊断", "排除诊断",
    ),
    "treatment": (
        "treat", "treatment", "therapy", "prescribe", "dose adjustment", "management plan",
        "治疗", "处方", "用药", "剂量调整", "治疗方案",
    ),
    "triage": (
        "urgent", "emergency", "admit", "discharge", "triage", "refer immediately",
        "急诊", "住院", "出院", "分诊", "立即转诊",
    ),
    "prognosis": (
        "survival prediction", "risk of death", "recurrence prediction", "will progress",
        "预后", "死亡风险", "复发风险", "进展风险",
    ),
}
_CLINICAL_SUPPORT_SIGNALS = {
    "research-summary": ("summarize", "cohort", "evidence", "literature", "assay", "研究", "队列", "证据", "文献"),
    "quality-audit": ("audit", "missing", "eligibility", "limitation", "qc", "审计", "缺失", "纳入", "质控"),
}


def cbioportal_study_record(study_id: str) -> dict[str, Any]:
    """Retrieve one exact public cancer-genomics study record from cBioPortal."""
    return fetch_cbioportal_study_evidence(study_id)


def cbioportal_gene_mutations(
    study_id: str, gene_symbol: str, max_records: int = 100,
    molecular_profile_id: str | None = None, sample_list_id: str | None = None,
) -> dict[str, Any]:
    """Retrieve bounded source-preserved cancer mutations for one gene and one study."""
    return fetch_cbioportal_gene_mutation_evidence(study_id, gene_symbol, max_records, molecular_profile_id, sample_list_id)


def cbioportal_gene_copy_number(study_id: str, gene_symbol: str, max_records: int = 100, event_type: str = "HOMDEL_AND_AMP") -> dict[str, Any]:
    """Retrieve bounded discrete copy-number events for one study gene."""
    return fetch_cbioportal_gene_copy_number_evidence(study_id, gene_symbol, max_records, event_type)


def copy_number_event_summary(records: list[dict[str, Any]], sample_count: int) -> dict[str, Any]:
    """Audit discrete copy-number event records before downstream cancer inference."""
    if not isinstance(records, list) or not isinstance(sample_count, int) or sample_count < 1:
        raise ValueError("records must be a list and sample_count must be a positive integer")
    labels = {-2: "homozygous_deletion", -1: "hemizygous_deletion", 0: "diploid", 1: "gain", 2: "amplification"}
    seen, counts = set(), Counter()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("each copy-number record must be an object")
        sample_id = record.get("sample_id")
        alteration = record.get("alteration")
        if not isinstance(sample_id, str) or not sample_id.strip() or sample_id in seen or alteration not in labels:
            raise ValueError("records require unique nonempty sample_id values and discrete alterations in -2..2")
        seen.add(sample_id)
        counts[alteration] += 1
    observed = len(records)
    if observed > sample_count:
        raise ValueError("observed event records cannot exceed the declared sample_count")
    labeled_counts = {labels[code]: counts[code] for code in sorted(labels)}
    non_diploid = observed - counts[0]
    return {
        "declared_sample_count": sample_count,
        "observed_record_count": observed,
        "missing_record_count": sample_count - observed,
        "observed_sample_fraction": observed / sample_count,
        "event_counts": labeled_counts,
        "event_fractions_of_declared_cohort": {labels[code]: counts[code] / sample_count for code in sorted(labels)},
        "non_diploid_record_count": non_diploid,
        "quality_status": "eligible_for_descriptive_cna_summary" if observed == sample_count else "incomplete_cohort_coverage",
        "limitations": [
            "This audit summarizes declared discrete event records only; it does not infer tumor purity, ploidy, focality, allele-specific copy number, clonality, absolute copy number, driver status, treatment response, or causality.",
            "Incomplete coverage blocks cohort-wide prevalence claims until missing samples and assay eligibility are reconciled.",
        ],
    }


def cbioportal_copy_number_audit_input(evidence: dict[str, Any]) -> dict[str, Any]:
    """Adapt a complete cBioPortal CNA retrieval into the deterministic audit contract."""
    if not isinstance(evidence, dict) or evidence.get("found") is not True:
        raise ValueError("evidence must be a resolved cBioPortal copy-number result")
    if evidence.get("truncated") is not False:
        raise ValueError("truncated cBioPortal records cannot support a cohort coverage audit")
    sample_list = evidence.get("sample_list")
    records = evidence.get("records")
    if not isinstance(sample_list, dict) or not isinstance(sample_list.get("sample_count"), int) or sample_list["sample_count"] < 1:
        raise ValueError("cBioPortal evidence requires a positive structured sample_list.sample_count")
    if not isinstance(records, list):
        raise ValueError("cBioPortal evidence requires a records list")
    return {
        "records": [{"sample_id": row.get("sample_id"), "alteration": row.get("alteration")} for row in records if isinstance(row, dict)],
        "sample_count": sample_list["sample_count"],
        "provenance": {"adapter": "cbioportal_copy_number_audit_input", "study_id": evidence.get("study_id"), "gene_symbol": evidence.get("gene_symbol"), "sample_list_id": sample_list.get("id")},
    }


def cbioportal_copy_number_coverage_audit(evidence: dict[str, Any]) -> dict[str, Any]:
    """Run the verified cBioPortal CNA adaptation and coverage audit as one serial operation."""
    adapted = cbioportal_copy_number_audit_input(evidence)
    summary = copy_number_event_summary(adapted["records"], adapted["sample_count"])
    return {"input_provenance": adapted["provenance"], "summary": summary}


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


def clinical_decision_boundary_audit(
    request_text: str,
    intended_use: str = "research_support",
    has_qualified_clinician_review: bool = False,
    evidence_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Classify whether a clinical request must be blocked before interpretation."""
    if not isinstance(request_text, str) or not request_text.strip():
        raise ValueError("request_text must be nonempty")
    if intended_use not in {"research_support", "clinical_decision_support", "patient_specific_decision"}:
        raise ValueError("intended_use must be research_support, clinical_decision_support, or patient_specific_decision")
    if not isinstance(has_qualified_clinician_review, bool):
        raise ValueError("has_qualified_clinician_review must be boolean")
    evidence = [] if evidence_items is None else evidence_items
    if not isinstance(evidence, list) or any(not isinstance(item, dict) for item in evidence):
        raise ValueError("evidence_items must be a list of objects when supplied")

    normalized = re.sub(r"\s+", " ", request_text.lower())
    blocker_hits = {
        family: sorted({term for term in terms if term.lower() in normalized})
        for family, terms in _CLINICAL_DECISION_BLOCKERS.items()
    }
    blocker_hits = {family: hits for family, hits in blocker_hits.items() if hits}
    support_hits = {
        family: sorted({term for term in terms if term.lower() in normalized})
        for family, terms in _CLINICAL_SUPPORT_SIGNALS.items()
    }
    support_hits = {family: hits for family, hits in support_hits.items() if hits}
    evidence_types = sorted({str(item.get("type", "")).strip() for item in evidence if str(item.get("type", "")).strip()})
    missing_evidence = [
        name
        for name in ("source_records", "cohort_denominator", "uncertainty_or_limitations")
        if name not in evidence_types
    ]

    fatal_reasons = []
    if intended_use == "patient_specific_decision":
        fatal_reasons.append("patient-specific decision use is outside this plugin")
    if blocker_hits and intended_use != "research_support":
        fatal_reasons.append("request contains diagnosis, treatment, triage, or prognosis decision language")
    if blocker_hits and not has_qualified_clinician_review:
        fatal_reasons.append("decision-like language lacks documented qualified clinician review")
    if missing_evidence and intended_use != "research_support":
        fatal_reasons.append("clinical decision support requires source records, cohort denominator, and explicit uncertainty")

    if fatal_reasons:
        risk_level = "blocked"
        allowed_actions = ["deidentify input", "summarize non-patient-specific evidence", "list missing evidence", "draft questions for qualified review"]
    elif blocker_hits:
        risk_level = "major_review_required"
        allowed_actions = ["summarize evidence with no recommendation", "preserve uncertainty", "route to qualified review"]
    elif missing_evidence:
        risk_level = "limited_research_support"
        allowed_actions = ["summarize available research evidence", "report missing evidence", "avoid patient-specific conclusions"]
    else:
        risk_level = "research_support_allowed"
        allowed_actions = ["summarize evidence", "audit limitations", "prepare review-ready research notes"]

    return {
        "intended_use": intended_use,
        "risk_level": risk_level,
        "interpretation_allowed": risk_level in {"limited_research_support", "research_support_allowed"},
        "clinical_recommendation_allowed": False,
        "blocker_hits": blocker_hits,
        "support_hits": support_hits,
        "evidence_types": evidence_types,
        "missing_evidence_types": missing_evidence,
        "fatal_reasons": fatal_reasons,
        "allowed_actions": allowed_actions,
        "limitations": [
            "This boundary audit is a deterministic safety classifier for research-assistant routing; it is not medical advice, diagnosis, triage, treatment selection, or regulatory review.",
            "Any patient-specific, diagnostic, therapeutic, prognostic, or urgent-care request remains blocked unless handled by qualified clinical workflows outside this plugin.",
        ],
    }
