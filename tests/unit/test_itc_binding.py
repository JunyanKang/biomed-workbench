import unittest

from biomed_workbench.capabilities.biophysics import (
    _one_site_injection_heats,
    electrophysiology_trace_summary,
    fit_itc_single_site_binding,
)


class ItcBindingTests(unittest.TestCase):
    def test_fits_synthetic_one_site_integrated_heats(self):
        volumes = [2.0] * 12
        expected = _one_site_injection_heats(volumes, 20.0, 200.0, 200.0, -6.0, -8.0, 1.0, 0.1, 0.0)
        result = fit_itc_single_site_binding(volumes, expected, 20.0, 200.0, 200.0)

        self.assertTrue(result["fit_diagnostics"]["converged"])
        self.assertLess(result["fit_diagnostics"]["rmse_ucal"], 1e-5)
        self.assertAlmostEqual(result["parameters"]["kd_m"], 1e-6, places=7)

    def test_summarizes_one_electrophysiology_trace_without_cell_state_claim(self):
        result = electrophysiology_trace_summary(
            time_ms=[0, 1, 2, 3, 4, 5, 6],
            signal=[-70, -70, -69, -50, -20, -45, -68],
            baseline_window_ms=1,
            polarity="positive",
        )

        self.assertEqual(result["baseline"], -70.0)
        self.assertEqual(result["peak_amplitude_from_baseline"], 50.0)
        self.assertEqual(result["time_to_peak_ms"], 4.0)
        self.assertEqual(result["threshold_crossing_count"], 1)
        self.assertEqual(result["quality_status"], "passed")
        self.assertIn("does not detect action-potential classes", result["limitations"][0])


if __name__ == "__main__":
    unittest.main()
