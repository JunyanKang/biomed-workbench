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
    )
    args.public_output.parent.mkdir(parents=True, exist_ok=True)
    args.public_output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("file_count", "reconciled_count", "pending_count", "receipt_root_digest")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
