#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from route_task import human_description, intent_boosts, query_terms, score_one

CATALOG = Path(__file__).with_name("catalog.json")


def load_catalog():
    return json.loads(CATALOG.read_text())


def print_entry(entry, verbose=False):
    print(f"{entry['id']} [{entry['workflow']} / {entry['kind']}]")
    print(f"  name: {entry.get('name', '')}")
    print(f"  description: {human_description(entry)}")
    print(f"  path: {entry.get('path', '')}")
    print(f"  run_policy: {entry.get('run_policy', '')}")
    if verbose:
        for key in ("source", "source_path", "function", "language", "domain"):
            if entry.get(key):
                print(f"  {key}: {entry[key]}")
        req = entry.get("required_parameters") or []
        if req:
            print("  required_parameters:")
            for param in req:
                print(f"    - {param.get('name')}: {param.get('description', '')}")


def main():
    parser = argparse.ArgumentParser(description="Search the unified local biomedical tool catalog.")
    parser.add_argument("query", nargs="*", help="Search terms.")
    parser.add_argument("--workflow", default="auto", help="Workflow filter or 'auto'.")
    parser.add_argument("--kind", default="", help="Kind filter, e.g. script, biomni_function, runtime.")
    parser.add_argument("--id", dest="tool_id", default="", help="Show one tool by exact id.")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    entries = load_catalog()["entries"]
    if args.tool_id:
        for entry in entries:
            if entry["id"] == args.tool_id:
                print_entry(entry, verbose=True)
                return
        raise SystemExit(f"No tool id: {args.tool_id}")

    if args.workflow != "auto":
        entries = [e for e in entries if e.get("workflow") == args.workflow]
    if args.kind:
        entries = [e for e in entries if e.get("kind") == args.kind]

    query = " ".join(args.query).strip()
    terms = query_terms(query)
    if query:
        workflows = [] if args.workflow == "auto" else [args.workflow]
        boosts = intent_boosts(query)
        scored = []
        for entry in entries:
            score = score_one(entry, terms, workflows, boosts)
            if score:
                scored.append((score, entry))
        entries = [e for _, e in sorted(scored, key=lambda x: (-x[0], x[1]["workflow"], x[1]["id"]))]
    else:
        entries = sorted(entries, key=lambda e: (e["workflow"], e["kind"], e["id"]))

    print(f"{len(entries)} match(es)")
    for entry in entries[: args.limit]:
        print_entry(entry, verbose=args.verbose)


if __name__ == "__main__":
    main()
