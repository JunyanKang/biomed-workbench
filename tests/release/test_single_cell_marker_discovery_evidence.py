import hashlib
import json
import unittest
from pathlib import Path

from biomed_workbench.modules.contract import parse_manifest, version_is_allowed


ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = (
    ROOT
    / "biomed_workbench"
    / "modules"
    / "builtin"
    / "single-cell-marker-discovery"
)
REPORT = ROOT / "reports" / "single-cell-marker-discovery-live-verification.json"


class SingleCellMarkerDiscoveryEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))
        cls.manifest = parse_manifest(
            json.loads((MODULE_ROOT / "module.json").read_text(encoding="utf-8"))
        )

    def test_report_is_bound_to_template_and_compatibility_row(self):
        row = self.manifest.compatibility_matrix[0]
        template = MODULE_ROOT / "templates" / "discover_markers.py"
        self.assertTrue(self.report["passed"])
        self.assertEqual(self.report["module_id"], self.manifest.id)
        self.assertEqual(self.report["module_version"], self.manifest.version)
        self.assertEqual(self.report["compatibility_row_id"], row.id)
        self.assertEqual(
            self.report["templates"]["marker"]["sha256"],
            hashlib.sha256(template.read_bytes()).hexdigest(),
        )
        self.assertTrue(
            version_is_allowed(
                self.report["tool_versions"]["scanpy"],
                row.tool_versions["scanpy"],
            )
        )
        self.assertTrue(
            all(
                version_is_allowed(value, row.dependency_versions[name])
                for name, value in self.report["dependency_versions"].items()
            )
        )

    def test_discovery_and_validation_are_separated(self):
        execution = self.report["execution"]
        summary = self.report["scientific_summary"]
        self.assertTrue(execution["marker_ranking_completed"])
        self.assertTrue(execution["held_out_validation_completed"])
        self.assertTrue(execution["held_out_perturbation_rank_invariance_completed"])
        self.assertTrue(execution["output_reloaded"])
        self.assertTrue(summary["discovery_sample_stability_computed"])
        self.assertTrue(summary["held_out_sample_stability_computed"])
        self.assertTrue(
            summary["validation_excluded_from_ranking_and_threshold_selection"]
        )
        self.assertTrue(summary["held_out_values_do_not_change_discovery_ranks"])
        self.assertTrue(summary["held_out_perturbation_changes_validation_evidence"])
        self.assertTrue(summary["planted_markers_independently_validated"])

    def test_inferential_and_annotation_boundaries_are_enforced(self):
        summary = self.report["scientific_summary"]
        self.assertTrue(summary["cell_level_p_values_limited_to_descriptive_scope"])
        self.assertTrue(summary["raw_counts_preserved"])
        self.assertTrue(summary["no_automatic_label_assignment"])

    def test_report_contains_no_machine_path_or_credential(self):
        serialized = REPORT.read_text(encoding="utf-8")
        for marker in (
            "/Users/",
            "/private/",
            "/var/folders/",
            "API_KEY",
            "ACCESS_TOKEN=",
            "SECRET=",
        ):
            self.assertNotIn(marker, serialized)


if __name__ == "__main__":
    unittest.main()
