#!/usr/bin/env python3
"""Build the deterministic, publish-safe foundational format contract report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.formats import FormatRegistry  # noqa: E402


def build() -> dict[str, object]:
    registry = FormatRegistry.builtin()
    profiles = registry.all()
    return {
        "schema_version": 1,
        "registry_digest": registry.digest,
        "profile_count": len(profiles),
        "format_names": sorted(profile.name for profile in profiles),
        "requirement_coverage": {
            "coordinate_aware": sum(bool(profile.coordinate_systems) for profile in profiles),
            "indexed": sum(bool(profile.index_requirements) for profile in profiles),
            "reference_required": sum(profile.reference_policy == "required" for profile in profiles),
            "annotation_required": sum(profile.annotation_policy == "required" for profile in profiles),
            "identifier_namespace_required": sum(profile.identifier_namespace_policy == "required" for profile in profiles),
            "sample_manifest_required": sum(profile.sample_manifest_policy == "required" for profile in profiles),
            "multi_payload": sum(len(profile.required_payload_roles) > 1 for profile in profiles),
        },
        "profiles": registry.to_dict()["profiles"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "format-contract-registry.json")
    args = parser.parse_args()
    report = build()
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"profile_count": report["profile_count"], "registry_digest": report["registry_digest"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
