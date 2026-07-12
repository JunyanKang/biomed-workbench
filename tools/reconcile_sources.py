#!/usr/bin/env python3
"""Reconcile private per-file source ledgers with current path-free release evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.audit import reconcile_ledgers  # noqa: E402
from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402


PROJECT_EVIDENCE_SOURCES = {
    "codex-plugin-manifest-contract-v1": {
        "report": "reports/plugin-contract-verification.json",
        "evidence_type": "codex-plugin-contract",
        "artifact": ".codex-plugin/plugin.json",
        "digest_section": "plugin",
        "digest_field": "manifest_sha256",
    },
    "codex-native-image-generation-handoff-v1": {
        "report": "reports/codex-native-handoff-verification.json",
        "evidence_type": "codex-native-tool-handoff",
        "artifact": "skills/biomed-workbench/SKILL.md",
        "digest_section": "skill",
        "digest_field": "sha256",
    },
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _project_evidence() -> dict[str, dict[str, str]]:
    records = {}
    for evidence_id, source in PROJECT_EVIDENCE_SOURCES.items():
        report_path = ROOT / source["report"]
        artifact_path = ROOT / source["artifact"]
        report = json.loads(report_path.read_text(encoding="utf-8"))
        artifact_sha256 = _sha256(artifact_path)
        if (
            report.get("passed") is not True
            or report.get("evidence_id") != evidence_id
            or report.get("evidence_type") != source["evidence_type"]
            or report.get(source["digest_section"], {}).get(source["digest_field"]) != artifact_sha256
        ):
            raise RuntimeError(f"project contract evidence is stale or invalid: {evidence_id}")
        records[evidence_id] = {
            "evidence_type": source["evidence_type"],
            "artifact_sha256": artifact_sha256,
            "verification_sha256": _sha256(report_path),
        }
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--design-ledger", type=Path, required=True)
    parser.add_argument("--capability-bindings", type=Path, required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    parser.add_argument("--public-output", type=Path, required=True)
    args = parser.parse_args()
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    research = json.loads((ROOT / "reports" / "research-engine-verification.json").read_text(encoding="utf-8"))
    compatibility = json.loads((ROOT / "reports" / "compatibility-execution-evidence.json").read_text(encoding="utf-8"))
    if compatibility.get("passed") is not True or compatibility.get("registry_digest") != registry.digest:
        raise RuntimeError("compatibility evidence is stale or not passing")
    module_evidence = {
        record["module_id"]: (
            record["row_id"],
            record["regression"]["id"],
            record["end_to_end"]["id"],
        )
        for record in compatibility["records"]
        if record.get("regression", {}).get("passed") is True and record.get("end_to_end", {}).get("passed") is True
    }
    skill_sha256 = hashlib.sha256((ROOT / "skills" / "biomed-workbench" / "SKILL.md").read_bytes()).hexdigest()
    args.private_output.parent.mkdir(parents=True, exist_ok=True)
    summary = reconcile_ledgers(
        args.manifest,
        args.design_ledger,
        module_count=len(registry.all()),
        registry_digest=registry.digest,
        skill_sha256=skill_sha256,
        test_count=research["test_count"],
        private_output=args.private_output,
        bindings_path=args.capability_bindings,
        module_evidence=module_evidence,
        project_evidence=_project_evidence(),
    )
    args.public_output.parent.mkdir(parents=True, exist_ok=True)
    args.public_output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("file_count", "reconciled_count", "pending_count", "receipt_root_digest")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
