import json
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.implementations.exomepeak2 import ExomePeak2ExecutionError, execute_exomepeak2


FAKE_RSCRIPT = r'''#!/usr/bin/env python3
import sys
from pathlib import Path
out = Path(sys.argv[-2])
out.mkdir(parents=True)
(out / 'exomePeak2_version.txt').write_text(sys.argv[-1] + '\n')
result = out / 'exomePeak2_output'; result.mkdir()
(result / 'peaks.bed').write_text('chr1\t1\t20\n')
(result / 'peaks.csv').write_text('chrom,start,end\nchr1,1,20\n')
(out / 'exomePeak2_result.rds').write_bytes(b'RDS-data')
'''


class ExomePeak2ExecutionTests(unittest.TestCase):
    def _inputs(self, root: Path):
        bam_paths = []
        for name in ("ip", "input"):
            bam = root / f"{name}.bam"; bam.write_bytes(b"bam")
            Path(str(bam) + ".bai").write_bytes(b"index")
            bam_paths.append(bam)
        gff = root / "genes.gtf"; gff.write_text('chr1\tt\texon\t1\t20\t.\t+\t.\tgene_id "g";\n')
        return bam_paths, gff

    def test_executes_official_api_and_reloads_outputs(self):
        with tempfile.TemporaryDirectory(prefix="exomepeak2-") as temporary:
            root = Path(temporary)
            executable = root / "Rscript"; executable.write_text(FAKE_RSCRIPT); executable.chmod(0o755)
            (ip, input_bam), gff = self._inputs(root)
            report = execute_exomepeak2(
                {
                    "schema_version": 1, "module_id": "bulk-rna-modification-enrichment", "assay": "m6a-seq",
                    "control_ip_bams": [str(ip)], "control_input_bams": [str(input_bam)], "gff": str(gff),
                    "parameters": {"test_method": "Poisson", "mode": "exon"},
                },
                output_dir=root / "run", report_path=root / "report.json", rscript=str(executable),
            )
            self.assertTrue(report["passed"])
            self.assertEqual(report["workflow"]["version"], "1.14.3")
            self.assertEqual(len(report["outputs"]["bed"]), 1)

    def test_unindexed_bam_is_blocked(self):
        with tempfile.TemporaryDirectory(prefix="exomepeak2-invalid-") as temporary:
            root = Path(temporary)
            bam = root / "ip.bam"; bam.write_bytes(b"bam")
            gff = root / "genes.gtf"; gff.write_text("x")
            with self.assertRaisesRegex(ExomePeak2ExecutionError, "indexed BAM"):
                execute_exomepeak2(
                    {
                        "schema_version": 1, "module_id": "bulk-rna-modification-enrichment", "assay": "merip-seq",
                        "control_ip_bams": [str(bam)], "control_input_bams": [str(bam)], "gff": str(gff), "parameters": {},
                    },
                    output_dir=root / "run", report_path=root / "report.json",
                )


if __name__ == "__main__":
    unittest.main()
