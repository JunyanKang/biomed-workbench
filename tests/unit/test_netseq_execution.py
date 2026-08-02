import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from biomed_workbench.implementations.netseq import NetSeqExecutionError, execute_netseq


FAKE_WDL = b'''version 1.0
workflow netseq {
 input { String refFasta = "https://hgdownload.soe.ucsc.edu/goldenPath/sacCer3/bigZips/sacCer3.fa.gz" }
 command { wget --quiet ~{refFasta} -O - | ${unzipFasta} }
 output { String x = "x" }
}
task AlignReads {
        String refFasta
}
'''

FAKE_CROMWELL = r'''#!/usr/bin/env python3
import gzip, json, sys
from pathlib import Path
if '--version' in sys.argv:
    print('cromwell 88')
    raise SystemExit(0)
metadata = Path(sys.argv[sys.argv.index('-m') + 1])
root = metadata.parent.parent / 'outputs'
root.mkdir()
files = {
 'output_bam': ('sample.bam', gzip.compress(b'BAM\x01payload')),
 'bedgraph_pos': ('sample.pos.bedgraph.gz', gzip.compress(b'chrI\t0\t1\t1\n')),
 'bedgraph_neg': ('sample.neg.bedgraph.gz', gzip.compress(b'chrI\t1\t2\t-1\n')),
 'mask_pos': ('sample.mask_pos.bedgraph.gz', gzip.compress(b'')),
 'mask_neg': ('sample.mask_neg.bedgraph.gz', gzip.compress(b'')),
 'alignment_log': ('sample.Log.final.out', b'Number of input reads | 2\nUniquely mapped reads number | 2\n'),
 'fastp_report_html': ('sample.fastp.html', b'<html><body>fastp</body></html>'),
 'fastp_report_json': ('sample.fastp.json', b'{"summary": {"before_filtering": {"total_reads": 2}}}'),
}
outputs = {}
for key, (name, payload) in files.items():
 p = root / name; p.write_bytes(payload); outputs['netseq.' + key] = str(p)
metadata.write_text(json.dumps({'outputs': outputs}))
'''


class NetSeqExecutionTests(unittest.TestCase):
    def test_execute_localizes_reference_and_reloads_outputs(self):
        with tempfile.TemporaryDirectory(prefix="netseq-") as temporary:
            root = Path(temporary)
            cromwell = root / "cromwell"
            cromwell.write_text(FAKE_CROMWELL, encoding="utf-8")
            cromwell.chmod(0o755)
            fastq = root / "sample.fastq"
            fasta = root / "sacCer3.fa"
            fastq.write_text("@r\nACGTACGT\n+\nIIIIIIII\n", encoding="utf-8")
            fasta.write_text(">chrI\nACGTACGT\n", encoding="utf-8")
            digest = hashlib.sha256(fasta.read_bytes()).hexdigest()
            with patch("biomed_workbench.implementations.netseq.UPSTREAM_WDL_SHA256", hashlib.sha256(FAKE_WDL).hexdigest()):
                report = execute_netseq(
                    {
                        "schema_version": 1, "module_id": "bulk-nascent-transcription", "assay": "net-seq",
                        "input_fastq": str(fastq), "reference_fasta": str(fasta), "reference_sha256": digest,
                        "container_image": "rdshear/netseq@sha256:" + "1" * 64,
                        "parameters": {"sample_name": "sample", "genome_name": "sacCer3", "umi_width": 6},
                    },
                    output_dir=root / "run", report_path=root / "report.json", cromwell=str(cromwell),
                    _source_wdl_bytes=FAKE_WDL,
                )
            self.assertTrue(report["passed"])
            self.assertEqual(set(report["outputs"]), {
                "output_bam", "bedgraph_pos", "bedgraph_neg", "mask_pos", "mask_neg",
                "alignment_log", "fastp_report_html", "fastp_report_json",
            })
            derived = (root / "run/provenance/netseq.local-reference.wdl").read_text()
            self.assertEqual(derived.count("File refFasta"), 2)
            self.assertIn("cat ~{refFasta}", derived)
            self.assertTrue(report["reload_validation"]["bam_reloaded"])
            self.assertEqual(report["reload_validation"]["star_input_reads"], 2)

    def test_sra_run_is_forwarded_without_local_fastq(self):
        with tempfile.TemporaryDirectory(prefix="netseq-sra-") as temporary:
            root = Path(temporary)
            cromwell = root / "cromwell"
            cromwell.write_text(FAKE_CROMWELL, encoding="utf-8")
            cromwell.chmod(0o755)
            fasta = root / "sacCer3.fa"
            fasta.write_text(">chrI\nACGTACGT\n", encoding="utf-8")
            digest = hashlib.sha256(fasta.read_bytes()).hexdigest()
            with patch("biomed_workbench.implementations.netseq.UPSTREAM_WDL_SHA256", hashlib.sha256(FAKE_WDL).hexdigest()):
                report = execute_netseq(
                    {
                        "schema_version": 1, "module_id": "bulk-nascent-transcription", "assay": "net-seq",
                        "sra_run_id": "SRR12840066", "reference_fasta": str(fasta), "reference_sha256": digest,
                        "container_image": "rdshear/netseq@sha256:" + "1" * 64,
                        "parameters": {"sample_name": "official", "max_read_count": 10},
                    },
                    output_dir=root / "run", report_path=root / "report.json", cromwell=str(cromwell),
                    _source_wdl_bytes=FAKE_WDL,
                )
            self.assertEqual(report["inputs"]["sra_run_id"], "SRR12840066")
            inputs = json.loads((root / "run/provenance/inputs.json").read_text())
            self.assertEqual(inputs["netseq.sraRunId"], "SRR12840066")
            self.assertNotIn("netseq.inputFastQ", inputs)

    def test_unpinned_container_is_blocked(self):
        with tempfile.TemporaryDirectory(prefix="netseq-invalid-") as temporary:
            root = Path(temporary)
            fastq = root / "sample.fastq"; fastq.write_text("x")
            fasta = root / "ref.fa"; fasta.write_text(">c\nA\n")
            with self.assertRaisesRegex(NetSeqExecutionError, "immutable"):
                execute_netseq(
                    {
                        "schema_version": 1, "module_id": "bulk-nascent-transcription", "assay": "net-seq",
                        "input_fastq": str(fastq), "reference_fasta": str(fasta),
                        "reference_sha256": hashlib.sha256(fasta.read_bytes()).hexdigest(),
                        "container_image": "rdshear/netseq:latest", "parameters": {},
                    },
                    output_dir=root / "run", report_path=root / "report.json",
                )


if __name__ == "__main__":
    unittest.main()
