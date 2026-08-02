#!/usr/bin/env python3
"""Bind newly generated module reports to their current module and template slice."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.evidence_scope import module_evidence_scope, report_module_ids  # noqa: E402
from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402


def atomic_write(path: Path, text: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        Path(temporary_name).unlink(missing_ok=True)


def bind(path: Path, registry: ModuleRegistry) -> tuple[str, ...]:
    resolved = path.resolve()
    if resolved.parent != (ROOT / "reports").resolve():
        raise RuntimeError("report must be a direct child of reports/")
    report = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(report, dict) or report.get("passed") is not True:
        raise RuntimeError("only passing object reports can receive an evidence scope")
    module_ids = report_module_ids(report)
    if not module_ids:
        raise RuntimeError("report does not identify a registered module")
    report.setdefault("schema_version", 1)
    report["evidence_scope"] = module_evidence_scope(registry, module_ids).to_dict()
    atomic_write(resolved, json.dumps(report, indent=2, sort_keys=True) + "\n")
    return module_ids


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="append", required=True, type=Path)
    args = parser.parse_args()
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    bound = {path.name: bind(path, registry) for path in args.report}
    print(json.dumps({"bound": bound, "registry_digest": registry.digest}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
