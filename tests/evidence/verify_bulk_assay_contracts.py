#!/usr/bin/env python3
"""Execute and verify the no-edit contract surface for experimental bulk assays."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.evidence_scope import module_evidence_scope
from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


MODULE_IDS = (
    "bulk-chromatin-accessibility",
    "bulk-dna-methylation",
    "bulk-nascent-transcription",
    "bulk-r-loop-mapping",
    "bulk-rbp-rna-binding",
    "bulk-ribosome-profiling",
    "bulk-rna-modification-enrichment",
    "bulk-three-dimensional-genome",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    for module_id in MODULE_IDS:
        manifest = registry.get(module_id)
        module_root = BUILTIN_ROOT / module_id
        manifest_path = module_root / "module.json"
        template_path = module_root / "templates" / "run_assay_workflow.py"
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        assay = manifest_payload["input_schema"]["properties"]["assay"]["enum"][0]
        decision_inputs = manifest_payload["agent_protocol"]["parameter_rules"][0]["decision_inputs"]
        parameters = {name: f"declared fixture value for {name}" for name in decision_inputs}
        with tempfile.TemporaryDirectory(prefix=f"{module_id}-contract-") as temporary:
            work = Path(temporary)
            source = work / "representative-input.fastq"
            source.write_text("@read1\nACGTACGT\n+\nFFFFFFFF\n", encoding="utf-8")
            source_digest_before = sha256(source)
            request = work / "request.json"
            request.write_text(
                json.dumps(
                    {
                        "module_id": module_id,
                        "assay": assay,
                        "parameters": parameters,
                        "input_files": [str(source)],
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            output_dir = work / "output"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(template_path),
                    "--request",
                    str(request),
                    "--output-dir",
                    str(output_dir),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            contract_path = output_dir / "run_contract.json"
            contract = json.loads(contract_path.read_text(encoding="utf-8")) if contract_path.is_file() else {}
            source_digest_after = sha256(source)
            passed = (
                completed.returncode == 0
                and contract.get("module_id") == module_id
                and contract.get("assay") == assay
                and contract.get("execution_state") == "admitted-not-run"
                and contract.get("parameters") == parameters
                and contract.get("inputs", [{}])[0].get("sha256") == source_digest_before
                and source_digest_after == source_digest_before
                and bool(contract.get("official_workflow"))
                and bool(contract.get("required_figure_inventory"))
            )

        report = {
            "schema_version": 1,
            "passed": passed,
            "module_id": module_id,
            "module_version": manifest.version,
            "registry_digest": registry.digest,
            "evidence_scope": module_evidence_scope(registry, [module_id]).to_dict(),
            "manifest_sha256": sha256(manifest_path),
            "template_sha256": sha256(template_path),
            "fixture": {
                "synthetic_file_sha256": source_digest_before,
                "assay": assay,
                "required_parameter_count": len(parameters),
            },
            "execution": {
                "packaged_contract_executed": True,
                "contract_reloaded": True,
                "input_immutability_verified": True,
                "external_workflow_executed": False,
                "biological_result_generated": False,
                "public_data_acceptance": False,
            },
            "scientific_boundary": (
                "This report verifies the immutable packaged parameter and file-admission surface only. "
                "It does not claim that the named external assay workflow ran, that a biological result "
                "exists, or that the module has passed public-data acceptance."
            ),
        }
        report_path = ROOT / "reports" / f"{module_id}-contract-verification.json"
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if not passed:
            raise RuntimeError(f"bulk assay contract verification failed: {module_id}")
    print(json.dumps({"module_count": len(MODULE_IDS), "passed": True}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
