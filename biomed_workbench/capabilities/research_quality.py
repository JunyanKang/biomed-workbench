"""Cross-domain research quality, safety, and reporting assessments."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlparse


_FRESHNESS_RECORD_FIELDS = {
    "id",
    "snapshot_date",
    "upstream_source",
    "upstream_version",
    "review_interval_days",
    "intended_use",
    "currentness_required",
}


def audit_source_freshness(
    records: list[dict[str, Any]],
    as_of_date: str,
    due_policy: str = "block_use_when_due",
) -> dict[str, Any]:
    """Audit deterministic review dates without pretending to assess upstream drift."""
    try:
        as_of = date.fromisoformat(as_of_date)
    except (TypeError, ValueError):
        raise ValueError("as_of_date must be an ISO 8601 calendar date") from None
    if due_policy not in {"block_use_when_due", "warn_when_due"}:
        raise ValueError("due_policy must be block_use_when_due or warn_when_due")
    if not isinstance(records, list) or not 1 <= len(records) <= 10000:
        raise ValueError("records must be a nonempty list with at most 10000 items")

    audited = []
    seen_ids = set()
    status_counts: Counter[str] = Counter()
    blocked_ids = []
    review_due_ids = []
    currentness_verification_ids = []
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict) or set(record) != _FRESHNESS_RECORD_FIELDS:
            raise ValueError(f"record {index} must contain exactly the supported freshness fields")
        identifier = record["id"]
        source = record["upstream_source"]
        upstream_version = record["upstream_version"]
        intended_use = record["intended_use"]
        interval = record["review_interval_days"]
        currentness_required = record["currentness_required"]
        if not isinstance(identifier, str) or identifier != identifier.strip() or not 1 <= len(identifier) <= 128:
            raise ValueError("record IDs must be nonempty and unique")
        if identifier in seen_ids:
            raise ValueError("record IDs must be nonempty and unique")
        seen_ids.add(identifier)
        parsed_source = urlparse(source) if isinstance(source, str) else None
        if (
            parsed_source is None
            or source.strip() != source
            or not 9 <= len(source) <= 2048
            or parsed_source.scheme != "https"
            or not parsed_source.netloc
            or parsed_source.username
            or parsed_source.password
            or parsed_source.query
            or parsed_source.fragment
        ):
            raise ValueError(f"record {identifier} upstream_source must be an absolute credential-free HTTPS URL")
        if not isinstance(upstream_version, str) or upstream_version != upstream_version.strip() or not 1 <= len(upstream_version) <= 256:
            raise ValueError(f"record {identifier} upstream_version must be meaningful text")
        if not isinstance(intended_use, str) or intended_use != intended_use.strip() or not 1 <= len(intended_use) <= 1000:
            raise ValueError(f"record {identifier} intended_use must be meaningful text")
        if not isinstance(interval, int) or isinstance(interval, bool) or not 1 <= interval <= 3650:
            raise ValueError(f"record {identifier} review_interval_days must be an integer from 1 to 3650")
        if not isinstance(currentness_required, bool):
            raise ValueError(f"record {identifier} currentness_required must be boolean")
        try:
            snapshot = date.fromisoformat(record["snapshot_date"])
        except (TypeError, ValueError):
            raise ValueError(f"record {identifier} snapshot_date must be an ISO 8601 calendar date") from None

        review_due_date = snapshot + timedelta(days=interval)
        age_days = (as_of - snapshot).days
        if snapshot > as_of:
            temporal_status = "future_dated"
            action = "reject_future_dated_snapshot"
            use_allowed = False
        elif as_of >= review_due_date:
            temporal_status = "review_due"
            review_due_ids.append(identifier)
            use_allowed = due_policy == "warn_when_due"
            action = "reverify_upstream_before_use" if not use_allowed else "reverify_upstream_and_report_limitation"
        else:
            temporal_status = "within_review_window"
            use_allowed = True
            action = "verify_upstream_before_currentness_claim" if currentness_required else "temporal_review_pass"
        if currentness_required:
            currentness_verification_ids.append(identifier)
        if not use_allowed:
            blocked_ids.append(identifier)
        status_counts[temporal_status] += 1
        audited.append(
            {
                "id": identifier,
                "snapshot_date": snapshot.isoformat(),
                "as_of_date": as_of.isoformat(),
                "age_days": age_days,
                "review_interval_days": interval,
                "review_due_date": review_due_date.isoformat(),
                "temporal_status": temporal_status,
                "upstream_source": source,
                "upstream_version": upstream_version,
                "intended_use": intended_use,
                "currentness_required": currentness_required,
                "upstream_drift_assessed": False,
                "currentness_claim_allowed": False,
                "use_allowed": use_allowed,
                "action": action,
            }
        )

    if any(item["temporal_status"] == "future_dated" for item in audited):
        overall_status = "invalid"
    elif blocked_ids:
        overall_status = "blocked"
    elif review_due_ids:
        overall_status = "review_required"
    elif currentness_verification_ids:
        overall_status = "pass_with_currentness_limit"
    else:
        overall_status = "pass"
    return {
        "as_of_date": as_of.isoformat(),
        "due_policy": due_policy,
        "record_count": len(audited),
        "status_counts": dict(sorted(status_counts.items())),
        "blocked_record_ids": blocked_ids,
        "review_due_record_ids": review_due_ids,
        "currentness_verification_record_ids": currentness_verification_ids,
        "overall_status": overall_status,
        "upstream_drift_assessed": False,
        "records": audited,
        "quality_gates": [
            "A review-window pass measures snapshot age only; it does not prove that the upstream source is unchanged or current.",
            "Any currentness-sensitive claim requires a separate, recorded upstream verification at the time of use.",
            "Future-dated snapshots are invalid, and review-due records follow the explicit due policy without silent fallback.",
        ],
    }


def calculate_tumor_mutation_burden(
    variants: list[dict[str, Any]],
    callable_megabases: float,
    minimum_allele_fraction: float = 0.05,
    include_effects: list[str] | None = None,
) -> dict[str, Any]:
    """Calculate descriptive TMB with an explicit, auditable rule cascade."""
    denominator = float(callable_megabases)
    minimum_af = float(minimum_allele_fraction)
    if not math.isfinite(denominator) or denominator <= 0 or not 0 <= minimum_af <= 1:
        raise ValueError("callable_megabases must be positive and minimum_allele_fraction must be 0..1")
    effects = {
        value.strip().lower()
        for value in (include_effects or ["missense", "nonsense", "frameshift", "splice", "inframe_indel", "start_lost", "stop_lost"])
        if value.strip()
    }
    if not effects:
        raise ValueError("include_effects must not be empty")
    eligible, excluded = [], []
    exclusion_counts: Counter[str] = Counter()
    seen_ids = set()
    for index, variant in enumerate(variants, start=1):
        if not isinstance(variant, dict):
            raise ValueError("variants must be objects")
        identifier = str(variant.get("id", f"variant-{index}")).strip()
        effect = str(variant.get("effect", "")).strip().lower()
        filter_value = str(variant.get("filter", "PASS")).strip()
        somatic = variant.get("somatic", True)
        allele_fraction = float(variant.get("allele_fraction", 0.0))
        if not identifier or identifier in seen_ids or not isinstance(somatic, bool) or not math.isfinite(allele_fraction) or not 0 <= allele_fraction <= 1:
            raise ValueError("variant IDs must be unique and somatic/allele_fraction fields valid")
        seen_ids.add(identifier)
        reason = None
        if filter_value not in {"PASS", "."}:
            reason = "filter"
        elif not somatic:
            reason = "not_somatic"
        elif effect not in effects:
            reason = "effect"
        elif allele_fraction < minimum_af:
            reason = "allele_fraction"
        if reason:
            exclusion_counts[reason] += 1
            excluded.append({"id": identifier, "reason": reason})
        else:
            eligible.append(identifier)
    return {
        "input_variant_count": len(variants),
        "eligible_variant_count": len(eligible),
        "eligible_variant_ids": eligible,
        "excluded_variants": excluded,
        "exclusion_counts": dict(sorted(exclusion_counts.items())),
        "callable_megabases": denominator,
        "minimum_allele_fraction": minimum_af,
        "included_effects": sorted(effects),
        "tmb_mutations_per_mb": len(eligible) / denominator,
        "method": "eligible somatic variants divided by declared callable megabases",
        "quality_gates": [
            "Use an assay- and indication-specific validated definition of variant classes and callable territory.",
            "Document genome build, germline filtering, sequencing depth, purity, and limit of detection.",
            "This descriptive value is not a clinical high/low classification or treatment recommendation.",
        ],
    }


def summarize_adverse_events(events: list[dict[str, Any]], enrolled_participants: int) -> dict[str, Any]:
    """Summarize events and affected participants without conflating denominators."""
    if not isinstance(enrolled_participants, int) or isinstance(enrolled_participants, bool) or enrolled_participants <= 0:
        raise ValueError("enrolled_participants must be a positive integer")
    terms: dict[str, dict[str, Any]] = defaultdict(lambda: {"event_count": 0, "participants": set(), "maximum_grade": 0, "serious_event_count": 0})
    participants = set()
    serious_participants = set()
    grades: Counter[int] = Counter()
    relatedness: Counter[str] = Counter()
    normalized_events = []
    for index, event in enumerate(events, start=1):
        if not isinstance(event, dict):
            raise ValueError("events must be objects")
        participant = str(event.get("participant", "")).strip()
        term = str(event.get("term", "")).strip()
        grade = event.get("grade")
        serious = event.get("serious")
        relation = str(event.get("relatedness", "unknown")).strip().lower()
        if not participant or not term or not isinstance(grade, int) or isinstance(grade, bool) or not 1 <= grade <= 5 or not isinstance(serious, bool):
            raise ValueError("each event requires participant, term, grade 1..5, and boolean serious")
        participants.add(participant)
        if serious:
            serious_participants.add(participant)
        grades[grade] += 1
        relatedness[relation] += 1
        row = terms[term]
        row["event_count"] += 1
        row["participants"].add(participant)
        row["maximum_grade"] = max(row["maximum_grade"], grade)
        row["serious_event_count"] += int(serious)
        normalized_events.append({"index": index, "participant": participant, "term": term, "grade": grade, "serious": serious, "relatedness": relation})
    if len(participants) > enrolled_participants:
        raise ValueError("participants with events cannot exceed enrolled participants")
    by_term = {}
    for term, row in sorted(terms.items()):
        participant_count = len(row.pop("participants"))
        by_term[term] = {
            **row,
            "participant_count": participant_count,
            "participant_incidence_percent": 100.0 * participant_count / enrolled_participants,
        }
    return {
        "enrolled_participants": enrolled_participants,
        "event_count": len(events),
        "participants_with_events": len(participants),
        "participant_incidence_percent": 100.0 * len(participants) / enrolled_participants,
        "serious_event_count": sum(event["serious"] for event in normalized_events),
        "participants_with_serious_events": len(serious_participants),
        "by_grade": {str(key): value for key, value in sorted(grades.items())},
        "by_relatedness": dict(sorted(relatedness.items())),
        "by_term": by_term,
        "events": normalized_events,
        "quality_gates": [
            "Event counts and participant incidence answer different questions and must remain separate.",
            "Seriousness, severity grade, expectedness, and relatedness are distinct attributes.",
            "This summary does not determine causality, regulatory reportability, or clinical management.",
        ],
    }


def assess_manuscript(
    claims: list[dict[str, Any]],
    review_domains: dict[str, bool],
    novelty: str,
) -> dict[str, Any]:
    """Create a claim-linked, domain-structured manuscript assessment."""
    required_domains = {"methods_reproducible", "statistics_adequate", "data_available", "ethics_resolved"}
    if novelty not in {"low", "moderate", "high"} or set(review_domains) != required_domains:
        raise ValueError("novelty and all four review domains are required")
    if any(not isinstance(value, bool) for value in review_domains.values()):
        raise ValueError("review domain values must be boolean")
    findings = []
    claim_rows = []
    seen_ids = set()
    causal_pattern = re.compile(r"\b(caus(?:e|es|ed|al|ally)|drives?|determines?|mechanis(?:m|tic))\b", re.IGNORECASE)
    causal_designs = {"randomized", "interventional", "genetic_perturbation", "causal_inference"}
    for index, claim in enumerate(claims, start=1):
        if not isinstance(claim, dict):
            raise ValueError("claims must be objects")
        identifier = str(claim.get("id", f"claim-{index}")).strip()
        text = str(claim.get("claim", "")).strip()
        design = str(claim.get("evidence_design", "unspecified")).strip().lower()
        replicated = claim.get("replicated")
        if not identifier or identifier in seen_ids or not text or not isinstance(replicated, bool):
            raise ValueError("claims require unique IDs, text, evidence design, and replication status")
        seen_ids.add(identifier)
        codes = []
        if causal_pattern.search(text) and design not in causal_designs:
            codes.append("CAUSALITY_OVERCLAIM")
            findings.append({"severity": "major", "code": "CAUSALITY_OVERCLAIM", "location": identifier, "message": "Causal language exceeds the declared evidence design."})
        if design == "unspecified":
            codes.append("EVIDENCE_DESIGN_UNSPECIFIED")
            findings.append({"severity": "major", "code": "EVIDENCE_DESIGN_UNSPECIFIED", "location": identifier, "message": "The evidence design is not declared."})
        if not replicated:
            codes.append("CLAIM_NOT_REPLICATED")
            findings.append({"severity": "minor", "code": "CLAIM_NOT_REPLICATED", "location": identifier, "message": "Independent or orthogonal replication is not declared."})
        claim_rows.append({"claim_id": identifier, "claim": text, "evidence_design": design, "replicated": replicated, "finding_codes": codes})
    domain_findings = {
        "methods_reproducible": ("METHODS_NOT_REPRODUCIBLE", "Methods do not currently support independent reproduction."),
        "statistics_adequate": ("STATISTICS_INADEQUATE", "Statistical design or reporting is inadequate."),
        "data_available": ("DATA_UNAVAILABLE", "Underlying data are not available for evaluation."),
        "ethics_resolved": ("ETHICS_UNRESOLVED", "Ethics, consent, or oversight requirements are unresolved."),
    }
    for domain, passed in review_domains.items():
        if not passed:
            code, message = domain_findings[domain]
            findings.append({"severity": "major", "code": code, "location": domain, "message": message})
    major = sum(finding["severity"] == "major" for finding in findings)
    minor = sum(finding["severity"] == "minor" for finding in findings)
    if not review_domains["ethics_resolved"]:
        recommendation = "not_reviewable"
    elif major:
        recommendation = "major_revision"
    elif minor or novelty == "low":
        recommendation = "minor_revision"
    else:
        recommendation = "accept"
    return {
        "novelty": novelty,
        "review_domains": dict(sorted(review_domains.items())),
        "claim_assessments": claim_rows,
        "findings": findings,
        "finding_counts": {"major": major, "minor": minor},
        "recommendation": recommendation,
        "quality_gates": [
            "Read the full manuscript, figures, supplements, data, and relevant literature before editorial judgment.",
            "Separate fatal validity concerns from addressable reporting or presentation issues.",
            "The recommendation is structured decision support, not an editor decision or substitute for field expertise.",
        ],
    }
