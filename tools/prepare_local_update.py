#!/usr/bin/env python3
"""Apply one Codex cachebuster to the plugin version and rebuild its catalog."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
_CACHEBUSTER_RE = re.compile(r"^[0-9A-Za-z.-]+$")


def cachebusted_version(version: str, cachebuster: str) -> str:
    base = version.split("+", 1)[0]
    if not _CACHEBUSTER_RE.fullmatch(cachebuster):
        raise ValueError("cachebuster must contain only letters, digits, dots, and hyphens")
    return f"{base}+codex.{cachebuster}"


def update_manifest(plugin_root: Path, cachebuster: str) -> str:
    path = plugin_root / ".codex-plugin" / "plugin.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["version"] = cachebusted_version(str(payload["version"]), cachebuster)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return payload["version"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cachebuster", help="Override the default UTC local timestamp")
    parser.add_argument("--plugin-root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--no-build", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    cachebuster = args.cachebuster or datetime.now(timezone.utc).strftime("local-%Y%m%d-%H%M%S")
    version = update_manifest(args.plugin_root, cachebuster)
    if not args.no_build:
        subprocess.run([sys.executable, str(args.plugin_root / "tools" / "build_catalog.py")], cwd=args.plugin_root, check=True)
    print(json.dumps({"version": version, "reinstall": "codex plugin add biomed-workbench@biomed-workbench"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
