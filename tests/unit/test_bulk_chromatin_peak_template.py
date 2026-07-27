"""Focused contract tests for the bulk chromatin MACS3 template."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "biomed_workbench/modules/builtin/bulk-chromatin-peak-calling/templates/call_macs3_chromatin.py"


def load_template():
    spec = importlib.util.spec_from_file_location("bulk_chromatin_template", TEMPLATE)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load bulk chromatin template")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BulkChromatinPeakTemplateTests(unittest.TestCase):
    def test_chip_seq_requires_control_and_cutrun_command_records_fixed_extension(self):
        module = load_template()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            treatment = root / "treatment.bed"
            treatment.write_text("chr1\t10\t30\n", encoding="utf-8")
            arguments = SimpleNamespace(
                assay="chip-seq", treatment=treatment, control=None, input_format="BED", peak_mode="narrow",
                genome_size="100000", qvalue=0.05, broad_cutoff=0.1, keep_dup="all", name="test",
                output_dir=root / "output", report=root / "report.json", nomodel_extsize=None,
            )
            with self.assertRaisesRegex(module.ChromatinPeakError, "matched input/control"):
                module.validate_request(arguments)

            arguments.assay = "cutrun"
            arguments.nomodel_extsize = 50
            module.validate_request(arguments)
            command = module.build_command(arguments, "macs3")
            self.assertIn("--nomodel", command)
            self.assertEqual(command[-1], "50")
            self.assertNotIn("-c", command)
            self.assertIn("--call-summits", command)

    def test_bed_validation_rejects_invalid_coordinates(self):
        module = load_template()
        with tempfile.TemporaryDirectory() as temporary:
            invalid = Path(temporary) / "invalid.bed"
            invalid.write_text("chr1\t30\t10\n", encoding="utf-8")
            with self.assertRaisesRegex(module.ChromatinPeakError, "invalid genomic coordinates"):
                module.parse_bed(invalid)

    def test_bedpe_requires_both_ends_and_bam_requires_index(self):
        module = load_template()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bedpe = root / "pairs.bedpe"
            bedpe.write_text("chr1\t10\t30\tchr1\t80\t60\n", encoding="utf-8")
            with self.assertRaisesRegex(module.ChromatinPeakError, "second-end BEDPE"):
                module.validate_input_format(bedpe, "BEDPE")
            bam = root / "sample.bam"
            bam.write_bytes(b"BAM\\x01")
            with self.assertRaisesRegex(module.ChromatinPeakError, "BAI or CSI"):
                module.validate_input_format(bam, "BAM")


if __name__ == "__main__":
    unittest.main()
