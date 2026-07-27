import unittest
import base64
from io import BytesIO

from biomed_workbench.capabilities.quantitative_assays import (
    fit_immunoassay_curve,
    import_fcs_events,
    quantify_relative_expression,
    summarize_crystal_violet_biofilm,
    summarize_dye_dilution_proliferation,
    summarize_annexin_viability_quadrants,
    fit_dna_content_phases,
    summarize_flow_immunophenotypes,
    summarize_flow_cytometry,
    summarize_western_blot_densitometry,
    summarize_radiotracer_biodistribution,
    summarize_xenograft_tumor_growth,
    fit_accelerated_stability,
)


class QuantitativeAssayTests(unittest.TestCase):
    def test_crystal_violet_summary_retains_blank_control_and_replicates(self):
        result = summarize_crystal_violet_biofilm(
            [
                {"group": "blank", "replicate_id": "b1", "role": "blank", "absorbance": 0.10},
                {"group": "blank", "replicate_id": "b2", "role": "blank", "absorbance": 0.12},
                {"group": "control", "replicate_id": "c1", "role": "control", "absorbance": 0.42},
                {"group": "control", "replicate_id": "c2", "role": "control", "absorbance": 0.46},
                {"group": "treated", "replicate_id": "t1", "role": "test", "absorbance": 0.78},
                {"group": "treated", "replicate_id": "t2", "role": "test", "absorbance": 0.82},
            ],
            replicate_level="biological",
        )
        treated = next(row for row in result["groups"] if row["group"] == "treated")
        self.assertAlmostEqual(result["blank_mean_absorbance"], 0.11)
        self.assertAlmostEqual(treated["fold_of_control"], 0.69 / 0.33)
        self.assertEqual(result["comparative_interpretation_status"], "eligible-for-design-aware-comparison")

    def test_dna_content_fit_requires_convergence_separation_and_residual_quality(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy and scipy are exercised in the declared DNA-content compatibility environment")
        rng = np.random.default_rng(17)
        values = np.concatenate((rng.normal(100, 8, 900), rng.uniform(112, 188, 300), rng.normal(200, 8, 300))).tolist()
        result = fit_dna_content_phases(values, bins=96, minimum_peak_separation=2.0)

        self.assertTrue(result["fit_admissible"])
        self.assertEqual(result["fit_status"], "admissible")
        self.assertEqual(result["g2_g1_ratio"], 2.0)
        self.assertGreater(result["peak_separation_sigma"], 2.0)
        self.assertAlmostEqual(sum(result["phase_percentages"].values()), 100.0)

    def test_annexin_quadrants_preserve_parent_denominator(self):
        result = summarize_annexin_viability_quadrants([
            {"quadrant": "viable", "event_count": 70}, {"quadrant": "early_apoptotic", "event_count": 10},
            {"quadrant": "late_apoptotic", "event_count": 15}, {"quadrant": "necrotic", "event_count": 5},
        ])

        self.assertEqual(result["total_parent_events"], 100)
        self.assertEqual(result["total_apoptotic_event_count"], 25)
        self.assertEqual(result["total_apoptotic_percent"], 25.0)

    def test_dye_dilution_metrics_use_precursor_equivalent_denominators(self):
        result = summarize_dye_dilution_proliferation(
            [
                {"generation": 0, "event_count": 40},
                {"generation": 1, "event_count": 40},
                {"generation": 2, "event_count": 40},
            ]
        )

        self.assertEqual(result["total_observed_events"], 120)
        self.assertEqual(result["precursor_equivalent_count"], 70.0)
        self.assertAlmostEqual(result["percent_divided"], 42.857142857142854)
        self.assertAlmostEqual(result["division_index"], 0.5714285714285714)
        self.assertAlmostEqual(result["proliferation_index"], 1.3333333333333333)
        self.assertEqual(result["proliferation_index_status"], "defined")

    def test_fcs_import_preserves_all_events_and_channels(self):
        try:
            import flowio
        except ImportError:
            self.skipTest("flowio is exercised in the module's declared compatibility environment")
        fixture = BytesIO()
        flowio.create_fcs(
            fixture,
            [100.0, 20.0, 5.0, 120.0, 35.0, 12.0],
            ["FSC-A", "SSC-A", "CD3-A"],
            metadata_dict={"CYT": "Synthetic Cytometer"},
        )
        result = import_fcs_events(fcs_base64=base64.b64encode(fixture.getvalue()).decode("ascii"))

        self.assertEqual(result["event_count"], 2)
        self.assertEqual(result["channels"], ["FSC-A", "SSC-A", "CD3-A"])
        self.assertEqual(result["events"][1]["CD3-A"], 12.0)
        self.assertEqual(result["metadata"]["cyt"], "Synthetic Cytometer")

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

    def test_immunophenotype_quantifies_rules_without_turning_them_into_identity_calls(self):
        result = summarize_flow_immunophenotypes(
            events=[
                {"CD3": 12.0, "CD4": 8.0},
                {"CD3": 14.0, "CD4": 2.0},
                {"CD3": 3.0, "CD4": 9.0},
            ],
            gates=[{"name": "live_singlets", "event_indices": [0, 1]}],
            population_rules=[{"name": "cd3_cd4_pattern", "parent_gate": "live_singlets", "conditions": {"CD3": {"min": 10.0}, "CD4": {"min": 5.0}}}],
            control_review={"panel_identity": "panel-a", "sample_identity": "sample-1", "compensation_reviewed": True, "transformation_declared": True, "threshold_basis_reviewed": True},
        )

        pattern = result["population_patterns"][0]
        self.assertEqual(pattern["event_count"], 1)
        self.assertEqual(pattern["event_indices"], [0])
        self.assertEqual(pattern["interpretation"], "descriptive_marker_pattern_not_cell_identity_call")
        self.assertEqual(result["review_status"], "eligible_for_descriptive_pattern_interpretation")

    def test_western_blot_reviewed_roi_accounting_retains_normalization_scope(self):
        result = summarize_western_blot_densitometry(
            measurements=[
                {
                    "lane_id": "control-1",
                    "condition": "control",
                    "target_integrated_intensity": 1200.0,
                    "target_background_per_pixel": 2.0,
                    "target_area_pixels": 100.0,
                    "loading_control_integrated_intensity": 1000.0,
                    "loading_control_background_per_pixel": 2.0,
                    "loading_control_area_pixels": 100.0,
                    "biological_replicate_id": "bio-1",
                },
                {
                    "lane_id": "treated-1",
                    "condition": "treated",
                    "target_integrated_intensity": 2200.0,
                    "target_background_per_pixel": 2.0,
                    "target_area_pixels": 100.0,
                    "loading_control_integrated_intensity": 1000.0,
                    "loading_control_background_per_pixel": 2.0,
                    "loading_control_area_pixels": 100.0,
                    "biological_replicate_id": "bio-2",
                },
            ],
            reference_lane_ids=["control-1"],
            replicate_level="biological",
        )

        treated = next(row for row in result["lanes"] if row["lane_id"] == "treated-1")
        self.assertAlmostEqual(treated["normalized_intensity"], 2.5)
        self.assertAlmostEqual(treated["fold_change_vs_reference"], 2.0)
        self.assertEqual(result["condition_summary"][1]["lane_count"], 1)
        self.assertEqual(result["replicate_level"], "biological")

    def test_radiotracer_biodistribution_retains_observed_interval_and_ratio_boundary(self):
        result = summarize_radiotracer_biodistribution(
            measurements=[
                {"sample_id": "mouse-1", "organ": "tumor", "time_hours": 1.0, "injected_dose_bq": 1000.0, "tissue_activity_bq": 20.0, "tissue_mass_g": 0.2},
                {"sample_id": "mouse-1", "organ": "blood", "time_hours": 1.0, "injected_dose_bq": 1000.0, "tissue_activity_bq": 10.0, "tissue_mass_g": 0.5},
                {"sample_id": "mouse-2", "organ": "tumor", "time_hours": 4.0, "injected_dose_bq": 1000.0, "tissue_activity_bq": 10.0, "tissue_mass_g": 0.2},
                {"sample_id": "mouse-2", "organ": "blood", "time_hours": 4.0, "injected_dose_bq": 1000.0, "tissue_activity_bq": 2.0, "tissue_mass_g": 0.5},
            ],
            tumor_organ="tumor",
            blood_organ="blood",
            replicate_level="biological",
        )

        self.assertAlmostEqual(result["measurements"][0]["percent_injected_dose_per_gram"], 10.0)
        tumor_auc = next(row for row in result["organ_auc_summary"] if row["organ"] == "tumor")
        self.assertAlmostEqual(tumor_auc["trapezoidal_auc_percent_injected_dose_per_gram_hour"], 22.5)
        self.assertAlmostEqual(result["tumor_to_blood_ratios"][0]["tumor_to_blood_ratio"], 5.0)

    def test_xenograft_summary_retains_animal_level_endpoint_tgi_boundary(self):
        result = summarize_xenograft_tumor_growth(
            observations=[
                {"animal_id": "c1", "group": "vehicle", "time_days": 0.0, "tumor_volume_mm3": 100.0},
                {"animal_id": "c1", "group": "vehicle", "time_days": 10.0, "tumor_volume_mm3": 300.0},
                {"animal_id": "t1", "group": "drug", "time_days": 0.0, "tumor_volume_mm3": 100.0},
                {"animal_id": "t1", "group": "drug", "time_days": 10.0, "tumor_volume_mm3": 150.0},
            ],
            control_group="vehicle",
        )
        drug = next(row for row in result["endpoint_group_summary"] if row["group"] == "drug")
        self.assertAlmostEqual(drug["tumor_growth_inhibition_percent_vs_control"], 75.0)
        self.assertEqual(result["animal_count"], 2)

    def test_accelerated_stability_fits_shared_first_order_model(self):
        result = fit_accelerated_stability(
            observations=[
                {"temperature_c": 25.0, "time_days": 0.0, "potency_percent": 100.0},
                {"temperature_c": 25.0, "time_days": 10.0, "potency_percent": 90.0},
                {"temperature_c": 25.0, "time_days": 20.0, "potency_percent": 81.0},
                {"temperature_c": 40.0, "time_days": 0.0, "potency_percent": 100.0},
                {"temperature_c": 40.0, "time_days": 10.0, "potency_percent": 80.0},
                {"temperature_c": 40.0, "time_days": 20.0, "potency_percent": 64.0},
            ],
            target_temperature_c=30.0,
            specification_percent=90.0,
        )
        self.assertEqual(result["selected_kinetic_model"], "first-order")
        self.assertGreater(result["predicted_time_to_specification_days"], 0)


if __name__ == "__main__":
    unittest.main()
