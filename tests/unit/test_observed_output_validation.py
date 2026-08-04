import tempfile
import unittest
from pathlib import Path

from biomed_workbench.modules.observed_output_validation import validate_observed_output


class ObservedOutputValidationTests(unittest.TestCase):
    def _context(self):
        return {"module_id": "functional-enrichment", "module_version": "1.0.0", "port": "result"}

    def test_tabular_payload_is_reloaded_and_row_counted(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "result.tsv"
            path.write_text("term\tp_value\nDNA repair\t0.01\n", encoding="utf-8")
            self.assertTrue(validate_observed_output(
                content={"format": "tab-separated-values", "record_count": 1},
                payloads=({"role": "primary", "media_type": "text/tab-separated-values", "path": str(path)},),
                context=self._context(),
            ))

    def test_claimed_media_type_cannot_substitute_for_format_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "result.json"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "media type"):
                validate_observed_output(
                    content={"format": "inline-json", "record_count": 1},
                    payloads=({"role": "primary", "media_type": "text/plain", "path": str(path)},),
                    context=self._context(),
                )

    def test_binary_signature_is_checked_during_reload(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "result.h5ad"
            path.write_text("not hdf5", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "HDF5"):
                validate_observed_output(
                    content={"format": "h5ad", "record_count": 0},
                    payloads=({"role": "primary", "media_type": "application/x-hdf5", "path": str(path)},),
                    context=self._context(),
                )


if __name__ == "__main__":
    unittest.main()
