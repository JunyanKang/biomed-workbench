import json
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.implementations.laceseq import (
    LaceSeqExecutionError,
    execute_laceseq,
    read_bed6,
    subtract_intervals,
)


class LaceSeqExecutionTests(unittest.TestCase):
    def test_control_overlap_excludes_the_whole_read_like_upstream(self):
        with tempfile.TemporaryDirectory(prefix="lace-subtract-") as temporary:
            path = Path(temporary) / "reads.bed"
            path.write_text("chr1\t10\t30\tr1\t1\t+\n", encoding="utf-8")
            remaining = subtract_intervals(read_bed6(path), [("chr1", 15, 20)])
            self.assertEqual(remaining, [])

    def test_reads_are_deduplicated_by_coordinate_and_strand(self):
        with tempfile.TemporaryDirectory(prefix="lace-deduplicate-") as temporary:
            path = Path(temporary) / "reads.bed"
            path.write_text(
                "chr1\t10\t30\tr1\t1\t+\n"
                "chr1\t10\t30\tr2\t2\t+\n"
                "chr1\t10\t30\tr3\t3\t-\n",
                encoding="utf-8",
            )
            reads = read_bed6(path)
            self.assertEqual(len(reads), 2)
            self.assertEqual([row.name for row in reads], ["r1", "r3"])

    def test_execute_calls_stranded_clusters_and_reloads_outputs(self):
        with tempfile.TemporaryDirectory(prefix="lace-execute-") as temporary:
            root = Path(temporary)
            experiment = root / "lace.bed"
            control = root / "igg.bed"
            experiment.write_text(
                "chr1\t100\t120\tr1\t1\t+\n"
                "chr1\t105\t125\tr2\t1\t+\n"
                "chr1\t110\t130\tr3\t1\t-\n"
                "chr1\t500\t520\tr4\t1\t-\n",
                encoding="utf-8",
            )
            control.write_text("chr1\t500\t520\tc1\t1\t+\n", encoding="utf-8")
            request = {
                "schema_version": 1,
                "module_id": "bulk-rbp-rna-binding",
                "assay": "lace-seq",
                "experiment_bed": str(experiment),
                "control_bed": str(control),
                "parameters": {"merge_distance": 10, "initial_rpm": 0, "min_strand_reads": 2},
            }
            report = execute_laceseq(request, output_dir=root / "out", report_path=root / "report.json")
            self.assertTrue(report["passed"])
            self.assertEqual(report["metrics"]["retained_clusters"], 1)
            self.assertEqual(report["outputs"]["clusters_tsv"]["rows"], 1)
            cluster = (root / "out/lace_clusters.tsv").read_text(encoding="utf-8").splitlines()[1].split("\t")
            self.assertEqual(cluster[4], "-")
            self.assertEqual(json.loads((root / "report.json").read_text())["method"]["upstream_commit"], "b8d1193638190c50c8553847ad3a1653544dbe14")

    def test_unknown_parameter_is_blocked(self):
        with tempfile.TemporaryDirectory(prefix="lace-invalid-") as temporary:
            root = Path(temporary)
            for name in ("lace.bed", "igg.bed"):
                (root / name).write_text("chr1\t1\t2\tr\t1\t+\n", encoding="utf-8")
            with self.assertRaisesRegex(LaceSeqExecutionError, "unknown"):
                execute_laceseq(
                    {
                        "schema_version": 1,
                        "module_id": "bulk-rbp-rna-binding",
                        "assay": "lace-seq",
                        "experiment_bed": str(root / "lace.bed"),
                        "control_bed": str(root / "igg.bed"),
                        "parameters": {"invented": True},
                    },
                    output_dir=root / "out",
                    report_path=root / "report.json",
                )


if __name__ == "__main__":
    unittest.main()
