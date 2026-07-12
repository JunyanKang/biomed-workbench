#!/usr/bin/env python3
"""Verify the project-owned Codex cachebuster update contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.prepare_local_update import cachebusted_version, update_manifest  # noqa: E402


EVIDENCE_ID = "codex-local-update-cachebuster-v1"
IMPLEMENTATION = ROOT / "tools" / "prepare_local_update.py"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify() -> dict[str, object]:
    regression = subprocess.run(
        [sys.executable, "-m", "unittest", "tests.unit.test_local_update"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if regression.returncode != 0:
        raise RuntimeError("local update regression failed")
    cases = {
        "plain": cachebusted_version("1.2.3", "reviewed-1"),
        "existing_build": cachebusted_version("1.2.3+codex.old", "reviewed-2"),
        "prerelease": cachebusted_version("1.2.3-rc.1+other.old", "reviewed-3"),
    }
    if cases != {
        "plain": "1.2.3+codex.reviewed-1",
        "existing_build": "1.2.3+codex.reviewed-2",
        "prerelease": "1.2.3-rc.1+codex.reviewed-3",
    }:
        raise RuntimeError("cachebuster replacement policy changed")
    try:
        cachebusted_version("1.2.3", "bad/value")
    except ValueError:
        invalid_rejected = True
    else:
        raise RuntimeError("unsafe cachebuster token was accepted")
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        manifest = root / ".codex-plugin" / "plugin.json"
        manifest.parent.mkdir()
        manifest.write_text(json.dumps({"name": "fixture", "version": "1.2.3+old"}), encoding="utf-8")
        first = update_manifest(root, "first")
        second = update_manifest(root, "second")
        observed = json.loads(manifest.read_text(encoding="utf-8"))
        temporary_absent = not manifest.with_suffix(".json.tmp").exists()
    if first != "1.2.3+codex.first" or second != "1.2.3+codex.second" or observed["version"] != second or not temporary_absent:
        raise RuntimeError("manifest update is not repeatable or atomic")
    return {
        "schema_version": 1,
        "passed": True,
        "evidence_id": EVIDENCE_ID,
        "evidence_type": "codex-plugin-local-update-contract",
        "implementation": {"sha256": _sha256(IMPLEMENTATION)},
        "regression": {"passed": True, "test_module": "tests.unit.test_local_update"},
        "verified_behaviors": {
            "single_build_metadata_suffix": True,
            "existing_build_metadata_replaced": True,
            "prerelease_preserved": True,
            "unsafe_token_rejected": invalid_rejected,
            "repeatable_manifest_update": True,
            "atomic_manifest_replacement": temporary_absent,
        },
        "examples": cases,
        "scope": "developer-local-plugin-reload-only",
        "scientific_runtime_capability": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "local-update-verification.json")
    args = parser.parse_args()
    report = verify()
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"evidence_id": report["evidence_id"], "passed": True}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
