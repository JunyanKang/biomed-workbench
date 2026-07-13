"""Deterministic temporal-integrity checks over explicit research facts."""

from __future__ import annotations

import calendar
import hashlib
import json
import re
from collections import Counter
from datetime import date
from typing import Any


_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_PRECISIONS = {"day", "month", "year", "interval", "unknown"}
_CONFIDENCE = {"high", "medium", "low", "unverified"}
_PROVENANCE_METHODS = {"publisher_metadata", "original_document", "user_verified", "adapter_metadata", "unknown"}
_CATALOG_COMPLETENESS = {"exhaustive", "partial", "unknown"}
_ASSERTION_KINDS = {"future_as_past", "governance", "version_comparison", "causal_order", "narrative"}
_PREDICATES = {
    "already_completed", "forthcoming", "governed_by", "compares_with", "enabled", "caused", "led_to",
    "in_response_to", "superseded", "preceded", "followed_by", "followed", "narrative",
}
_BEFORE_PREDICATES = {"enabled", "caused", "led_to", "preceded", "followed_by"}
_AFTER_PREDICATES = {"in_response_to", "superseded", "followed"}
_DEICTIC_RE = re.compile(
    r"\b(currently|now|at present|most recent|the latest|newest|new|recently|last year|this year|today|"
    r"nowadays|presently|emerging|recent cycle|latest available)\b",
    re.IGNORECASE,
)


def _exact(value: Any, fields: set[str], location: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{location} must contain exactly {sorted(fields)}")
    return value


def _identifier(value: Any, location: str) -> str:
    if not isinstance(value, str) or value != value.strip() or not _ID_RE.fullmatch(value):
        raise ValueError(f"{location} must be a normalized safe identifier")
    return value


def _text(value: Any, location: str, maximum: int = 4000) -> str:
    if not isinstance(value, str) or value != value.strip() or not 1 <= len(value) <= maximum:
        raise ValueError(f"{location} must be normalized meaningful text")
    return value


def _nullable_id(value: Any, location: str) -> str | None:
    return None if value is None else _identifier(value, location)


def _parse_iso_day(value: str, location: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{location} must be a valid ISO calendar date") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{location} must use canonical YYYY-MM-DD form")
    return parsed


def _date_interval(raw: dict[str, Any], location: str, *, allow_open_end: bool = False) -> tuple[date, date] | None:
    fact = _exact(raw, {"value", "precision", "open_ended", "provenance_method", "confidence", "source_record_id"}, location)
    precision = fact["precision"]
    if precision not in _PRECISIONS:
        raise ValueError(f"{location}.precision is unsupported")
    if fact["confidence"] not in _CONFIDENCE or fact["provenance_method"] not in _PROVENANCE_METHODS:
        raise ValueError(f"{location} provenance is unsupported")
    if not isinstance(fact["open_ended"], bool):
        raise ValueError(f"{location}.open_ended must be boolean")
    _nullable_id(fact["source_record_id"], f"{location}.source_record_id")
    if fact["confidence"] in {"high", "medium"} and fact["provenance_method"] == "unknown":
        raise ValueError(f"{location} cannot claim verified confidence with unknown provenance")
    if fact["confidence"] in {"high", "medium"} and fact["source_record_id"] is None:
        raise ValueError(f"{location} requires a source_record_id for verified confidence")
    value = fact["value"]
    if fact["open_ended"]:
        if not allow_open_end or precision != "unknown" or value is not None:
            raise ValueError(f"{location} open-ended form is only valid for an unknown effective-range end")
        return None
    if precision == "unknown":
        if value is not None:
            raise ValueError(f"{location} unknown precision requires value=null")
        return None
    if not isinstance(value, str):
        raise ValueError(f"{location}.value must be a string for known precision")
    if precision == "day":
        point = _parse_iso_day(value, f"{location}.value")
        return point, point
    if precision == "month":
        match = re.fullmatch(r"(\d{4})-(\d{2})", value)
        if not match:
            raise ValueError(f"{location}.value must use YYYY-MM for month precision")
        year, month = int(match.group(1)), int(match.group(2))
        try:
            last = calendar.monthrange(year, month)[1]
        except calendar.IllegalMonthError as exc:
            raise ValueError(f"{location}.value contains an invalid month") from exc
        return date(year, month, 1), date(year, month, last)
    if precision == "year":
        if not re.fullmatch(r"\d{4}", value):
            raise ValueError(f"{location}.value must use YYYY for year precision")
        year = int(value)
        return date(year, 1, 1), date(year, 12, 31)
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})", value)
    if not match:
        raise ValueError(f"{location}.value must use inclusive YYYY-MM-DD..YYYY-MM-DD interval form")
    start = _parse_iso_day(match.group(1), f"{location}.start")
    end = _parse_iso_day(match.group(2), f"{location}.end")
    if start > end:
        raise ValueError(f"{location} interval start must not exceed end")
    return start, end


