#!/usr/bin/env python3
"""Inspect the active analysis environment and its reusable project records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.kernel.environment_identity import (  # noqa: E402
    capture_analysis_environment,
    environment_reuse_status,
    validate_analysis_environment,
)
from biomed_workbench.kernel.state import ProjectState  # noqa: E402
from biomed_workbench.modules.compatibility import detect_environment  # noqa: E402
from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402


def _states(root: Path) -> tuple[ProjectState, ...]:
    directory = root / ".biomed-workbench" / "projects"
    values = []
    for path in sorted(directory.glob("*/project-state.json")) if directory.is_dir() else ():
        payload = json.loads(path.read_text(encoding="utf-8"))
        values.append(ProjectState.from_dict(payload))
    return tuple(values)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--module")
    parser.add_argument("--compatibility-row")
    args = parser.parse_args()
    root = args.project_root.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("project root must be a directory")
    current = capture_analysis_environment(project_root=root)
    if args.module:
        manifest = ModuleRegistry.discover(BUILTIN_ROOT).get(args.module)
        if args.compatibility_row and args.compatibility_row not in {
            row.id for row in manifest.compatibility_matrix
        }:
            raise ValueError("compatibility row is not declared by the selected module")
        current = detect_environment(
            manifest, project_root=str(root)
        ).resolved_analysis_environment(project_root=str(root))
    prior = []
    legacy_count = 0
    for state in _states(root):
        for receipt in state.observed_executions:
            if args.module and receipt.module_id != args.module:
                continue
            if args.compatibility_row and receipt.compatibility_row_id != args.compatibility_row:
                continue
            if receipt.execution_environment is None:
                legacy_count += 1
            else:
                prior.append(validate_analysis_environment(receipt.execution_environment))
    status = environment_reuse_status(current, tuple(prior)) if args.module else (
        "module-selection-required" if prior else "first-observed"
    )
    if legacy_count and not prior:
        status = "provenance-missing"
    payload = {
        "analysis_environment_protocol_version": current["protocol_version"],
        "current": current,
        "filters": {
            "module_id": args.module,
            "compatibility_row_id": args.compatibility_row,
        },
        "matching_environment_records": len(prior),
        "matching_legacy_receipts_without_environment": legacy_count,
        "reuse_status": status,
        "execution_allowed": status in {"first-observed", "reused-exact", "reused-relocated"},
        "action": {
            "first-observed": "record-current-environment-after-observed-execution",
            "reused-exact": "reuse-current-environment-without-installation",
            "reused-relocated": "reuse-content-equivalent-environment-without-installation",
            "drift-blocked": "restore-a-recorded-environment-or-create-an-explicit-new-analysis-branch",
            "provenance-missing": "recover-and-verify-the-legacy-environment-before-reexecution",
            "module-selection-required": "select-a-module-and-compatibility-row-before-a-reuse-decision",
        }[status],
    }
    print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if payload["execution_allowed"] else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc), "passed": False}, sort_keys=True), file=sys.stderr)
        raise SystemExit(2)
