import json
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.implementations.rlpipes import RLPipesExecutionError, execute_rlpipes


FAKE_RLPIPES = r'''#!/usr/bin/env python3
import sys
from pathlib import Path
if '--version' in sys.argv:
    print('RLPipes, version 0.9.3')
    raise SystemExit(0)
stage = sys.argv[1]
run_dir = Path(sys.argv[-2] if stage == 'build' else sys.argv[-1])
if stage == 'build':
    run_dir.mkdir()
    (run_dir / 'config.json').write_text('{}')
elif stage == 'run':
    for part in ('coverage', 'peaks', 'bam/sample', 'rlseq_report'):
        (run_dir / part).mkdir(parents=True, exist_ok=True)
    (run_dir / 'coverage/sample_hg38.bw').write_bytes(b'\x26\xfc\x8f\x88payload')
    (run_dir / 'peaks/sample_hg38.broadPeak').write_text('chr1\t1\t10\tpeak\t1\t.\n')
    (run_dir / 'bam/sample/sample_hg38.bam').write_bytes(b'BAM-data')
    (run_dir / 'rlseq_report/sample_hg38.html').write_text('<!doctype html><html></html>')
'''


class RLPipesExecutionTests(unittest.TestCase):
    def test_execute_build_check_run_and_reload(self):
        with tempfile.TemporaryDirectory(prefix="rlpipes-") as temporary:
            root = Path(temporary)
            executable = root / "RLPipes"
            executable.write_text(FAKE_RLPIPES, encoding="utf-8")
            executable.chmod(0o755)
            fastq = root / "sample.fastq"
            fastq.write_text("@r\nACGT\n+\nIIII\n", encoding="utf-8")
            samples = root / "samples.csv"
            samples.write_text(f"experiment\n{fastq}\n", encoding="utf-8")
            report = execute_rlpipes(
                {
                    "schema_version": 1, "module_id": "bulk-r-loop-mapping", "assay": "qdrip-seq",
                    "samples_csv": str(samples), "genome": "hg38", "parameters": {"threads": 2},
                },
                output_dir=root / "out", report_path=root / "report.json", executable=str(executable),
            )
            self.assertTrue(report["passed"])
            self.assertEqual(report["workflow"]["mode"], "qDRIP")
            self.assertEqual(len(report["outputs"]["coverage"]), 1)
            self.assertEqual(json.loads((root / "report.json").read_text())["workflow"]["commit"], "b1f864e52c48e164c059b40afc450a5726c147e7")

    def test_public_accession_is_blocked_by_default(self):
        with tempfile.TemporaryDirectory(prefix="rlpipes-public-") as temporary:
            root = Path(temporary)
            samples = root / "samples.csv"
            samples.write_text("experiment\nSRX113812\n", encoding="utf-8")
            with self.assertRaisesRegex(RLPipesExecutionError, "public accessions"):
                execute_rlpipes(
                    {
                        "schema_version": 1, "module_id": "bulk-r-loop-mapping", "assay": "drip-seq",
                        "samples_csv": str(samples), "genome": "hg38", "parameters": {},
                    },
                    output_dir=root / "out", report_path=root / "report.json", executable="missing",
                )


if __name__ == "__main__":
    unittest.main()
