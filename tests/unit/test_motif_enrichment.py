"""Regression tests for deterministic known-PWM motif enrichment."""

from __future__ import annotations

import unittest

from biomed_workbench.implementations.motif_enrichment import MotifEnrichmentError, known_motif_enrichment


MOTIF = {"id": "ACGT", "matrix": {"A": [10, 0, 0, 0], "C": [0, 10, 0, 0], "G": [0, 0, 10, 0], "T": [0, 0, 0, 10]}}


class MotifEnrichmentTests(unittest.TestCase):
    def test_known_motif_is_detected_on_both_strands_and_enriched(self):
        result = known_motif_enrichment(
            ["TTACGTAA", "GGACGTCC", "ACGTGGGG", "TTTACGTA"],
            ["TTTTTTTT", "CCCCCCCC", "GGGGGGGG", "TATATATA"], [MOTIF], threshold=0.8,
        )
        row = result["results"][0]
        self.assertEqual((row["foreground_hits"], row["background_hits"]), (4, 0))
        self.assertGreater(row["odds_ratio"], 1)
        self.assertLess(row["adjusted_p_value"], 0.1)

    def test_invalid_pwm_and_threshold_are_blocked(self):
        with self.assertRaisesRegex(MotifEnrichmentError, "A/C/G/T"):
            known_motif_enrichment(["ACGT"], ["TTTT"], [{"id": "bad", "matrix": {}}])
        with self.assertRaisesRegex(MotifEnrichmentError, "threshold"):
            known_motif_enrichment(["ACGT"], ["TTTT"], [MOTIF], threshold=0)


if __name__ == "__main__":
    unittest.main()
