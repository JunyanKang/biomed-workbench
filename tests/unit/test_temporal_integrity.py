import unittest

from biomed_workbench.capabilities.temporal_integrity import audit_temporal_integrity


def date_fact(value, precision="day", confidence="high", method="original_document", open_ended=False):
    return {
        "value": value,
        "precision": precision,
        "open_ended": open_ended,
        "provenance_method": method,
        "confidence": confidence,
        "source_record_id": "record-1" if value is not None or confidence in {"high", "medium"} else None,
    }


def source(source_id="standard-2024", *, start="2024-01-01", end=None, family="standard-family", completeness="partial"):
    return {
        "id": source_id,
        "published_date": date_fact("2024-01-01"),
        "effective_start": date_fact(start),
        "effective_end": date_fact(end, precision="unknown" if end is None else "day", open_ended=end is None),
        "version_family_id": family,
        "version_catalog_completeness": completeness,
        "supersedes": None,
        "superseded_by": None,
    }


def event(event_id="event-2023", value="2023-05-01"):
    return {"id": event_id, "description": "A dated research event.", "date": date_fact(value)}


def assertion(assertion_id="assertion-1", **overrides):
    value = {
        "id": assertion_id,
        "text": "The source governed the event.",
        "section_path": "Results",
        "assertion_kind": "governance",
        "predicate": "governed_by",
        "anchor_date": None,
        "event_id": "event-2023",
        "source_id": "standard-2024",
        "comparator_year": None,
        "left_binding": None,
        "right_binding": None,
    }
    value.update(overrides)
    return value


def provenance(**overrides):
    value = {
        "audit_id": "temporal-audit-1",
        "audit_version": "1.0.0",
        "reviewed_at": "2026-07-13",
        "timeline_complete": True,
        "assertion_extraction_complete": True,
        "rules_independent_from_writer": True,
    }
    value.update(overrides)
    return value


