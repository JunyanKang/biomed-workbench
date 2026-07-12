import math
import unittest

from biomed_workbench.capabilities.experiment import (
    dose_response_summary,
    growth_curve_summary,
    pcr_mix,
    serial_dilution,
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


if __name__ == "__main__":
    unittest.main()
