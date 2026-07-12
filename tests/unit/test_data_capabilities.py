import unittest

from biomed_workbench.capabilities.data import profile_table, sequence_inspect


class DataCapabilityTests(unittest.TestCase):
    def test_sequence_inspect_normalizes_dna_and_reports_composition(self):
        result = sequence_inspect("atgc nn\n", alphabet="dna")

        self.assertEqual(result["normalized_sequence"], "ATGCNN")
        self.assertEqual(result["length"], 6)
        self.assertEqual(result["canonical_length"], 4)
        self.assertAlmostEqual(result["gc_percent"], 50.0)
        self.assertEqual(result["reverse_complement"], "NNGCAT")
        self.assertEqual(result["ambiguous_positions"], [5, 6])

    def test_sequence_inspect_rejects_invalid_alphabet(self):
        with self.assertRaises(ValueError):
            sequence_inspect("ATGZ", alphabet="dna")

    def test_table_profile_infers_columns_missingness_and_uniqueness(self):
        result = profile_table(
            [
                {"sample": "A", "count": 10, "group": "control"},
                {"sample": "B", "count": 12, "group": "treated"},
                {"sample": "C", "count": None, "group": "treated"},
            ]
        )

        self.assertEqual(result["row_count"], 3)
        self.assertEqual(result["column_count"], 3)
        self.assertEqual(result["columns"]["count"]["missing_count"], 1)
        self.assertEqual(result["columns"]["count"]["inferred_type"], "integer")
        self.assertEqual(result["columns"]["group"]["unique_count"], 2)


if __name__ == "__main__":
    unittest.main()
