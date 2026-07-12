import math
import unittest

from biomed_workbench.kernel.identity import canonical_json, digest_value, freeze_mapping, redact_sensitive, validate_identifier


class KernelIdentityTests(unittest.TestCase):
    def test_canonical_json_and_digest_are_order_independent(self):
        first = {"b": [2, 1], "a": {"gene": "TP53", "effect": 0.5}}
        second = {"a": {"effect": 0.5, "gene": "TP53"}, "b": [2, 1]}

        self.assertEqual(canonical_json(first), canonical_json(second))
        self.assertEqual(digest_value(first), digest_value(second))
        self.assertRegex(digest_value(first), r"^[0-9a-f]{64}$")

    def test_state_values_reject_unordered_nonfinite_and_machine_local_content(self):
        invalid = (
            {"values": {"a", "b"}},
            {"effect": math.nan},
            {"effect": math.inf},
            {"path": "/Users/researcher/project/data.tsv"},
            {"path": "/Volumes/research/data.tsv"},
            {"uri": "file:///tmp/data.tsv"},
            {"path": "C:\\Users\\researcher\\data.tsv"},
            {"path": "D:\\research\\data.tsv"},
            {1: "non-string-key"},
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                canonical_json(value)

    def test_redaction_is_recursive_and_does_not_retain_secret_values(self):
        original = {"query": "TP53", "nested": {"api_key": "secret-value", "tokens": [{"authToken": "also-secret"}]}}

        redacted = redact_sensitive(original)
        serialized = canonical_json(redacted)

        self.assertNotIn("secret-value", serialized)
        self.assertNotIn("also-secret", serialized)
        self.assertEqual(redacted["nested"]["api_key"], "[REDACTED]")

    def test_frozen_mapping_is_detached_and_nested_values_cannot_mutate(self):
        original = {"scope": {"tissue": "retina"}, "groups": ["control", "treated"]}
        frozen = freeze_mapping(original)
        original["scope"]["tissue"] = "brain"

        self.assertEqual(frozen["scope"]["tissue"], "retina")
        with self.assertRaises(TypeError):
            frozen["scope"]["tissue"] = "brain"

    def test_identifiers_are_source_neutral_and_stable(self):
        self.assertEqual(validate_identifier("project-retina-01", "project_id"), "project-retina-01")
        for value in ("Project", "source/path", "_hidden", "two spaces"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_identifier(value, "project_id")


if __name__ == "__main__":
    unittest.main()