def _eligible(raw: dict[str, Any], interval: tuple[date, date] | None) -> bool:
    return interval is not None and raw["confidence"] in {"high", "medium"}


def _interval_text(interval: tuple[date, date] | None, *, open_ended: bool = False) -> str | None:
    if open_ended:
        return "+infinity"
    if interval is None:
        return None
    return f"{interval[0].isoformat()}..{interval[1].isoformat()}"


def _issue(code: str, severity: str, subject_ids: list[str], rationale: str, suggested_fix: str | None) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "subject_ids": sorted(set(subject_ids)),
        "rationale": rationale,
        "suggested_fix": suggested_fix,
    }


def audit_temporal_integrity(
    report_reference_date: str,
    terminal_policy: str,
    sources: list[dict[str, Any]],
    events: list[dict[str, Any]],
    assertions: list[dict[str, Any]],
    audit_provenance: dict[str, Any],
) -> dict[str, Any]:
    """Audit explicit temporal assertions without inventing missing ground truth."""
    reference_date = _parse_iso_day(report_reference_date, "report_reference_date")
    if terminal_policy not in {"advisory", "strict"}:
        raise ValueError("terminal_policy must be advisory or strict")
    if not isinstance(sources, list) or len(sources) > 100000:
        raise ValueError("sources must be a list with at most 100000 records")
    if not isinstance(events, list) or len(events) > 100000:
        raise ValueError("events must be a list with at most 100000 records")
    if not isinstance(assertions, list) or not 1 <= len(assertions) <= 100000:
        raise ValueError("assertions must contain 1 to 100000 records")

    source_fields = {
        "id", "published_date", "effective_start", "effective_end", "version_family_id",
        "version_catalog_completeness", "supersedes", "superseded_by",
    }
    source_index: dict[str, dict[str, Any]] = {}
    source_dates: dict[str, dict[str, tuple[date, date] | None]] = {}
    global_issues: list[dict[str, Any]] = []
    for index, raw in enumerate(sources, start=1):
        source = _exact(raw, source_fields, f"source {index}")
        source_id = _identifier(source["id"], f"source {index}.id")
        if source_id in source_index:
            raise ValueError("source IDs must be unique")
        published = _date_interval(source["published_date"], f"source {source_id}.published_date")
        start = _date_interval(source["effective_start"], f"source {source_id}.effective_start")
        end = _date_interval(source["effective_end"], f"source {source_id}.effective_end", allow_open_end=True)
        family = _nullable_id(source["version_family_id"], f"source {source_id}.version_family_id")
        if source["version_catalog_completeness"] not in _CATALOG_COMPLETENESS:
            raise ValueError(f"source {source_id} has unsupported version catalog completeness")
        _nullable_id(source["supersedes"], f"source {source_id}.supersedes")
        _nullable_id(source["superseded_by"], f"source {source_id}.superseded_by")
        if start is not None and end is not None and start[0] > end[1]:
            raise ValueError(f"source {source_id} effective range start exceeds end")
        if source["effective_end"]["open_ended"] and start is None:
            raise ValueError(f"source {source_id} cannot have an open end without a known effective start")
        source_index[source_id] = dict(source)
        source_dates[source_id] = {"published": published, "start": start, "end": end}

    for source_id, source in source_index.items():
        older = source["supersedes"]
        newer = source["superseded_by"]
        for field, target in (("supersedes", older), ("superseded_by", newer)):
            if target is not None and target not in source_index:
                global_issues.append(_issue("TIMELINE_REFERENCE_UNRESOLVED", "major", [source_id, target], f"{field} references an unknown source.", "Add the missing source record or remove the unresolved link."))
        if older in source_index and source_index[older]["superseded_by"] != source_id:
            global_issues.append(_issue("SUPERSESSION_LINK_ASYMMETRIC", "major", [source_id, older], "A supersedes link is not reciprocated by superseded_by.", "Repair both sides of the supersession relationship."))
        if newer in source_index and source_index[newer]["supersedes"] != source_id:
            global_issues.append(_issue("SUPERSESSION_LINK_ASYMMETRIC", "major", [source_id, newer], "A superseded_by link is not reciprocated by supersedes.", "Repair both sides of the supersession relationship."))
    for origin in sorted(source_index):
        seen: set[str] = set()
        cursor: str | None = origin
        while cursor in source_index:
            if cursor in seen:
                global_issues.append(_issue("SUPERSESSION_CYCLE", "major", sorted(seen | {cursor}), "The source supersession graph contains a cycle.", "Replace cyclic version links with a directed chronological chain."))
                break
            seen.add(cursor)
            cursor = source_index[cursor]["supersedes"]

    event_index: dict[str, dict[str, Any]] = {}
    event_dates: dict[str, tuple[date, date] | None] = {}
    for index, raw in enumerate(events, start=1):
        event = _exact(raw, {"id", "description", "date"}, f"event {index}")
        event_id = _identifier(event["id"], f"event {index}.id")
        if event_id in event_index:
            raise ValueError("event IDs must be unique")
        _text(event["description"], f"event {event_id}.description")
        event_dates[event_id] = _date_interval(event["date"], f"event {event_id}.date")
        event_index[event_id] = dict(event)

    assertion_fields = {
        "id", "text", "section_path", "assertion_kind", "predicate", "anchor_date", "event_id", "source_id",
        "comparator_year", "left_binding", "right_binding",
    }
    assertion_results: list[dict[str, Any]] = []
    seen_assertions: set[str] = set()

    def resolve_binding(binding: dict[str, Any], location: str) -> tuple[tuple[date, date] | None, list[str], str | None]:
        item = _exact(binding, {"kind", "id", "date"}, location)
        if item["kind"] not in {"source", "event", "direct"}:
            raise ValueError(f"{location}.kind is unsupported")
        if item["kind"] == "source":
            source_id = _identifier(item["id"], f"{location}.id")
            if item["date"] is not None:
                raise ValueError(f"{location}.date must be null for source binding")
            if source_id not in source_index:
                return None, [source_id], "unknown source binding"
            raw_date = source_index[source_id]["published_date"]
            interval = source_dates[source_id]["published"]
            return interval if _eligible(raw_date, interval) else None, [source_id], None if _eligible(raw_date, interval) else "source publication date is missing or unverified"
        if item["kind"] == "event":
            event_id = _identifier(item["id"], f"{location}.id")
            if item["date"] is not None:
                raise ValueError(f"{location}.date must be null for event binding")
            if event_id not in event_index:
                return None, [event_id], "unknown event binding"
            raw_date = event_index[event_id]["date"]
            interval = event_dates[event_id]
            return interval if _eligible(raw_date, interval) else None, [event_id], None if _eligible(raw_date, interval) else "event date is missing or unverified"
        if item["id"] is not None:
            raise ValueError(f"{location}.id must be null for direct binding")
        if item["date"] is None:
            raise ValueError(f"{location}.date is required for direct binding")
        interval = _date_interval(item["date"], f"{location}.date")
        return interval if _eligible(item["date"], interval) else None, [], None if _eligible(item["date"], interval) else "direct date is missing or unverified"

    for index, raw in enumerate(assertions, start=1):
        assertion = _exact(raw, assertion_fields, f"assertion {index}")
        assertion_id = _identifier(assertion["id"], f"assertion {index}.id")
        if assertion_id in seen_assertions:
            raise ValueError("assertion IDs must be unique")
        seen_assertions.add(assertion_id)
        _text(assertion["text"], f"assertion {assertion_id}.text", 10000)
        _text(assertion["section_path"], f"assertion {assertion_id}.section_path", 1000)
        kind, predicate = assertion["assertion_kind"], assertion["predicate"]
        if kind not in _ASSERTION_KINDS or predicate not in _PREDICATES:
            raise ValueError(f"assertion {assertion_id} kind or predicate is unsupported")
        event_id = _nullable_id(assertion["event_id"], f"assertion {assertion_id}.event_id")
        source_id = _nullable_id(assertion["source_id"], f"assertion {assertion_id}.source_id")
        comparator_year = assertion["comparator_year"]
        if comparator_year is not None and (not isinstance(comparator_year, int) or isinstance(comparator_year, bool) or not 1000 <= comparator_year <= 9999):
            raise ValueError(f"assertion {assertion_id}.comparator_year is invalid")
        issues: list[dict[str, Any]] = []
        bound_ids: list[str] = []
        bound_intervals: dict[str, str | None] = {"left": None, "right": None}

        expected_shape = {
            "future_as_past": (predicate in {"already_completed", "forthcoming"} and assertion["anchor_date"] is not None and event_id is not None and source_id is None and comparator_year is None and assertion["left_binding"] is None and assertion["right_binding"] is None),
            "governance": (predicate == "governed_by" and assertion["anchor_date"] is None and event_id is not None and source_id is not None and comparator_year is None and assertion["left_binding"] is None and assertion["right_binding"] is None),
            "version_comparison": (predicate == "compares_with" and assertion["anchor_date"] is None and event_id is None and source_id is not None and comparator_year is not None and assertion["left_binding"] is None and assertion["right_binding"] is None),
            "causal_order": (predicate in _BEFORE_PREDICATES | _AFTER_PREDICATES and assertion["anchor_date"] is None and event_id is None and source_id is None and comparator_year is None and assertion["left_binding"] is not None and assertion["right_binding"] is not None),
            "narrative": (predicate == "narrative" and assertion["anchor_date"] is None and event_id is None and source_id is None and comparator_year is None and assertion["left_binding"] is None and assertion["right_binding"] is None),
        }
        if not expected_shape[kind]:
            raise ValueError(f"assertion {assertion_id} fields do not match assertion_kind={kind}")

        if kind == "future_as_past":
            anchor = _date_interval(assertion["anchor_date"], f"assertion {assertion_id}.anchor_date")
            event = event_dates.get(event_id)
            bound_ids.append(event_id)
            if event_id not in event_index or not _eligible(assertion["anchor_date"], anchor) or (event_id in event_index and not _eligible(event_index[event_id]["date"], event)):
                issues.append(_issue("TEMPORAL_METADATA_MISSING", "warning", [assertion_id, event_id], "Future/past arithmetic requires verified anchor and event intervals; missing or low-confidence facts remain unresolved.", "Verify both date facts against first-party records."))
            else:
                bound_intervals = {"left": _interval_text(anchor), "right": _interval_text(event)}
                impossible = (predicate == "already_completed" and event[0] > anchor[1]) or (predicate == "forthcoming" and event[1] <= anchor[0])
                valid = (predicate == "already_completed" and event[1] <= anchor[0]) or (predicate == "forthcoming" and event[0] > anchor[1])
                overlap = not impossible and not valid
                if impossible:
                    issues.append(_issue("TEMPORAL_ARITHMETIC_IMPOSSIBLE", "major", [assertion_id, event_id], "The asserted completion/future status contradicts the verified anchor and event intervals.", "Restate the event status at the anchor date or correct the bound dates."))
                elif overlap:
                    issues.append(_issue("TEMPORAL_ORDER_UNRESOLVED", "warning", [assertion_id, event_id], "Date precision leaves the asserted ordering unresolved.", "Obtain finer date precision or qualify the temporal statement."))
        elif kind == "governance":
            bound_ids.extend([source_id, event_id])
            source = source_index.get(source_id)
            event = event_dates.get(event_id)
            if source is None or event_id not in event_index:
                issues.append(_issue("TEMPORAL_REFERENCE_UNRESOLVED", "major", [assertion_id, source_id, event_id], "Governance assertion references an unknown source or event.", "Bind the assertion to registered source and event records."))
            else:
                start, end = source_dates[source_id]["start"], source_dates[source_id]["end"]
                start_ok = _eligible(source["effective_start"], start)
                end_open = source["effective_end"]["open_ended"]
                end_ok = end_open or _eligible(source["effective_end"], end)
                event_ok = _eligible(event_index[event_id]["date"], event)
                range_end = "+infinity" if end_open else end[1].isoformat() if end is not None else None
                bound_intervals = {"left": _interval_text(event), "right": f"{start[0].isoformat()}..{range_end}" if start and range_end else None}
                if not (start_ok and end_ok and event_ok):
                    issues.append(_issue("TEMPORAL_METADATA_MISSING", "warning", [assertion_id, source_id, event_id], "Publication date is not a substitute for a verified effective range; governance cannot be adjudicated from incomplete metadata.", "Verify the source effective start and end against the governing document."))
                elif start[0] > event[1] or (not end_open and end[1] < event[0]):
                    issues.append(_issue("TEMPORAL_ANACHRONISTIC_SOURCE", "major", [assertion_id, source_id, event_id], "The cited source was not effective during the asserted event interval.", "Use the version effective during the event or revise the governance claim."))
        elif kind == "version_comparison":
            bound_ids.append(source_id)
            source = source_index.get(source_id)
            if source is None:
                issues.append(_issue("TEMPORAL_REFERENCE_UNRESOLVED", "major", [assertion_id, source_id], "Version comparison references an unknown source.", "Register the cited version before comparing versions."))
            elif source["version_family_id"] is None:
                issues.append(_issue("TEMPORAL_METADATA_MISSING", "warning", [assertion_id, source_id], "The cited source has no version-family binding, so the comparator cannot be materialized.", "Assign a verified version family and catalog its known versions."))
            else:
                family = source["version_family_id"]
                family_sources = [item for item in source_index.values() if item["version_family_id"] == family]
                materialized = False
                for item in family_sources:
                    interval = source_dates[item["id"]]["published"]
                    if _eligible(item["published_date"], interval) and interval[0].year <= comparator_year <= interval[1].year:
                        materialized = True
                        bound_ids.append(item["id"])
                        break
                if not materialized:
                    exhaustive = any(item["version_catalog_completeness"] == "exhaustive" for item in family_sources)
                    code = "TEMPORAL_COMPARATOR_PHANTOM" if exhaustive else "TEMPORAL_COMPARATOR_UNMATERIALIZED"
                    severity = "major" if exhaustive else "warning"
                    rationale = "The comparator year is absent from a declared exhaustive version catalog." if exhaustive else "The comparator year is not materialized in the available version catalog; absence is not proof that the version never existed."
                    issues.append(_issue(code, severity, [assertion_id, source_id], rationale, "Add a verified comparator-version record or remove/qualify the comparison."))
        elif kind == "causal_order":
            left, left_ids, left_error = resolve_binding(assertion["left_binding"], f"assertion {assertion_id}.left_binding")
            right, right_ids, right_error = resolve_binding(assertion["right_binding"], f"assertion {assertion_id}.right_binding")
            bound_ids.extend(left_ids + right_ids)
            bound_intervals = {"left": _interval_text(left), "right": _interval_text(right)}
            if left_error or right_error or left is None or right is None:
                issues.append(_issue("TEMPORAL_METADATA_MISSING", "warning", [assertion_id, *bound_ids], "Causal ordering requires two verified date intervals; missing or low-confidence dates remain unresolved.", "Verify both causal endpoints against first-party records."))
            else:
                expects_before = predicate in _BEFORE_PREDICATES
                valid = left[1] < right[0] if expects_before else left[0] > right[1]
                inverted = left[0] > right[1] if expects_before else left[1] < right[0]
                if inverted:
                    issues.append(_issue("TEMPORAL_CAUSAL_INVERSION", "major", [assertion_id, *bound_ids], "The verified endpoint order is opposite to the causal relation expressed in the assertion.", "Reverse or qualify the causal narrative, or correct the bound temporal facts."))
                elif not valid:
                    issues.append(_issue("TEMPORAL_ORDER_UNRESOLVED", "warning", [assertion_id, *bound_ids], "Overlapping date intervals do not establish the direction required by the causal wording.", "Use finer temporal resolution or avoid directional causal wording."))

        for match in _DEICTIC_RE.finditer(assertion["text"]):
            issues.append(_issue("TEMPORAL_DEICTIC_LANGUAGE", "warning", [assertion_id], f"Deictic phrase '{match.group(0)}' is anchored to writing time and can become false after publication.", f"Replace it with an explicit date or version anchored to {reference_date.isoformat()}."))

        major = any(item["severity"] == "major" for item in issues)
        gate = "blocked" if major and terminal_policy == "strict" else "review_required" if issues else "passed"
        assertion_results.append({
            "assertion_id": assertion_id,
            "assertion_kind": kind,
            "predicate": predicate,
            "bound_ids": sorted(set(bound_ids)),
            "bound_intervals": bound_intervals,
            "issues": sorted(issues, key=lambda item: (item["severity"], item["code"], item["subject_ids"])),
            "gate": gate,
        })

    provenance = _exact(audit_provenance, {"audit_id", "audit_version", "reviewed_at", "timeline_complete", "assertion_extraction_complete", "rules_independent_from_writer"}, "audit_provenance")
    for field in ("audit_id", "audit_version"):
        _identifier(provenance[field], f"audit_provenance.{field}")
    _parse_iso_day(provenance["reviewed_at"], "audit_provenance.reviewed_at")
    for field in ("timeline_complete", "assertion_extraction_complete", "rules_independent_from_writer"):
        if not isinstance(provenance[field], bool):
            raise ValueError(f"audit_provenance.{field} must be boolean")
    provenance_gate_ids = []
    if not provenance["timeline_complete"]:
        provenance_gate_ids.append("timeline_incomplete")
    if not provenance["assertion_extraction_complete"]:
        provenance_gate_ids.append("assertion_extraction_incomplete")
    if not provenance["rules_independent_from_writer"]:
        provenance_gate_ids.append("audit_rules_not_independent")
    if provenance_gate_ids:
        global_issues.append(_issue("TEMPORAL_AUDIT_INCOMPLETE", "major", provenance_gate_ids, "An incomplete or non-independent audit cannot establish temporal integrity.", "Complete timeline extraction, assertion coverage, and independent-rule review before release."))

    all_issues = global_issues + [issue for result in assertion_results for issue in result["issues"]]
    counts = Counter(issue["severity"] for issue in all_issues)
    release_safe = counts["major"] == 0 and not provenance_gate_ids
    if provenance_gate_ids or (terminal_policy == "strict" and counts["major"]):
        overall_status = "blocked"
    elif all_issues:
        overall_status = "review_required"
    else:
        overall_status = "passed"
    digest_payload = {
        "report_reference_date": report_reference_date, "terminal_policy": terminal_policy, "sources": sources,
        "events": events, "assertions": assertions, "audit_provenance": audit_provenance,
    }
    audit_digest = hashlib.sha256(json.dumps(digest_payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "audit_id": provenance["audit_id"],
        "audit_version": provenance["audit_version"],
        "audit_digest": audit_digest,
        "report_reference_date": report_reference_date,
        "terminal_policy": terminal_policy,
        "source_count": len(source_index),
        "event_count": len(event_index),
        "assertion_count": len(assertion_results),
        "assertion_results": assertion_results,
        "global_issues": sorted(global_issues, key=lambda item: (item["severity"], item["code"], item["subject_ids"])),
        "issue_counts": {severity: counts.get(severity, 0) for severity in ("major", "warning")},
        "provenance_gate_ids": provenance_gate_ids,
        "release_safe": release_safe,
        "overall_status": overall_status,
        "quality_gates": [
            "Publication date never substitutes for a source's effective date range.",
            "Low-confidence or missing temporal facts remain unresolved and are never used as arithmetic ground truth.",
            "Causal direction requires nonoverlapping verified intervals in the asserted order.",
            "A missing comparator is called phantom only when the version catalog is explicitly exhaustive.",
            "The reference date is supplied and recorded; wall-clock time never changes the audit result.",
        ],
        "limitations": [
            "The module evaluates supplied structured bindings and does not infer every temporal relation from unrestricted prose.",
            "Timeline completeness and provenance declarations still require project governance and source review.",
        ],
    }
