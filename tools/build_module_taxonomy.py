#!/usr/bin/env python3
"""Build a complete registry taxonomy report from orthogonal scientific facets."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry
from biomed_workbench.modules.scientific_taxonomy import classify_module


def main() -> None:
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    rows = [classify_module(module) for module in registry.all()]
    if len(rows) != len({row["module_id"] for row in rows}):
        raise RuntimeError("module taxonomy coverage is not one-to-one")
    scales = Counter(row["primary_scale"] for row in rows)
    roles = Counter(row["method_role"] for row in rows)
    report = {
        "schema_version": 1,
        "generated_on": "2026-07-31",
        "registry_digest": registry.digest,
        "module_count": len(rows),
        "classification_model": {
            "first_facet": "data scale: bulk, single-cell, spatial, or universal",
            "second_facet": "measurement family or non-assay research function",
            "third_facet": "method role: assay-specific, multi-assay, cross-scale, or infrastructure",
            "strategy_fields": "target, antibody, spike-in/internal reference, specificity control, normalization, and peak recall remain parameters and never become assay classes",
        },
        "scale_counts": dict(sorted(scales.items())),
        "method_role_counts": dict(sorted(roles.items())),
        "modules": rows,
    }
    canonical = json.dumps(report, indent=2, sort_keys=True) + "\n"
    report["report_sha256_without_self_field"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    (ROOT / "reports" / "module-scientific-taxonomy.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"modules": len(rows), "scales": dict(scales), "registry_digest": registry.digest}, sort_keys=True))


if __name__ == "__main__":
    main()
