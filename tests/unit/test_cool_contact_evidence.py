"""Focused tests for strict .cool contact evidence extraction."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import h5py
import numpy as np

from biomed_workbench.implementations.cool_contact_evidence import CoolContactError, cool_contact_candidates


def write_cool(path: Path) -> None:
    with h5py.File(path, "w") as handle:
        handle.attrs["format"] = "HDF5::Cooler"
        handle.attrs["bin-size"] = 100
        chroms = handle.create_group("chroms")
        chroms.create_dataset("name", data=np.array([b"chr1"]))
        chroms.create_dataset("length", data=np.array([400], dtype=np.int64))
        bins = handle.create_group("bins")
        bins.create_dataset("chrom", data=np.array([0, 0, 0, 0], dtype=np.int64))
        bins.create_dataset("start", data=np.array([0, 100, 200, 300], dtype=np.int64))
        bins.create_dataset("end", data=np.array([100, 200, 300, 400], dtype=np.int64))
        pixels = handle.create_group("pixels")
        pixels.create_dataset("bin1_id", data=np.array([0, 0, 0, 1, 1, 2], dtype=np.int64))
        pixels.create_dataset("bin2_id", data=np.array([0, 1, 2, 1, 2, 3], dtype=np.int64))
        pixels.create_dataset("count", data=np.array([10, 4, 12, 10, 2, 4], dtype=np.int64))


class CoolContactEvidenceTests(unittest.TestCase):
    def test_extracts_same_chromosome_candidates_with_descriptive_distance_baseline(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cool = root / "test.cool"
            elements = root / "elements.bed"
            write_cool(cool)
            elements.write_text("chr1\t10\t40\tenh-1\tenhancer\nchr1\t205\t250\tprom-1\tpromoter\n", encoding="utf-8")
            result = cool_contact_candidates(cool, elements)
            self.assertEqual(result["cool"]["bin_size"], 100)
            self.assertEqual(result["candidate_count"], 1)
            candidate = result["candidates"][0]
            self.assertEqual(candidate["observed_count"], 12.0)
            self.assertEqual(candidate["distance_median_count"], 12.0)
            self.assertEqual(candidate["observed_over_distance_median"], 1.0)

    def test_rejects_implicit_element_type_and_non_cool_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake = root / "not-cool.h5"
            elements = root / "elements.bed"
            with h5py.File(fake, "w"):
                pass
            elements.write_text("chr1\t10\t40\tenh-1\n", encoding="utf-8")
            with self.assertRaisesRegex(CoolContactError, "regulatory-elements BED requires"):
                cool_contact_candidates(fake, elements)


if __name__ == "__main__":
    unittest.main()
