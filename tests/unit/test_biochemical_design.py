import unittest

from biomed_workbench.capabilities.biochemical_design import (
    fit_enzyme_kinetics,
    plan_golden_gate,
    scan_glycosylation,
)


class BiochemicalDesignTests(unittest.TestCase):
    def test_kinetics_returns_model_diagnostics_and_observation_residuals(self):
        result = fit_enzyme_kinetics(
            observations=[
                {"substrate": substrate, "velocity": 10.0 * substrate / (3.0 + substrate)}
                for substrate in [0.5, 1.0, 2.0, 5.0, 10.0, 20.0]
            ],
            model="michaelis_menten",
        )

        self.assertAlmostEqual(result["parameters"]["vmax"], 10.0, places=4)
        self.assertAlmostEqual(result["parameters"]["km"], 3.0, places=4)
        self.assertGreater(result["diagnostics"]["r_squared"], 0.999999)
        self.assertEqual(len(result["observations"]), 6)
        self.assertIn("aicc", result["diagnostics"])

    def test_glycosylation_scan_reports_context_and_overlap(self):
        result = scan_glycosylation("MANVTNPSNAT", context_radius=2)

        self.assertEqual([site["start"] for site in result["n_linked_sequons"]], [3, 9])
        self.assertEqual(result["n_linked_sequons"][0]["motif"], "NVT")
        self.assertEqual(result["coordinate_system"], "one-based inclusive")

    def test_golden_gate_checks_reverse_sites_overhang_uniqueness_and_junctions(self):
        result = plan_golden_gate(
            fragments=[
                {"name": "promoter", "sequence": "ATGCGCAT", "left_overhang": "AATG", "right_overhang": "GGCT"},
                {"name": "cds", "sequence": "ATGAAATAG", "left_overhang": "GGCT", "right_overhang": "CGCT"},
            ],
            enzyme="BsaI",
            circular=False,
        )

        self.assertTrue(result["assembly_ready"])
        self.assertEqual(result["junctions"][0]["overhang"], "GGCT")
        self.assertEqual(result["internal_site_findings"], [])
        self.assertEqual(result["risk_findings"], [])


if __name__ == "__main__":
    unittest.main()
