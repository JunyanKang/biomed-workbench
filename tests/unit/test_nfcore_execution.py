import gzip
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from biomed_workbench.implementations.nfcore import (
    CLIPSEQ,
    HIC,
    METHYLSEQ,
    NASCENT,
    RIBOSEQ,
    NfCoreExecutionError,
    _build_command,
    _prepare_runtime_compatibility,
    _validate_request,
    execute_nfcore,
    schema_parameters,
    validate_pipeline_parameters,
)


def schema(*names: str) -> dict:
    properties = {
        name: {
            "type": (
                "boolean"
                if name.startswith("skip_") or name in {"rrbs", "em_seq"}
                else "string"
            )
        }
        for name in names
    }
    return {"$defs": {"options": {"type": "object", "properties": properties}}}


FAKE_NEXTFLOW = r"""#!/usr/bin/env python3
import json
import sys
from pathlib import Path

if "-version" in sys.argv:
    print("N E X T F L O W  ~  version 25.04.8")
    raise SystemExit(0)
params_path = Path(sys.argv[sys.argv.index("-params-file") + 1])
params = json.loads(params_path.read_text(encoding="utf-8"))
outdir = Path(params["outdir"])
(outdir / "pipeline_info").mkdir(parents=True)
(outdir / "pipeline_info" / "software_versions.yml").write_text("nextflow: 25.04.8\n", encoding="utf-8")
pipeline = sys.argv[sys.argv.index("run") + 1]
if pipeline == "nf-core/riboseq":
    (outdir / "multiqc" / "star").mkdir(parents=True)
    (outdir / "multiqc" / "star" / "multiqc_report.html").write_text("<!doctype html><html></html>", encoding="utf-8")
    (outdir / "riboseq_qc" / "ribotish").mkdir(parents=True)
    (outdir / "riboseq_qc" / "ribotish" / "sample_qual.txt").write_text("metric\tvalue\nperiodicity\t0.80\n", encoding="utf-8")
    (outdir / "orf_predictions" / "ribotish").mkdir(parents=True)
    (outdir / "orf_predictions" / "ribotish" / "sample_pred.txt").write_text("ORF\tstatus\norf1\ttranslated\n", encoding="utf-8")
elif pipeline == "nf-core/nascent":
    (outdir / "multiqc").mkdir(parents=True)
    (outdir / "multiqc" / "multiqc_report.html").write_text("<!doctype html><html></html>", encoding="utf-8")
    (outdir / "coverage_graphs").mkdir(parents=True)
    (outdir / "coverage_graphs" / "sample.plus.bigWig").write_bytes(b"\x26\xfc\x8f\x88payload")
    (outdir / "quantification" / "gene").mkdir(parents=True)
    (outdir / "quantification" / "gene" / "sample.featureCounts.txt").write_text("gene\tcount\nA\t2\n", encoding="utf-8")
    (outdir / "quantification" / "nascent").mkdir(parents=True)
    (outdir / "quantification" / "nascent" / "sample.featureCounts.txt").write_text("transcript\tcount\nTU1\t2\n", encoding="utf-8")
elif pipeline == "nf-core/clipseq":
    import gzip
    (outdir / "multiqc").mkdir(parents=True)
    (outdir / "multiqc" / "sample_multiqc_report.html").write_text("<!doctype html><html></html>", encoding="utf-8")
    (outdir / "xlinks").mkdir(parents=True)
    with gzip.open(outdir / "xlinks" / "sample.xl.bed.gz", "wt", encoding="utf-8") as handle:
        handle.write("chr1\t1\t2\t.\t3\t+\n")
    (outdir / "clipqc").mkdir(parents=True)
    (outdir / "clipqc" / "sample.tsv").write_text("metric\tvalue\ncrosslinks\t3\n", encoding="utf-8")
elif pipeline == "nf-core/methylseq":
    (outdir / "multiqc" / "bismark").mkdir(parents=True)
    (outdir / "multiqc" / "bismark" / "multiqc_report.html").write_text("<!doctype html><html></html>", encoding="utf-8")
    (outdir / "bismark" / "methylation_calls" / "bedGraph").mkdir(parents=True)
    (outdir / "bismark" / "methylation_calls" / "bedGraph" / "sample.bedGraph").write_text("chr1\t1\t2\t50\n", encoding="utf-8")
    (outdir / "bismark" / "methylation_calls" / "mbias").mkdir(parents=True)
    (outdir / "bismark" / "methylation_calls" / "mbias" / "sample.M-bias.txt").write_text("position\tmethylated\n1\t5\n", encoding="utf-8")
elif pipeline == "nf-core/hic":
    (outdir / "multiqc").mkdir(parents=True)
    (outdir / "multiqc" / "multiqc_report.html").write_text("<!doctype html><html></html>", encoding="utf-8")
    (outdir / "hicpro" / "valid_pairs" / "sample").mkdir(parents=True)
    (outdir / "hicpro" / "valid_pairs" / "sample" / "sample.validPairs").write_text("read1\tchr1\t1\t+\tchr1\t10\t-\n", encoding="utf-8")
    (outdir / "contact_maps" / "cool").mkdir(parents=True)
    (outdir / "contact_maps" / "cool" / "sample.cool").write_bytes(b"HDF5-contact-map")
print("fake workflow complete")
"""


