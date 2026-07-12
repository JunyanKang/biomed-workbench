import json
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.implementations.nmf_metagenes import factorize
from biomed_workbench.quality import NMFReportError, parse_nmf_outputs


ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "tests" / "fixtures" / "omics"
PARAMETERS = {
    "ranks": "2,3",
    "restarts": 8,
    "max_iter": 2000,
    "tolerance": 0.00001,
    "top_genes": 3,
    "selection_error_gap": 0.01,
    "minimum_component_stability": 0.95,
    "minimum_assignment_stability": 0.95,
    "maximum_component_similarity": 0.95,
    "seed": 271828,
}


class NMFQualityTests(unittest.TestCase):
    def execute(self, root: Path):
        paths = (root / "loadings.tsv", root / "exposures.tsv", root / "report.json")
        factorize(
            FIXTURE / "nmf-matrix.tsv",
            FIXTURE / "nmf-features.txt",
            FIXTURE / "nmf-samples.txt",
            *paths,
            ranks_text=PARAMETERS["ranks"],
            restarts=PARAMETERS["restarts"],
            max_iter=PARAMETERS["max_iter"],
            tolerance=PARAMETERS["tolerance"],
            top_genes=PARAMETERS["top_genes"],
            selection_error_gap=PARAMETERS["selection_error_gap"],
            minimum_component_stability=PARAMETERS["minimum_component_stability"],
            minimum_assignment_stability=PARAMETERS["minimum_assignment_stability"],
            maximum_component_similarity=PARAMETERS["maximum_component_similarity"],
            seed=PARAMETERS["seed"],
        )
        return paths

    def parse(self, paths):
        return parse_nmf_outputs(
            FIXTURE / "nmf-matrix.tsv",
            FIXTURE / "nmf-features.txt",
            FIXTURE / "nmf-samples.txt",
            *paths,
            expected_parameters=PARAMETERS,
        )

    def test_recovers_two_stable_programs_and_recomputes_all_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = self.parse(self.execute(Path(temporary)))

        self.assertEqual(report["selected_rank"], 2)
        self.assertEqual(report["removed_features"], ["GENE_ZERO", "GENE_CONSTANT"])
        self.assertEqual([item["feature"] for item in report["top_features"]["Metagene_1"]], ["GENE_A", "GENE_B", "GENE_C"])
        self.assertEqual([item["feature"] for item in report["top_features"]["Metagene_2"]], ["GENE_D", "GENE_E", "GENE_F"])
        self.assertEqual(report["dominant_component_by_sample"]["SAMPLE_A1"], "Metagene_1")
        self.assertEqual(report["dominant_component_by_sample"]["SAMPLE_B3"], "Metagene_2")
        self.assertEqual(report["quality_status"], "passed")

    def test_rejects_tampered_factor_or_selection_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = self.execute(Path(temporary))
            loadings = paths[0].read_text(encoding="utf-8").replace("0.413196", "0.513196", 1)
            paths[0].write_text(loadings, encoding="utf-8")
            with self.assertRaises(NMFReportError):
                self.parse(paths)

            paths = self.execute(Path(temporary))
            report = json.loads(paths[2].read_text(encoding="utf-8"))
            report["selected_rank"] = 3
            paths[2].write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaises(NMFReportError):
                self.parse(paths)

    def test_rejects_negative_input_instead_of_clipping(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            matrix = root / "matrix.tsv"
            matrix.write_text((FIXTURE / "nmf-matrix.tsv").read_text(encoding="utf-8").replace("10.05", "-10.05", 1), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "never clipped"):
                factorize(
                    matrix,
                    FIXTURE / "nmf-features.txt",
                    FIXTURE / "nmf-samples.txt",
                    root / "loadings.tsv",
                    root / "exposures.tsv",
                    root / "report.json",
                    ranks_text="2,3",
                    restarts=8,
                    max_iter=2000,
                    tolerance=0.00001,
                    top_genes=3,
                    selection_error_gap=0.01,
                    minimum_component_stability=0.95,
                    minimum_assignment_stability=0.95,
                    maximum_component_similarity=0.95,
                    seed=271828,
                )


if __name__ == "__main__":
    unittest.main()
