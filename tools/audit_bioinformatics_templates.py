#!/usr/bin/env python3
"""Build the release-facing bioinformatics code-template coverage report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402
from biomed_workbench.modules.template_quality import (  # noqa: E402
    is_bioinformatics_module,
    referenced_template_paths,
    validate_module_templates,
)


def build() -> dict[str, object]:
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    records = []
    for manifest in registry.all():
        if not is_bioinformatics_module(manifest):
            continue
        module_path = BUILTIN_ROOT / manifest.id
        errors = validate_module_templates(module_path, manifest)
        manual_templates = [
            item.path for item in manifest.code_templates if item.requires_adaptation
        ]
        records.append(
            {
                "module_id": manifest.id,
                "module_type": manifest.module_type,
                "domains": list(manifest.domains),
                "template_files": list(referenced_template_paths(manifest)),
                "template_count": len(referenced_template_paths(manifest)),
                "manual_adaptation_template_count": len(manual_templates),
                "manual_adaptation_templates": manual_templates,
                "passed": not errors,
                "errors": errors,
            }
        )
    return {
        "schema_version": 1,
        "registry_digest": registry.digest,
        "bioinformatics_module_count": len(records),
        "covered_module_count": sum(bool(item["template_count"]) for item in records),
        "passing_module_count": sum(bool(item["passed"]) for item in records),
        "manual_adaptation_template_count": sum(
            int(item["manual_adaptation_template_count"]) for item in records
        ),
        "passed": bool(records) and all(bool(item["passed"]) for item in records),
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build()
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
