#!/usr/bin/env python3
"""Verify Codex-native tool handoffs without claiming the native artifact exists."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402
from biomed_workbench.router import route  # noqa: E402
from biomed_workbench.runner import run  # noqa: E402


EVIDENCE_ID = "codex-native-image-generation-handoff-v1"
MODULE_ID = "scientific-illustration-generation"
EXPECTED_GATES = {
    "generated-not-observed-data",
    "scientific-accuracy-review",
    "text-label-fidelity",
    "reference-invariant-preservation",
    "generation-disclosure",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify() -> dict[str, object]:
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    manifest = registry.get(MODULE_ID)
    fixture_path = ROOT / "tests" / "fixtures" / "offline-capability-cases.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))[MODULE_ID]
    result = run(MODULE_ID, fixture["input"]).to_dict()
    output = result["output"]
    handoff = output.get("execution_handoff", {})
    gate_ids = {gate.get("id") for gate in output.get("quality_gates", [])}
    plan = route(manifest.intents[0], registry=registry)
    routed = [item["id"] for step in plan["steps"] for item in step["candidates"]]
    compatibility_path = ROOT / "reports" / "compatibility-execution-evidence.json"
    compatibility = json.loads(compatibility_path.read_text(encoding="utf-8"))
    record = next((item for item in compatibility["records"] if item["module_id"] == MODULE_ID), None)
    skill_path = ROOT / "skills" / "biomed-workbench" / "SKILL.md"
    skill = skill_path.read_text(encoding="utf-8")
    if (
        manifest.access != "codex_native"
        or manifest.credentials
        or manifest.tool_requirements
        or manifest.execution.kind != "workflow"
        or result.get("status") != "completed"
        or output.get("ready") is not True
        or output.get("representation_scope") != "scientific-communication-only"
        or handoff.get("tool") != "image_gen"
        or handoff.get("operation") not in {"generate", "edit"}
        or handoff.get("authentication") != "codex-managed"
        or handoff.get("cli_fallback_allowed") is not False
        or gate_ids != EXPECTED_GATES
        or routed.count(MODULE_ID) != 1
        or record is None
        or record.get("regression", {}).get("passed") is not True
        or record.get("end_to_end", {}).get("passed") is not True
        or any(marker not in skill for marker in ("execution_handoff", "access: codex_native", "tool: image_gen", "The handoff is not proof that a bitmap exists"))
    ):
        raise RuntimeError("Codex-native image handoff contract is incomplete or stale")
    return {
        "schema_version": 1,
        "passed": True,
        "evidence_id": EVIDENCE_ID,
        "evidence_type": "codex-native-tool-handoff",
        "module": {
            "id": manifest.id,
            "version": manifest.version,
            "manifest_sha256": _sha256(BUILTIN_ROOT / MODULE_ID / "module.json"),
            "access": manifest.access,
            "credentials": [],
            "external_tool_requirements": 0,
            "compatibility_row_id": manifest.compatibility_matrix[0].id,
            "regression_evidence_id": record["regression"]["id"],
            "end_to_end_evidence_id": record["end_to_end"]["id"],
        },
        "skill": {
            "sha256": _sha256(skill_path),
            "single_entry": True,
            "native_handoff_protocol_present": True,
        },
        "handoff": {
            "tool": "image_gen",
            "authentication": "codex-managed",
            "provider_sdk_or_cli": False,
            "provider_credential_requested": False,
            "deterministic_handoff_executed": True,
            "native_bitmap_invocation_tested": False,
            "native_bitmap_invocation_boundary": "Codex host at user-request execution time",
            "quality_gate_ids": sorted(EXPECTED_GATES),
            "module_routed_once": True,
        },
        "source_behavior_disposition": {
            "generate_and_edit_intent": "codex-native-handoff",
            "structured_prompt_constraints": "independent-scientific-brief-contract",
            "multiple_assets": "parallel-or-serial-module-composition",
            "provider_auth_model_endpoint_and_retry_client": "retired-codex-managed",
            "provider_specific_size_quality_transparency_and_fidelity_flags": "retired-codex-managed",
            "filesystem_output_and_downscaling": "project-artifact-delivery-after-observed-native-result",
        },
        "fixture_sha256": _sha256(fixture_path),
        "compatibility_evidence_sha256": _sha256(compatibility_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "codex-native-handoff-verification.json")
    args = parser.parse_args()
    report = verify()
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"evidence_id": report["evidence_id"], "module_id": report["module"]["id"], "passed": True}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
