from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry
from biomed_workbench.router import route


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "biomed_workbench/modules/builtin/rna-processing-alternative-splicing/templates/run_rna_processing_workflow.py"
FIXTURES = ROOT / "tests/fixtures/rna_processing"


def load_runner():
    spec = importlib.util.spec_from_file_location("rna_processing_workflow", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RNAProcessingAlternativeSplicingTests(unittest.TestCase):
    def test_manifest_and_entrypoint_are_discoverable(self) -> None:
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        manifest = registry.get("rna-processing-alternative-splicing")
        self.assertEqual(manifest.version, "1.0.0")
        self.assertTrue(callable(registry.resolve_entrypoint(manifest.id)))
        self.assertFalse(manifest.code_templates[0].requires_adaptation)

    def test_method_selection_keeps_estimands_distinct(self) -> None:
        runner = load_runner()
        event = runner.method_selection({"assay_class": "bulk-short-read", "scientific_question": "event-level-splicing"})
        dtu = runner.method_selection({"assay_class": "bulk-short-read", "scientific_question": "transcript-usage"})
        droplet = runner.method_selection({"assay_class": "single-nucleus-three-prime", "scientific_question": "event-level-splicing"})
        self.assertEqual(event["primary_method"], "rMATS-turbo")
        self.assertIn("DRIMSeq", dtu["primary_method"])
        self.assertEqual(droplet["primary_method"], "sample-level junction candidate screen")

    def test_junction_screen_uses_sample_level_gates(self) -> None:
        runner = load_runner()
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            report = runner.run_junction_screen({
                "junction_counts_tsv": str(FIXTURES / "junction_counts.tsv"),
                "min_event_count_per_sample": 20,
                "min_junction_count_per_sample": 3,
                "max_within_condition_psi_range": 0.2,
                "min_abs_delta_psi": 0.1,
            }, out)
            self.assertEqual(report["scientific_status"], "candidate")
            self.assertEqual(report["candidate_count"], 1)
            rows = runner.read_tsv(out / "junction_candidate_events.tsv")
            self.assertEqual(rows[0]["event_id"], "E1")
            self.assertEqual(rows[0]["candidate_pass"], "true")

    def test_integration_preserves_causal_uncertainty(self) -> None:
        runner = load_runner()
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            splice = out / "events.tsv"
            splice.write_text("event_id\tgene_id\nE1\tTpm1\nE2\tUnknown\n", encoding="utf-8")
            report = runner.run_evidence_integration({
                "splicing_events_tsv": str(splice),
                "evidence_ledger_tsv": str(FIXTURES / "evidence_ledger.tsv"),
            }, out)
            self.assertEqual(report["linked_event_count"], 1)
            rows = runner.read_tsv(out / "rna_processing_evidence_integration.tsv")
            self.assertTrue(all(row["causal_status"] == "unresolved" for row in rows))

    def test_router_resolves_rna_processing_without_secondary_structure(self) -> None:
        result = route(
            "Use 3' snRNA-seq junction evidence to assess RNA processing and splicing changes, not RNA secondary structure.",
            per_workflow=10,
        )
        self.assertIn("rna-processing-alternative-splicing", result["selected_module_ids"])
        self.assertNotIn("rna-secondary-structure-summary", result["selected_module_ids"])


if __name__ == "__main__":
    unittest.main()