class TemporalIntegrityTests(unittest.TestCase):
    def run_audit(self, *, sources=None, events=None, assertions=None, policy="strict", audit_provenance=None):
        return audit_temporal_integrity(
            report_reference_date="2026-07-13",
            terminal_policy=policy,
            sources=[source()] if sources is None else sources,
            events=[event()] if events is None else events,
            assertions=[assertion()] if assertions is None else assertions,
            audit_provenance=provenance() if audit_provenance is None else audit_provenance,
        )

    def test_governance_source_outside_event_interval_blocks(self):
        result = self.run_audit()
        row = result["assertion_results"][0]
        self.assertEqual(row["issues"][0]["code"], "TEMPORAL_ANACHRONISTIC_SOURCE")
        self.assertEqual(row["gate"], "blocked")
        self.assertFalse(result["release_safe"])

    def test_publication_date_does_not_replace_missing_effective_range(self):
        item = source()
        item["effective_start"] = date_fact(None, precision="unknown", confidence="unverified", method="unknown")
        item["effective_end"] = date_fact(None, precision="unknown", confidence="unverified", method="unknown")
        result = self.run_audit(sources=[item])
        self.assertEqual(result["assertion_results"][0]["issues"][0]["code"], "TEMPORAL_METADATA_MISSING")
        self.assertEqual(result["overall_status"], "review_required")

    def test_future_as_past_uses_verified_intervals(self):
        claim = assertion(
            assertion_kind="future_as_past",
            predicate="already_completed",
            text="As of March, June work had already completed.",
            anchor_date=date_fact("2025-03", precision="month"),
            event_id="event-future",
            source_id=None,
        )
        result = self.run_audit(sources=[], events=[event("event-future", "2025-06") | {"date": date_fact("2025-06", precision="month")}], assertions=[claim])
        self.assertEqual(result["assertion_results"][0]["issues"][0]["code"], "TEMPORAL_ARITHMETIC_IMPOSSIBLE")

    def test_leap_year_month_interval_is_calendar_correct(self):
        claim = assertion(
            assertion_kind="future_as_past",
            predicate="already_completed",
            anchor_date=date_fact("2024-02", precision="month"),
            event_id="event-february",
            source_id=None,
        )
        february = event("event-february", "2024-02")
        february["date"] = date_fact("2024-02", precision="month")
        result = self.run_audit(sources=[], events=[february], assertions=[claim])
        self.assertEqual(result["assertion_results"][0]["bound_intervals"]["left"], "2024-02-01..2024-02-29")

    def test_low_confidence_date_remains_unresolved(self):
        claim = assertion(
            assertion_kind="future_as_past",
            predicate="already_completed",
            anchor_date=date_fact("2025-03-01", confidence="low", method="adapter_metadata"),
            event_id="event-future",
            source_id=None,
        )
        result = self.run_audit(sources=[], events=[event("event-future", "2025-06-01")], assertions=[claim])
        codes = [item["code"] for item in result["assertion_results"][0]["issues"]]
        self.assertEqual(codes, ["TEMPORAL_METADATA_MISSING"])

    def test_verified_date_requires_non_path_source_record(self):
        claim = assertion(
            assertion_kind="future_as_past",
            predicate="already_completed",
            anchor_date=date_fact("2025-03-01") | {"source_record_id": None},
            event_id="event-future",
            source_id=None,
        )
        with self.assertRaisesRegex(ValueError, "source_record_id"):
            self.run_audit(sources=[], events=[event("event-future", "2025-06-01")], assertions=[claim])

    def test_exhaustive_version_catalog_can_identify_phantom_comparator(self):
        claim = assertion(
            assertion_kind="version_comparison",
            predicate="compares_with",
            event_id=None,
            source_id="standard-2024",
            comparator_year=1998,
        )
        result = self.run_audit(sources=[source(completeness="exhaustive")], events=[], assertions=[claim])
        self.assertEqual(result["assertion_results"][0]["issues"][0]["code"], "TEMPORAL_COMPARATOR_PHANTOM")

    def test_partial_catalog_does_not_turn_absence_into_nonexistence(self):
        claim = assertion(
            assertion_kind="version_comparison",
            predicate="compares_with",
            event_id=None,
            source_id="standard-2024",
            comparator_year=1998,
        )
        result = self.run_audit(sources=[source(completeness="partial")], events=[], assertions=[claim])
        issue = result["assertion_results"][0]["issues"][0]
        self.assertEqual(issue["code"], "TEMPORAL_COMPARATOR_UNMATERIALIZED")
        self.assertEqual(issue["severity"], "warning")

    def test_causal_inversion_uses_explicit_bindings(self):
        claim = assertion(
            assertion_kind="causal_order",
            predicate="enabled",
            event_id=None,
            source_id=None,
            left_binding={"kind": "direct", "id": None, "date": date_fact("2026-01-01")},
            right_binding={"kind": "direct", "id": None, "date": date_fact("2020-01-01")},
        )
        result = self.run_audit(sources=[], events=[], assertions=[claim])
        self.assertEqual(result["assertion_results"][0]["issues"][0]["code"], "TEMPORAL_CAUSAL_INVERSION")

    def test_overlapping_causal_intervals_are_unresolved_not_inverted(self):
        claim = assertion(
            assertion_kind="causal_order",
            predicate="enabled",
            event_id=None,
            source_id=None,
            left_binding={"kind": "direct", "id": None, "date": date_fact("2025", precision="year")},
            right_binding={"kind": "direct", "id": None, "date": date_fact("2025-06", precision="month")},
        )
        result = self.run_audit(sources=[], events=[], assertions=[claim])
        self.assertEqual(result["assertion_results"][0]["issues"][0]["code"], "TEMPORAL_ORDER_UNRESOLVED")

    def test_deictic_language_is_flagged_with_frozen_reference_date(self):
        claim = assertion(
            assertion_kind="narrative",
            predicate="narrative",
            text="Currently, the latest standard is used.",
            event_id=None,
            source_id=None,
        )
        result = self.run_audit(sources=[], events=[], assertions=[claim])
        issues = result["assertion_results"][0]["issues"]
        self.assertEqual([item["code"] for item in issues], ["TEMPORAL_DEICTIC_LANGUAGE", "TEMPORAL_DEICTIC_LANGUAGE"])
        self.assertIn("2026-07-13", issues[0]["suggested_fix"])

    def test_incomplete_audit_cannot_produce_clean_release(self):
        claim = assertion(assertion_kind="narrative", predicate="narrative", text="The 2024 standard was used.", event_id=None, source_id=None)
        result = self.run_audit(sources=[], events=[], assertions=[claim], audit_provenance=provenance(timeline_complete=False))
        self.assertEqual(result["overall_status"], "blocked")
        self.assertIn("timeline_incomplete", result["provenance_gate_ids"])

    def test_digest_is_deterministic(self):
        first = self.run_audit()
        second = self.run_audit()
        self.assertEqual(first, second)

    def test_invalid_month_is_rejected(self):
        claim = assertion(
            assertion_kind="future_as_past",
            predicate="already_completed",
            anchor_date=date_fact("2024-13", precision="month"),
            event_id="event-2023",
            source_id=None,
        )
        with self.assertRaisesRegex(ValueError, "invalid month"):
            self.run_audit(assertions=[claim])


if __name__ == "__main__":
    unittest.main()
