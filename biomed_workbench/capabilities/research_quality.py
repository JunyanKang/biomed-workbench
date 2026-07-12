"""Cross-domain research quality, safety, and reporting assessments."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any


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
