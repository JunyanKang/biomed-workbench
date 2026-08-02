import gzip
import json
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.implementations.laceseq_fastq import (
    LaceSeqFastqExecutionError,
    execute_laceseq_fastq,
)


FAKE_CUTADAPT = r'''#!/usr/bin/env python3
import shutil, sys
if '--version' in sys.argv:
 print('1.15'); raise SystemExit(0)
out = sys.argv[sys.argv.index('-o') + 1]
shutil.copyfile(sys.argv[-1], out)
'''

FAKE_BOWTIE = r'''#!/usr/bin/env python3
import gzip, shutil, sys
if '--version' in sys.argv:
 print('bowtie version 1.2.3'); raise SystemExit(0)
if '--un' in sys.argv:
 out = sys.argv[sys.argv.index('--un') + 1]
 with gzip.open(sys.argv[-2], 'rt') as src, open(out, 'w') as dst: shutil.copyfileobj(src, dst)
 sam = sys.argv[-1]
 open(sam, 'w').write('@HD\tVN:1.0\n')
else:
 sam = sys.argv[-1]
 start = 101 if 'experiment' in sys.argv[-2] else 501
 with open(sam, 'w') as out:
  out.write('@HD\tVN:1.0\n')
  for i in range(25): out.write(f'r{i}\t0\tchr1\t{start+i}\t30\t20M\t*\t0\t0\tAAAAAAAAAAAAAAAAAAAA\tIIIIIIIIIIIIIIIIIIII\n')
'''


class LaceSeqFastqExecutionTests(unittest.TestCase):
    @staticmethod
    def _inputs(root: Path) -> dict:
        for label in ("experiment", "control"):
            with gzip.open(root / f"{label}.fastq.gz", "wt") as handle:
                handle.write("@r\nAAAAAAAAAAAAAAAAAAAA\n+\nIIIIIIIIIIIIIIIIIIII\n")
        for prefix in (root / "rrna", root / "genome"):
            for suffix in (".1.ebwt", ".2.ebwt", ".3.ebwt", ".4.ebwt", ".rev.1.ebwt", ".rev.2.ebwt"):
                Path(str(prefix) + suffix).write_bytes(b"index")
        (root / "rrna.fa").write_text(">rrna\nAAAAAAAAAAAAAAAAAAAA\n", encoding="utf-8")
        (root / "genome.fa").write_text(">chr1\nAAAAAAAAAAAAAAAAAAAA\n", encoding="utf-8")
        return {
            "schema_version": 1, "module_id": "bulk-rbp-rna-binding", "assay": "lace-seq",
            "experiment_fastq": str(root / "experiment.fastq.gz"),
            "control_fastq": str(root / "control.fastq.gz"),
            "rrna_bowtie_index": str(root / "rrna"), "genome_bowtie_index": str(root / "genome"),
            "reference_metadata": {
                "rrna_fasta": str(root / "rrna.fa"), "rrna_name": "test-rRNA",
                "rrna_source_url": "https://example.test/rrna.fa",
                "genome_fasta": str(root / "genome.fa"), "genome_build": "test",
                "genome_scope": "chr1",
                "genome_source_url": "https://example.test/genome.fa",
            },
            "parameters": {"min_strand_reads": 20},
        }

    def test_raw_fastq_path_runs_and_reloads_clusters(self):
        with tempfile.TemporaryDirectory(prefix="laceseq-fastq-") as temporary:
            root = Path(temporary)
            cutadapt = root / "cutadapt"; cutadapt.write_text(FAKE_CUTADAPT); cutadapt.chmod(0o755)
            bowtie = root / "bowtie"; bowtie.write_text(FAKE_BOWTIE); bowtie.chmod(0o755)
            report = execute_laceseq_fastq(
                self._inputs(root),
                output_dir=root / "run", report_path=root / "report.json",
                cutadapt=str(cutadapt), bowtie=str(bowtie),
            )
            self.assertTrue(report["passed"])
            self.assertEqual(report["clusters"]["retained_clusters"], 1)
            self.assertEqual(json.loads((root / "report.json").read_text())["preprocessing"]["experiment"]["mapped_bed_rows"], 25)

    def test_container_runtime_requires_immutable_images(self):
        with tempfile.TemporaryDirectory(prefix="laceseq-container-contract-") as temporary:
            root = Path(temporary)
            request = self._inputs(root)
            request["runtime"] = {
                "mode": "containers", "platform": "linux/amd64",
                "cutadapt_image": "quay.io/biocontainers/cutadapt:1.15--py36_0",
                "bowtie_image": "quay.io/biocontainers/bowtie:1.2.3--py37h9a982cc_2",
            }
            with self.assertRaisesRegex(LaceSeqFastqExecutionError, "immutable image"):
                execute_laceseq_fastq(
                    request, output_dir=root / "run", report_path=root / "report.json"
                )


if __name__ == "__main__":
    unittest.main()
