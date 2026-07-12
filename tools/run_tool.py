#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

CATALOG = Path(__file__).with_name("catalog.json")
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_entry(tool_id):
    for entry in json.loads(CATALOG.read_text())["entries"]:
        if entry["id"] == tool_id:
            return entry
    raise SystemExit(f"No tool id: {tool_id}")


def command_for(entry, extra_args):
    path = Path(entry["path"])
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    policy = entry.get("run_policy")
    if policy == "direct" and entry.get("kind") == "runtime":
        from adapters.claude_science import command_for_runtime

        return command_for_runtime(entry, extra_args)
    if policy == "direct" and entry.get("kind") == "script":
        suffix = path.suffix.lower()
        if suffix == ".py":
            return [sys.executable, str(path), *extra_args]
        if suffix == ".r":
            return ["Rscript", str(path), *extra_args]
        if suffix == ".sh":
            return ["bash", str(path), *extra_args]
        return [str(path), *extra_args]
    raise SystemExit(
        f"{entry['id']} is not directly runnable (run_policy={policy}, kind={entry.get('kind')}). "
        f"Inspect it with search_tools.py --id {entry['id']}."
    )


def main():
    parser = argparse.ArgumentParser(description="Run a direct tool from the unified biomedical catalog.")
    parser.add_argument("tool_id")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments passed to the tool; use -- before them.")
    ns = parser.parse_args()
    extra = ns.args[1:] if ns.args[:1] == ["--"] else ns.args
    entry = load_entry(ns.tool_id)
    cmd = command_for(entry, extra)
    env = os.environ.copy()
    env.setdefault("PYTHONNOUSERSITE", "0")
    raise SystemExit(subprocess.call(cmd, env=env))


if __name__ == "__main__":
    main()
