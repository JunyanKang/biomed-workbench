import unittest

from biomed_workbench.capabilities.quantitative_assays import (
    fit_immunoassay_curve,
    quantify_relative_expression,
    summarize_flow_cytometry,
)


class QuantitativeAssayTests(unittest.TestCase):
    def test_qpcr_uses_replicates_multiple_references_and_efficiencies(self):
        measurements = [
            {"sample": sample, "assay": assay, "ct": ct}
            for sample, assay, values in (
                ("control", "target", [20.0, 20.2]),
                ("control", "ref1", [16.0, 16.2]),
                ("control", "ref2", [18.0, 18.2]),
                ("treated", "target", [18.0, 18.2]),
                ("treated", "ref1", [16.0, 16.2]),
                ("treated", "ref2", [18.0, 18.2]),
            )
            for ct in values
        ]
        result = quantify_relative_expression(
            measurements=measurements,
            target_assay="target",
            reference_assays=["ref1", "ref2"],
            calibrator_samples=["control"],
            efficiencies={"target": 2.0, "ref1": 2.0, "ref2": 2.0},
            replicate_ct_sd_limit=0.5,
        )

        treated = next(row for row in result["samples"] if row["sample"] == "treated")
        self.assertAlmostEqual(treated["relative_expression"], 4.0, places=6)
        self.assertEqual(treated["qc_flags"], [])
        self.assertEqual(result["method"], "efficiency-corrected relative quantification with geometric reference normalization")

    def test_immunoassay_aggregates_replicates_and_flags_extrapolation(self):
        standards = [
            {"concentration": concentration, "response": response}
            for concentration, responses in ((0.0, [0.1, 0.11]), (1.0, [0.5, 0.51]), (2.0, [0.9, 0.91]), (3.0, [1.3, 1.31]))
            for response in responses
        ]
        result = fit_immunoassay_curve(
            standards=standards,
            unknowns=[
                {"sample": "in_range", "response": 0.705, "dilution_factor": 2.0},
                {"sample": "high", "response": 1.6, "dilution_factor": 1.0},
            ],
            model="linear",
        )

        self.assertAlmostEqual(result["unknowns"][0]["reported_concentration"], 3.0, places=5)
        self.assertIn("OUTSIDE_CALIBRATED_RESPONSE_RANGE", result["unknowns"][1]["qc_flags"])
        self.assertGreater(result["fit"]["r_squared"], 0.999)
        self.assertEqual(len(result["standards"]), 4)

    def test_flow_cytometry_applies_sequential_parent_gates(self):
        result = summarize_flow_cytometry(
            events=[
                {"FSC": 100.0, "SSC": 30.0, "CD3": 5.0},
                {"FSC": 120.0, "SSC": 35.0, "CD3": 12.0},
                {"FSC": 10.0, "SSC": 5.0, "CD3": 20.0},
            ],
            gates=[
                {"name": "cells", "parent": "all", "conditions": {"FSC": {"min": 50.0}, "SSC": {"min": 20.0}}},
                {"name": "cd3_positive", "parent": "cells", "conditions": {"CD3": {"min": 10.0}}},
            ],
        )

        gates = {row["name"]: row for row in result["gates"]}
        self.assertEqual(gates["cells"]["event_count"], 2)
        self.assertEqual(gates["cd3_positive"]["event_count"], 1)
        self.assertAlmostEqual(gates["cd3_positive"]["percent_of_parent"], 50.0)
        self.assertEqual(result["gate_order"], ["cells", "cd3_positive"])


if __name__ == "__main__":
    unittest.main()
