import math
import unittest

from biomed_workbench.capabilities.rhythm import fit_fixed_period_cosinor


class CosinorTests(unittest.TestCase):
    def test_recovers_declared_fixed_period_signal(self):
        time = [float(index * 3) for index in range(16)]
        values = [10.0 + 2.0 * math.cos(2 * math.pi * item / 24.0) for item in time]
        result = fit_fixed_period_cosinor(time, values)

        self.assertAlmostEqual(result["parameters"]["mesor"], 10.0, places=8)
        self.assertAlmostEqual(result["parameters"]["amplitude"], 2.0, places=8)
        self.assertLess(result["fit_diagnostics"]["zero_amplitude_p_value"], 1e-8)


if __name__ == "__main__":
    unittest.main()
