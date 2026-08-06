import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.kernel.state import ProjectState


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
            self.assertEqual(result["execution_status"], "completed", result)
            self.assertEqual(result["scientific_status"], "awaiting_review", result)
            self.assertEqual(result["stop_reason"], "awaiting_artifact_review")
            state_path = root / result["project_state_path"]
            self.assertTrue(state_path.is_file())
            persisted = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["state_digest"], result["project_state_digest"])
            self.assertEqual(len(persisted["observed_executions"]), 1)
            self.assertEqual(len(persisted["artifact_reloads"]), 1)
            self.assertEqual(len(persisted["execution_reviews"]), 1)
            self.assertEqual(len(result["output_artifacts"]), 1)
            payloads = result["output_artifacts"][0]["payloads"]
            self.assertEqual({item["role"] for item in payloads}, {"archive", "report"})
            self.assertTrue(all(item["object_key"].startswith("sha256/") for item in payloads))
            self.assertNotIn(str(root), completed.stdout)

            artifact_id = result["output_artifacts"][0]["id"]
            review = {
                "id": "review-fastqc-public-output",
                "artifact_id": artifact_id,
                "artifact_kind": "data",
                "rationale_zh": "依据预先登记的技术质量标准复核 FastQC 输出及其完整来源链。",
                "rationale_en": "Review the FastQC output and its complete provenance chain against the preregistered technical criteria.",
                "methods_zh": "重新读取内容寻址的报告和压缩归档，并核对命令、版本、输入身份与输出摘要。",
                "methods_en": "Reload the content-addressed report and archive and verify command, versions, input identity, and output digests.",
                "results_zh": "登记的两类输出均已重新读取，执行回执和内容摘要一致，未发现阻断性技术问题。",
                "results_en": "Both declared outputs were reloaded and their execution receipts and content digests agree without a blocking technical issue.",
                "conclusion_zh": "该小型夹具的 FastQC 技术结果可以带局限保留，用于验证完整项目状态闭环。",
                "conclusion_en": "The fixture's FastQC technical result may be retained with limitations to validate the complete project-state loop.",
                "panels": [],
                "technical_status": "passed",
                "statistical_status": "warning",
                "biological_status": "warning",
                "robustness_status": "warning",
                "limitations_zh": ["该小型夹具不代表生产测序文库，也不支持生物学效应结论。"],
                "limitations_en": ["This small fixture is not a production sequencing library and supports no biological-effect claim."],
                "recommended_action": "retain-with-caveat",
                "source_urls": ["https://www.bioinformatics.babraham.ac.uk/projects/fastqc/"],
            }
            review_path = root / "review.json"
            review_path.write_text(json.dumps(review), encoding="utf-8")
            reviewed = subprocess.run(
                [sys.executable, "tools/project_workflow.py", "review", "--state", str(state_path), "--input", str(review_path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(reviewed.returncode, 0, reviewed.stderr)

            revision_request = {
                "source_artifact_id": artifact_id,
                "action": "rerun-adjusted-parameters",
                "target_module_id": None,
                "parameter_overrides": {"threads": 2},
                "rationale": "Repeat the bounded technical check with a changed thread parameter to validate review-triggered revision reachability.",
            }
            revision_path = root / "revision.json"
            revision_path.write_text(json.dumps(revision_request), encoding="utf-8")
            prepared = subprocess.run(
                [sys.executable, "tools/project_workflow.py", "prepare-revision", "--state", str(state_path), "--input", str(revision_path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            prepared_state = ProjectState.from_dict(json.loads(state_path.read_text(encoding="utf-8")))
            active_plan = next(item for item in prepared_state.plans if item.id == prepared_state.active_plan_id)
            replacement = next(item for item in active_plan.nodes if item.revision_of_node_id is not None)
            self.assertEqual(dict(replacement.parameter_overrides), {"threads": 2})
            self.assertIsNotNone(replacement.revision_contract)

            decision = {
                "id": "decision-fastqc-public-rerun",
                "review_id": review["id"],
                "artifact_id": artifact_id,
                "hypothesis_ids": ["hypothesis-fastqc-technical-quality"],
                "action": "rerun-adjusted-parameters",
                "rationale_zh": "为验证参数化修订链，使用登记的不同线程参数重新执行同一技术检查。",
                "rationale_en": "Re-execute the same technical check with the registered changed thread parameter to validate the parameterized revision chain.",
                "active_evidence": False,
                "next_plan_node_ids": [replacement.id],
                "revision_contract_id": replacement.revision_contract.id,
            }
            decision_path = root / "decision.json"
            decision_path.write_text(json.dumps(decision), encoding="utf-8")
            decided = subprocess.run(
                [sys.executable, "tools/project_workflow.py", "decide", "--state", str(state_path), "--input", str(decision_path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(decided.returncode, 0, decided.stderr)
            revised_admission = prepared_state.analysis_admissions[0].to_dict()
            revised_admission.update({
                "id": "admission-fastqc-public-rerun",
                "plan_node_id": replacement.id,
                "parameter_justifications": {
                    "threads": "Two threads deliberately differ from the reviewed source request and remain inside the registered module range."
                },
            })
            revised_admission_path = root / "revised-admission.json"
            revised_admission_path.write_text(json.dumps(revised_admission), encoding="utf-8")
            admitted_revision = subprocess.run(
                [sys.executable, "tools/project_workflow.py", "admit", "--state", str(state_path), "--input", str(revised_admission_path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(admitted_revision.returncode, 0, admitted_revision.stderr)
            resumed = subprocess.run(
                [sys.executable, "tools/project_workflow.py", "resume", "--state", str(state_path), "--project-root", str(root)],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            rerun_result = json.loads(resumed.stdout)
            self.assertEqual(rerun_result["stop_reason"], "awaiting_artifact_review", rerun_result)
            revised_state = ProjectState.from_dict(json.loads(state_path.read_text(encoding="utf-8")))
            revised_artifact_id = replacement.planned_output_artifact_ids["read_quality_report"]
            self.assertIn(revised_artifact_id, {item.id for item in revised_state.artifacts})
            revised_execution = next(item for item in revised_state.observed_executions if item.plan_node_id == replacement.id)
            self.assertEqual(revised_execution.parameters_digest, replacement.planned_request_digest)

            revised_review = {
                **review,
                "id": "review-fastqc-revised-output",
                "artifact_id": revised_artifact_id,
            }
            revised_decision = {
                "id": "decision-fastqc-revised-output",
                "review_id": revised_review["id"],
                "artifact_id": revised_artifact_id,
                "hypothesis_ids": ["hypothesis-fastqc-technical-quality"],
                "action": "retain-with-caveat",
                "rationale_zh": "修订执行与重载链完整且技术评审通过，因此在声明夹具局限后保留。",
                "rationale_en": "The revised execution and reload chain is complete and technical review passed, so retain it with the fixture limitation.",
                "active_evidence": True,
                "next_plan_node_ids": [],
            }
            revised_review_path = root / "revised-review.json"
            revised_decision_path = root / "revised-decision.json"
            revised_review_path.write_text(json.dumps(revised_review), encoding="utf-8")
            revised_decision_path.write_text(json.dumps(revised_decision), encoding="utf-8")
            for command, input_path in (("review", revised_review_path), ("decide", revised_decision_path)):
                appended = subprocess.run(
                    [sys.executable, "tools/project_workflow.py", command, "--state", str(state_path), "--input", str(input_path)],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(appended.returncode, 0, appended.stderr)
            completed_revision = subprocess.run(
                [sys.executable, "tools/project_workflow.py", "resume", "--state", str(state_path), "--project-root", str(root)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed_revision.returncode, 0, completed_revision.stderr)
            self.assertEqual(json.loads(completed_revision.stdout)["stop_reason"], "plan_completed")
            appended_run = subprocess.run(
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
            self.assertEqual(appended_run.returncode, 0, appended_run.stderr)
            appended_result = json.loads(appended_run.stdout)
            self.assertEqual(appended_result["scientific_status"], "awaiting_review")
            self.assertNotEqual(appended_result["output_artifacts"][0]["id"], artifact_id)

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
