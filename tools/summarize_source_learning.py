#!/usr/bin/env python3
"""Create a publish-safe synthesis from the private per-file understanding manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.assimilation import load_private_manifest  # noqa: E402
from biomed_workbench.learning_synthesis import synthesize_learning  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    _roots, records = load_private_manifest(args.manifest)
    payload = synthesize_learning(records)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"learned_file_count": payload["learned_file_count"], "clusters": len(payload["clusters"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