class NfCoreExecutionTests(unittest.TestCase):
    def test_relative_destinations_are_resolved_before_nextflow_changes_cwd(self):
        with tempfile.TemporaryDirectory(prefix="nfcore-relative-") as temporary:
            root = Path(temporary)
            nextflow = root / "nextflow"
            nextflow.write_text(FAKE_NEXTFLOW, encoding="utf-8")
            nextflow.chmod(0o755)
            docker = root / "docker"
            docker.write_text("#!/bin/sh\necho '26.1.4'\n", encoding="utf-8")
            docker.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{root}:{old_path}"
            input_fastq = root / "reads.fastq.gz"
            with gzip.open(input_fastq, "wt", encoding="utf-8") as handle:
                handle.write("@r\nACGT\n+\nIIII\n")
            samples = root / "samples.csv"
            samples.write_text(f"sample,fastq_1,fastq_2\ns1,{input_fastq},\n", encoding="utf-8")
            request = {
                "schema_version": 1,
                "module_id": NASCENT.module_id,
                "assay": "gro-seq",
                "engine_profile": "docker",
                "official_test_profile": False,
                "resume": False,
                "pipeline_params": {"input": str(samples), "assay_type": "GROseq"},
            }
            old = os.getcwd()
            os.chdir(root)
            try:
                with patch("biomed_workbench.implementations.nfcore.validate_host_execution_path"):
                    report = execute_nfcore(
                        request,
                        spec=NASCENT,
                        output_dir=Path("relative-run"),
                        report_path=Path("relative-report.json"),
                        nextflow=str(nextflow),
                        schema=schema("input", "assay_type", "outdir"),
                    )
            finally:
                os.chdir(old)
                os.environ["PATH"] = old_path
            self.assertTrue(report["passed"])
            self.assertTrue((root / "relative-run/results").is_dir())
            self.assertTrue((root / "relative-report.json").is_file())

    def test_ribotish_python314_compatibility_is_narrow_and_checksum_bound(self):
        with tempfile.TemporaryDirectory(prefix="nfcore-compat-") as temporary:
            provenance = Path(temporary) / "workspace with space"
            provenance.mkdir()
            config, records = _prepare_runtime_compatibility(
                provenance,
                spec=RIBOSEQ,
                profile="docker",
                architecture_profile="arm64",
            )
            self.assertIsNotNone(config)
            text = config.read_text(encoding="utf-8")
            self.assertIn("withName: /.*RIBOTISH_.*/", text)
            self.assertNotIn("withName: /.*RIBOSEQ.*/", text)
            self.assertIn('containerOptions = "--platform linux/arm64 -e PYTHONPATH=', text)
            self.assertIn("PYTHONPATH='", text)
            self.assertFalse(records[0]["scientific_parameters_changed"])
            self.assertEqual(len(records[0]["sitecustomize_sha256"]), 64)
            self.assertEqual(len(records[0]["nextflow_config_sha256"]), 64)

    def test_schema_exposes_adjustable_official_parameters(self):
        payload = schema("input", "fasta", "gtf", "skip_ribotricer")
        self.assertEqual(
            set(schema_parameters(payload)),
            {"input", "fasta", "gtf", "skip_ribotricer"},
        )

    def test_official_resource_limits_are_written_to_nextflow_config(self):
        with tempfile.TemporaryDirectory(prefix="nfcore-resources-") as temporary:
            provenance = Path(temporary)
            config, records = _prepare_runtime_compatibility(
                provenance,
                spec=METHYLSEQ,
                profile="docker",
                architecture_profile=None,
                resource_limits={"cpus": 4, "memory": "30.GB", "time": "6.h"},
            )
            self.assertIsNotNone(config)
            text = config.read_text(encoding="utf-8")
            self.assertIn("resourceLimits", text)
            self.assertIn("cpus: 4", text)
            self.assertIn('memory: "30.GB"', text)
            self.assertEqual(records[0]["id"], "nfcore-workstation-resource-limits")
            self.assertFalse(records[0]["scientific_parameters_changed"])
            self.assertEqual(len(records[0]["nextflow_config_sha256"]), 64)

    def test_nascent_arm64_uses_digest_pinned_fastqc_container_only(self):
        request = {
            "schema_version": 1,
            "module_id": NASCENT.module_id,
            "assay": "gro-seq",
            "engine_profile": "docker",
            "official_test_profile": True,
            "resume": False,
            "container_architecture": "linux/arm64",
            "pipeline_params": {},
        }
        profile, official_test, resume, architecture_profile = _validate_request(request, NASCENT)
        self.assertEqual(profile, "docker")
        self.assertTrue(official_test)
        self.assertFalse(resume)
        self.assertEqual(architecture_profile, "fastqc_arm64")
        with tempfile.TemporaryDirectory(prefix="nfcore-nascent-arm64-") as temporary:
            provenance = Path(temporary)
            config, records = _prepare_runtime_compatibility(
                provenance,
                spec=NASCENT,
                profile="docker",
                architecture_profile=architecture_profile,
            )
            text = config.read_text(encoding="utf-8")
            self.assertIn("withName: FASTQC", text)
            self.assertNotIn("process.arch", text)
            self.assertIn("sha256:c7cdf1bd0bd7557ba7d0a986f1e907bed45cd54a484f3a81dc5a472abdf318ba", text)
            self.assertIn("--platform linux/arm64", text)
            self.assertEqual(records[0]["id"], "nfcore-nascent-fastqc-arm64-container")
            self.assertFalse(records[0]["scientific_parameters_changed"])
            self.assertEqual(len(records[0]["nextflow_config_sha256"]), 64)
            command = _build_command(
                NASCENT,
                "nextflow",
                "docker",
                architecture_profile,
                True,
                False,
                provenance / "params.json",
                provenance / "results",
                provenance / "work",
                provenance / "nextflow.log",
                config,
            )
            profiles = command[command.index("-profile") + 1]
            self.assertEqual(profiles, "test,docker")

    def test_unknown_parameter_and_remote_project_input_are_blocked(self):
        payload = schema("input")
        with self.assertRaisesRegex(NfCoreExecutionError, "unknown parameter"):
            validate_pipeline_parameters(
                RIBOSEQ,
                {"input": "samples.csv", "invented": True},
                payload,
                official_test_profile=False,
            )
        with self.assertRaisesRegex(NfCoreExecutionError, "local immutable file"):
            validate_pipeline_parameters(
                RIBOSEQ,
                {"input": "https://example.org/samples.csv"},
                payload,
                official_test_profile=False,
            )

    def test_pinned_riboseq_and_nascent_workflows_execute_and_reload(self):
        with tempfile.TemporaryDirectory(prefix="nfcore-runner-") as temporary:
            root = Path(temporary)
            fake = root / "nextflow"
            fake.write_text(FAKE_NEXTFLOW, encoding="utf-8")
            fake.chmod(0o755)
            fake_mamba = root / "mamba"
            fake_mamba.write_text("#!/bin/sh\necho 'mamba 2.0.5'\n", encoding="utf-8")
            fake_mamba.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{root}:{old_path}"
            try:
                with patch("biomed_workbench.implementations.nfcore.platform.machine", return_value="x86_64"):
                    ribo_report = self._execute_riboseq(root, fake)
                    nascent_report = self._execute_nascent(root, fake)
            finally:
                os.environ["PATH"] = old_path
        self.assertEqual(ribo_report["execution_evidence_level"], "observed_scientific_workflow")
        self.assertTrue(ribo_report["execution"]["external_workflow_executed"])
        self.assertGreaterEqual(ribo_report["outputs"]["scientific_file_count"], 4)
        self.assertEqual(nascent_report["workflow"]["revision"], "2.3.0")
        self.assertTrue(nascent_report["execution"]["outputs_reloaded"])

    def test_clip_methylation_and_hic_workflows_execute_and_reload(self):
        with tempfile.TemporaryDirectory(prefix="nfcore-expanded-") as temporary:
            root = Path(temporary)
            fake = root / "nextflow"
            fake.write_text(FAKE_NEXTFLOW, encoding="utf-8")
            fake.chmod(0o755)
            fake_mamba = root / "mamba"
            fake_mamba.write_text("#!/bin/sh\necho 'mamba 2.0.5'\n", encoding="utf-8")
            fake_mamba.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{root}:{old_path}"
            fastq_1 = root / "sample_1.fastq.gz"
            fastq_2 = root / "sample_2.fastq.gz"
            self._fastq(fastq_1)
            self._fastq(fastq_2)
            cases = [
                (
                    CLIPSEQ,
                    "iclip",
                    f"sample,fastq\ns1,{fastq_1}\n",
                    {"input": None, "fasta": str(fastq_1)},
                    schema("input", "fasta", "peakcaller"),
                    "crosslinks",
                ),
                (
                    METHYLSEQ,
                    "rrbs",
                    f"sample,fastq_1,fastq_2,genome\ns1,{fastq_1},{fastq_2},\n",
                    {"input": None, "fasta": str(fastq_1), "rrbs": True},
                    schema("input", "fasta", "rrbs"),
                    "methylation_calls",
                ),
                (
                    HIC,
                    "hi-c",
                    f"sample,fastq_1,fastq_2\ns1,{fastq_1},{fastq_2}\n",
                    {"input": None, "fasta": str(fastq_1), "digestion": "mboi"},
                    schema("input", "fasta", "digestion"),
                    "contact_matrices",
                ),
            ]
            try:
                for index, (spec, assay, sample_text, params, official_schema, expected_group) in enumerate(cases):
                    samples = root / f"samples-{index}.csv"
                    samples.write_text(sample_text, encoding="utf-8")
                    params["input"] = str(samples)
                    request = {
                        "schema_version": 1,
                        "module_id": spec.module_id,
                        "assay": assay,
                        "engine_profile": "mamba",
                        "official_test_profile": False,
                        "resume": False,
                        "pipeline_params": params,
                    }
                    report = execute_nfcore(
                        request,
                        spec=spec,
                        output_dir=root / f"run-{index}",
                        report_path=root / f"report-{index}.json",
                        nextflow=str(fake),
                        schema=official_schema,
                        timeout_seconds=30,
                    )
                    self.assertTrue(report["execution"]["outputs_reloaded"])
                    self.assertGreater(report["outputs"]["groups"][expected_group]["file_count"], 0)
            finally:
                os.environ["PATH"] = old_path

    @staticmethod
    def _fastq(path: Path) -> None:
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            handle.write("@read1\nACGT\n+\nFFFF\n")

    def _execute_riboseq(self, root: Path, fake: Path) -> dict:
        fastq = root / "ribo.fastq.gz"
        self._fastq(fastq)
        samples = root / "ribo.csv"
        samples.write_text(
            f"sample,fastq_1,fastq_2,strandedness,type\nr1,{fastq},,forward,riboseq\n",
            encoding="utf-8",
        )
        request = {
            "schema_version": 1,
            "module_id": RIBOSEQ.module_id,
            "assay": "ribo-seq",
            "engine_profile": "mamba",
            "official_test_profile": False,
            "resume": False,
            "pipeline_params": {"input": str(samples), "fasta": str(samples), "gtf": str(samples)},
        }
        return execute_nfcore(
            request,
            spec=RIBOSEQ,
            output_dir=root / "ribo-run",
            report_path=root / "ribo-report.json",
            nextflow=str(fake),
            schema=schema("input", "fasta", "gtf"),
            timeout_seconds=30,
        )

    def _execute_nascent(self, root: Path, fake: Path) -> dict:
        fastq = root / "nascent.fastq.gz"
        self._fastq(fastq)
        samples = root / "nascent.csv"
        samples.write_text(
            f"sample,fastq_1,fastq_2\nn1,{fastq},\n",
            encoding="utf-8",
        )
        request = {
            "schema_version": 1,
            "module_id": NASCENT.module_id,
            "assay": "pro-seq",
            "engine_profile": "mamba",
            "official_test_profile": False,
            "resume": False,
            "pipeline_params": {
                "input": str(samples),
                "fasta": str(samples),
                "gtf": str(samples),
                "assay_type": "PROseq",
            },
        }
        return execute_nfcore(
            request,
            spec=NASCENT,
            output_dir=root / "nascent-run",
            report_path=root / "nascent-report.json",
            nextflow=str(fake),
            schema=schema("input", "fasta", "gtf", "assay_type"),
            timeout_seconds=30,
        )


if __name__ == "__main__":
    unittest.main()
