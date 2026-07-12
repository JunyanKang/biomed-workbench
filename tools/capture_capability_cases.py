#!/usr/bin/env python3
"""Capture representative offline capability inputs and observed outputs."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def capture_cases() -> dict[str, dict[str, object]]:
    module = importlib.import_module("tests.e2e.test_offline_capabilities")
    original = module.execute
    captured = {}

    def recording_execute(capability_id, payload):
        output = original(capability_id, payload)
        captured[capability_id] = {"input": payload, "output": output}
        return output

    module.execute = recording_execute
    try:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(module.OfflineCapabilityE2ETests)
        result = unittest.TestResult()
        suite.run(result)
    finally:
        module.execute = original
    if result.failures or result.errors:
        raise RuntimeError("offline capability cases failed during capture")
    return {capability_id: captured[capability_id] for capability_id in sorted(captured)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "tests" / "fixtures" / "offline-capability-cases.json")
    args = parser.parse_args()
    cases = capture_cases()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(cases, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"case_count": len(cases), "output": args.output.name}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
