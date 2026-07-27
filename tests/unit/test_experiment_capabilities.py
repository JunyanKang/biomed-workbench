import math
import unittest

from biomed_workbench.capabilities.experiment import (
    dose_response_summary,
    enumerate_cfu_from_dilution_plates,
    growth_curve_summary,
    pcr_mix,
    serial_dilution,
    simulate_bacterial_population_scenario,
)


class ExperimentCapabilityTests(unittest.TestCase):
    def test_serial_dilution_conserves_volume_and_tracks_concentration(self):
        result = serial_dilution(initial_concentration=100.0, dilution_factor=10.0, steps=3, final_volume_ul=1000.0)

        self.assertEqual([step["concentration"] for step in result["steps"]], [10.0, 1.0, 0.1])
        self.assertTrue(all(math.isclose(step["transfer_ul"] + step["diluent_ul"], 1000.0) for step in result["steps"]))

    def test_pcr_mix_applies_reaction_overage(self):
        result = pcr_mix(
            reactions=8,
            reaction_volume_ul=20.0,
            components={"master_mix": 10.0, "forward_primer": 1.0, "reverse_primer": 1.0, "template": 2.0},
            overage_percent=10.0,
        )

        self.assertAlmostEqual(result["water_per_reaction_ul"], 6.0)
        self.assertAlmostEqual(result["master_mix"]["water"], 52.8)
        self.assertEqual(result["prepared_reaction_equivalents"], 8.8)

    def test_dose_response_estimates_half_max_on_log_scale(self):
        result = dose_response_summary(
            concentrations=[0.1, 1.0, 10.0, 100.0],
            responses=[98.0, 80.0, 20.0, 2.0],
            direction="decreasing",
        )

        self.assertGreater(result["half_max_concentration"], 1.0)
        self.assertLess(result["half_max_concentration"], 10.0)
        self.assertTrue(result["monotonic"])

    def test_growth_curve_recovers_exponential_doubling_time(self):
        times = [0, 1, 2, 3, 4]
        values = [0.05 * math.exp(0.7 * time) for time in times]
        result = growth_curve_summary(times, values, window=3)

        self.assertAlmostEqual(result["max_growth_rate_per_time"], 0.7, places=6)
        self.assertAlmostEqual(result["doubling_time"], math.log(2) / 0.7, places=6)
        self.assertTrue(result["fit_admissible"])
        self.assertEqual(result["interpretation_status"], "blocked-review-required")

    def test_growth_curve_retains_replicates_and_blocks_nonbiological_designs(self):
        observations = [
            {"time_hours": time, "od": 0.05 + 1.2 / (1 + math.exp(-1.1 * (time - 3))) + offset, "replicate_id": replicate}
            for time in range(7)
            for replicate, offset in (("a", -0.003), ("b", 0.003))
        ]
        result = growth_curve_summary(
            observations=observations,
            blank_od=0.05,
            replicate_level="technical",
        )

        self.assertTrue(result["fit_admissible"])
        self.assertIn(result["selected_model"], {"logistic", "modified_gompertz"})
        self.assertEqual(result["replicate_design_status"], "complete-at-every-timepoint")
        self.assertEqual(result["interpretation_status"], "blocked-review-required")
        self.assertEqual(result["distinct_timepoint_count"], 7)
        self.assertTrue(all(row["replicate_count"] == 2 for row in result["timepoint_summary"]))

    def test_cfu_enumeration_pools_observed_countable_plate_exposure(self):
        result = enumerate_cfu_from_dilution_plates(
            plates=[
                {"plate_id": "d4-a", "replicate_id": "culture-a", "dilution_factor": 10_000, "plated_volume_ml": 0.1, "count_status": "counted", "colony_count": 92},
                {"plate_id": "d4-b", "replicate_id": "culture-b", "dilution_factor": 10_000, "plated_volume_ml": 0.1, "count_status": "counted", "colony_count": 96},
                {"plate_id": "d5-a", "replicate_id": "culture-a", "dilution_factor": 100_000, "plated_volume_ml": 0.1, "count_status": "counted", "colony_count": 11},
                {"plate_id": "d3-a", "replicate_id": "culture-a", "dilution_factor": 1_000, "plated_volume_ml": 0.1, "count_status": "tntc"},
            ],
            replicate_level="biological",
        )

        self.assertTrue(result["estimate_admissible"])
        self.assertEqual(result["countable_plate_count"], 2)
        self.assertEqual(result["plate_results"][2]["selection_status"], "excluded-below-countable-range")
        self.assertEqual(result["plate_results"][3]["selection_status"], "excluded-tntc")
        self.assertAlmostEqual(result["cfu_per_ml"], 9_400_000.0)
        self.assertEqual(result["comparative_interpretation_status"], "eligible-for-design-aware-comparison")

    def test_cfu_enumeration_blocks_when_no_plate_is_countable(self):
        result = enumerate_cfu_from_dilution_plates(
            plates=[
                {"plate_id": "low", "replicate_id": "culture-a", "dilution_factor": 100_000, "plated_volume_ml": 0.1, "count_status": "counted", "colony_count": 3},
                {"plate_id": "high", "replicate_id": "culture-a", "dilution_factor": 1_000, "plated_volume_ml": 0.1, "count_status": "tntc"},
            ]
        )

        self.assertFalse(result["estimate_admissible"])
        self.assertEqual(result["enumeration_status"], "blocked-no-countable-plates")
        self.assertIsNone(result["cfu_per_ml"])

    def test_bacterial_population_scenario_is_explicitly_simulated(self):
        result = simulate_bacterial_population_scenario(
            initial_population=100.0,
            growth_rate_per_hour=1.0,
            clearance_rate_per_hour=0.2,
            carrying_capacity=10_000.0,
            duration_hours=12.0,
            output_steps=25,
        )
        self.assertTrue(result["population_is_simulated"])
        self.assertEqual(result["equilibrium_status"], "positive-equilibrium")
        self.assertAlmostEqual(result["deterministic_equilibrium_population"], 8000.0)
        self.assertEqual(len(result["trajectory"]), 25)
        self.assertGreater(result["trajectory"][-1]["simulated_population"], 100.0)


if __name__ == "__main__":
    unittest.main()
