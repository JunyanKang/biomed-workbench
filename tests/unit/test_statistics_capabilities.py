import unittest

from biomed_workbench.capabilities.statistics import benjamini_hochberg, hypergeometric_tail, welch_t_test


class StatisticsCapabilityTests(unittest.TestCase):
    def test_bh_adjustment_is_monotone_in_sorted_p_values(self):
        adjusted = benjamini_hochberg([0.01, 0.04, 0.03])
        self.assertEqual([round(value, 6) for value in adjusted], [0.03, 0.04, 0.04])

    def test_hypergeometric_tail_matches_finite_population_probability(self):
        result = hypergeometric_tail(population=100, successes=10, draws=5, observed=3)
        expected = sum(
            __import__("math").comb(10, value) * __import__("math").comb(90, 5 - value) / __import__("math").comb(100, 5)
            for value in range(3, 6)
            if value <= 10 and 5 - value <= 90
        )
        self.assertAlmostEqual(result, expected)

    def test_welch_test_detects_separated_groups_and_reports_degrees_of_freedom(self):
        result = welch_t_test([1, 2, 3, 4, 5], [10, 11, 12, 13, 14])
        self.assertLess(result["p_value_two_sided"], 0.001)
        self.assertLess(result["t_statistic"], 0)
        self.assertGreater(result["degrees_of_freedom"], 0)


if __name__ == "__main__":
    unittest.main()
