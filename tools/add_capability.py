#!/usr/bin/env python3
"""Add one validated capability contract to a domain specification."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.catalog import SPECIFICATION_ROOT, capability_to_dict, load_capabilities, resolve_entrypoint  # noqa: E402
from biomed_workbench.models import ACCESS_MODES, KINDS, MUTABILITY_MODES, WORKFLOWS, Capability  # noqa: E402


def add_capability(specification_root: Path, capability: Capability) -> Path:
    existing = load_capabilities(specification_root)
    if capability.id in {item.id for item in existing}:
        raise ValueError(f"capability already exists: {capability.id}")
    resolve_entrypoint(capability)
    path = specification_root / f"{capability.workflow}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["capabilities"].append(capability_to_dict(capability))
    payload["capabilities"].sort(key=lambda row: row["id"])
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    load_capabilities(specification_root)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capability_id")
    parser.add_argument("--workflow", required=True, choices=sorted(WORKFLOWS))
    parser.add_argument("--title", required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument("--entrypoint", required=True)
    parser.add_argument("--kind", choices=sorted(KINDS), default="python")
    parser.add_argument("--access", choices=sorted(ACCESS_MODES), default="offline")
    parser.add_argument("--mutability", choices=sorted(MUTABILITY_MODES), default="read_only")
    parser.add_argument("--input-schema", type=Path, help="JSON file containing the input object schema")
    parser.add_argument("--requirement", action="append", default=[])
    parser.add_argument("--specification-root", type=Path, default=SPECIFICATION_ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--no-build", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    schema = (
        json.loads(args.input_schema.read_text(encoding="utf-8"))
        if args.input_schema
        else {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
    )
    capability = Capability(
        id=args.capability_id,
        workflow=args.workflow,
        kind=args.kind,
        title=args.title,
        description=args.description,
        entrypoint=args.entrypoint,
        input_schema=schema,
        requirements=tuple(args.requirement),
        access=args.access,
        mutability=args.mutability,
    )
    path = add_capability(args.specification_root, capability)
    if not args.no_build and args.specification_root.resolve() == SPECIFICATION_ROOT.resolve():
        subprocess.run([sys.executable, str(ROOT / "tools" / "build_catalog.py")], cwd=ROOT, check=True)
    print(json.dumps({"capability": capability.id, "specification": path.name}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
