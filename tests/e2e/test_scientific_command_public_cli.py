import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FASTQ = ROOT / "tests" / "fixtures" / "sequencing" / "read-qc-balanced.fastq"


class ScientificCommandPublicCliTests(unittest.TestCase):
    def test_fastqc_public_cli_binds_project_artifact_and_returns_content_addressed_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tools = root / "bin"
            tools.mkdir()
            fastqc = tools / "fastqc"
            fastqc.write_text(
                """#!/usr/bin/env python3
import pathlib, sys, zipfile
if '--version' in sys.argv:
    print('FastQC v0.12.1')
    raise SystemExit(0)
outdir = pathlib.Path(sys.argv[sys.argv.index('--outdir') + 1])
source = pathlib.Path(sys.argv[-1])
stem = source.name.rsplit('.', 1)[0]
with zipfile.ZipFile(outdir / f'{stem}_fastqc.zip', 'w') as archive:
    archive.writestr('summary.txt', 'PASS\\tBasic Statistics\\treads.fastq\\n')
(outdir / f'{stem}_fastqc.html').write_text('<html><body>FastQC Report</body></html>')
""",
                encoding="utf-8",
            )
            fastqc.chmod(0o755)
            java = tools / "java"
            java.write_text("#!/bin/sh\nprintf '%s\\n' 'java version \"22\"' >&2\n", encoding="utf-8")
            java.chmod(0o755)
            bindings = {
                "project_context": {
                    "project_id": "fastqc-public-fixture",
                    "objective": "Execute FastQC through the strict public project entry and retain its outputs.",
                    "scientific_question": "Do the registered sequencing reads satisfy the declared technical quality contract?",
                    "species": ["human"],
                    "biological_scope": {"assay": "rna-seq", "sample-id": "sample-1"},
                    "study_design": "technical-qc",
                    "experimental_unit": "sample",
                    "comparisons": [
                        {
                            "id": "technical-check",
                            "numerator_group": "observed",
                            "denominator_group": "declared",
                            "covariates": [],
                        }
                    ],
                    "constraints": [],
                    "required_deliverables": ["quality-report"],
                    "required_evidence_types": ["technical-quality"],
                    "privacy_level": "public",
                },
                "hypotheses": [
                    {
                        "id": "hypothesis-fastqc-technical-quality",
                        "statement": "The registered sequencing reads satisfy the prespecified technical quality criteria for downstream analysis.",
                        "biological_scope": {"species": "human", "assay": "rna-seq"},
                        "experimental_unit": "sample",
                        "comparison_id": "technical-check",
                        "expected_direction": "no-change",
                        "expected_observations": ["FastQC reports no blocking failure for the registered read file."],
                        "disconfirming_observations": ["FastQC identifies a blocking failure in the registered read file."],
                        "alternative_explanations": ["The small validation fixture may not represent a production sequencing library."],
                        "required_evidence_types": ["technical-quality"],
                        "minimum_independent_evidence_groups": 1,
                        "permitted_claim_strength": "descriptive",
                        "status": "active",
                        "supporting_evidence_ids": [],
                        "conflicting_evidence_ids": [],
                        "missing_evidence_types": ["technical-quality"],
                        "parent_hypothesis_id": None,
                        "revision": 1,
                    }
                ],
                "analysis_admission": {
                    "rationale_zh": "在任何下游分析之前，对登记的测序读段执行独立质量检查。",
                    "rationale_en": "Run an independent read-quality assessment before any downstream scientific analysis.",
                    "method": "FastQC version 0.12.1 with the declared Java runtime and exact FASTQ compatibility row.",
                    "official_sources": ["https://www.bioinformatics.babraham.ac.uk/projects/fastqc/"],
                    "alternatives_considered": ["Retain raw read statistics without FastQC as a nonpreferred diagnostic alternative."],
                    "assumptions": ["The registered FASTQ payload belongs to the declared sample and quality encoding."],
                    "parameter_justifications": {"threads": "One thread is sufficient for this bounded public validation fixture."},
                    "acceptance_criteria": ["The command exits successfully and its HTML and archive outputs are reloaded."],
                    "falsification_criteria": ["A command failure or missing declared output invalidates this technical assessment."],
                    "approved": True,
                },
                "artifacts": {
                    "reads": {
                        "artifact_id": "artifact-fastqc-public-input",
                        "format_name": "fastq",
                        "format_version": "sanger-phred33",
                        "compression": "none",
                        "orientation": "single-end",
                        "indexes": [],
                        "scientific_scope": {
                            "species": ["human"],
                            "sample-id": "sample-1",
                            "read-layout": "single-end",
                            "quality-encoding": "sanger-phred33",
                        },
                        "denominator": "one-registered-sample",
                        "processing_level": "raw",
                        "quality_status": "passed",
                        "representation": "text",
                        "sample_manifest_digest": "0" * 64,
                        "content": {},
                        "payload_files": [
                            {"role": "reads", "path": str(FASTQ), "media_type": "application/fastq"}
                        ],
                    }
                },
            }
            binding_path = root / "bindings.json"
            binding_path.write_text(json.dumps(bindings), encoding="utf-8")
            environment = {**os.environ, "PATH": str(tools) + os.pathsep + os.environ.get("PATH", "")}
            completed = subprocess.run(
                [
                    sys.executable,
                    "tools/run_tool.py",
                    "read-quality-fastqc",
                    "--input",
                    '{"threads":1}',
                    "--project-root",
                    str(root),
                    "--artifact-bindings",
                    str(binding_path),
                    "--compatibility-row",
                    "fastqc-0.12.1-java-22-fastq-sanger",
                ],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertEqual(result["status"], "completed", result)
            self.assertEqual(result["stop_reason"], "awaiting_artifact_review")
            self.assertEqual(len(result["output_artifacts"]), 1)
            payloads = result["output_artifacts"][0]["payloads"]
            self.assertEqual({item["role"] for item in payloads}, {"archive", "report"})
            self.assertTrue(all(item["object_key"].startswith("sha256/") for item in payloads))
            self.assertNotIn(str(root), completed.stdout)

    def test_command_without_project_bindings_returns_specific_error(self):
        completed = subprocess.run(
            [sys.executable, "tools/run_tool.py", "read-quality-fastqc", "--input", '{"threads":1}'],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 2)
        error = json.loads(completed.stderr)
        self.assertEqual(error["code"], "INPUT_ARTIFACT_REQUIRED")
        self.assertNotIn("TypeError", completed.stderr)


if __name__ == "__main__":
    unittest.main()
