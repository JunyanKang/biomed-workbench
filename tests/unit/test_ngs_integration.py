import gzip
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.capabilities.ngs_integration import (
    assess_sequencing_readiness,
    ingest_sequencing_run_package,
    inspect_sequencing_inputs,
)


class NGSIntegrationTests(unittest.TestCase):
    def test_packaged_templates_execute_outside_the_repository(self):
        root = Path(__file__).resolve().parents[2]
        module_root = root / "biomed_workbench" / "modules" / "builtin"
        fixture_run = root / "tests" / "fixtures" / "sequencing-run-package"
        cases = {
            "sequencing-input-intake": {
                "script": "run_sequencing_input_intake.py",
                "request": {"paths": [str(root / "README.md")]},
            },
            "sequencing-execution-readiness": {
                "script": "run_sequencing_execution_readiness.py",
                "request": {
                    "assay": "bulk-rna",
                    "tools": [{"name": "python3", "required": True}],
                    "references": [{"role": "annotation", "path": str(root / "README.md"), "required": True}],
                },
            },
            "sequencing-run-package-ingest": {
                "script": "run_sequencing_run_package_ingest.py",
                "request": {"run_directory": str(fixture_run)},
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            working = Path(tmp)
            for module_id, case in cases.items():
                request = working / f"{module_id}.request.json"
                output = working / f"{module_id}.output.json"
                request.write_text(json.dumps(case["request"]), encoding="utf-8")
                script = module_root / module_id / "templates" / case["script"]
                completed = subprocess.run(
                    [sys.executable, str(script), str(request), str(output)],
                    cwd=working,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                result = json.loads(output.read_text(encoding="utf-8"))
                self.assertEqual(result["module_id"], module_id)
                self.assertTrue(result["quality_review_required"])

    def test_intake_inspects_fastq_pair_and_sample_sheet(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reads = []
            for mate in (1, 2):
                path = root / f"donorA_R{mate}.fastq.gz"
                with gzip.open(path, "wt") as handle:
                    handle.write(f"@read/{mate}\nACGT\n+\nIIII\n")
                reads.append(str(path))
            sheet = root / "samples.csv"
            sheet.write_text("sample,condition\ndonorA,treated\n", encoding="utf-8")
            result = inspect_sequencing_inputs(reads, "bulk-rna", str(sheet))
        self.assertTrue(result["admissible_for_planning"])
        self.assertEqual(result["type_counts"], {"fastq": 2})
        self.assertEqual(result["incomplete_fastq_pairs"], [])
        self.assertIn("count-level inference", result["route_candidates"][1])

    def test_readiness_keeps_tools_and_references_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            fasta = Path(tmp) / "genome.fa"
            fasta.write_text(">chr1\nACGT\n", encoding="utf-8")
            result = assess_sequencing_readiness(
                "atac",
                tools=[{"name": "definitely-not-installed-biomed-tool", "required": True}],
                references=[{"role": "genome_fasta", "path": str(fasta), "required": True}],
            )
        self.assertFalse(result["tool_readiness"])
        self.assertTrue(result["reference_readiness"])
        self.assertFalse(result["ready_to_execute"])

    def test_completed_run_package_is_reloaded_and_hashed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result_file = root / "results" / "counts.tsv"
            result_file.parent.mkdir()
            result_file.write_text("gene\ts1\nA\t3\n", encoding="utf-8")
            import hashlib
            digest = hashlib.sha256(result_file.read_bytes()).hexdigest()
            (root / "manifest.json").write_text(json.dumps({
                "status": "completed", "workflow": {"name": "example", "version": "1"},
                "environment": {"identity": "sha256:environment"},
            }), encoding="utf-8")
            (root / "artifact_index.json").write_text(json.dumps({"artifacts": [{
                "path": "results/counts.tsv", "sha256": digest, "role": "counts",
            }]}), encoding="utf-8")
            result = ingest_sequencing_run_package(str(root))
        self.assertTrue(result["accepted"])
        self.assertEqual(result["artifacts"][0]["sha256"], digest)

    def test_prepared_run_package_is_not_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "manifest.json").write_text(json.dumps({"status": "prepared"}), encoding="utf-8")
            (root / "artifact_index.json").write_text(json.dumps({"artifacts": []}), encoding="utf-8")
            result = ingest_sequencing_run_package(str(root))
        self.assertFalse(result["accepted"])


if __name__ == "__main__":
    unittest.main()
