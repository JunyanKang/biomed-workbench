#!/usr/bin/env python3
"""Build a complete, path-neutral assimilation ledger for academic-figure-skill."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess


SOURCE_URL = "https://github.com/TingxiYu/academic-figure-skill"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tracked(root: Path) -> list[str]:
    output = subprocess.check_output(["git", "-C", str(root), "ls-files", "-z"])
    return sorted(item.decode("utf-8") for item in output.split(b"\0") if item)


def _commit(root: Path) -> str:
    return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()


def _classify(relative: str) -> tuple[str, str, str]:
    path = Path(relative)
    suffix = path.suffix.lower()
    if relative == "LICENSE":
        return "provenance", "retain-attribution", "Apache-2.0 provenance is retained in the product module contract."
    if suffix in {".png", ".pdf"}:
        return "generated-visual-asset", "exclude", "Preview or example artwork is not shipped or used as scientific input; its data provenance is insufficient for a product output."
    if relative.startswith("install/"):
        return "host-adapter", "exclude", "Host-specific installation copies are replaced by the Workbench registry and Codex plugin entrypoint."
    if suffix in {".py", ".r"} and relative.startswith("assets/figures/"):
        return "example-plot-code", "supersede", "Hard-coded, simulated, path-dependent, or manually adapted examples are replaced by one immutable parameterized renderer."
    if suffix in {".py", ".r"}:
        return "evaluation-or-composition-code", "supersede", "Self-referential checks and composition helpers are replaced by executed rendering, container reload, row-integrity, determinism, and routing tests."
    if suffix in {".md", ".cursorrules"}:
        return "guidance", "translate-to-source-neutral-contract", "Useful principles are expressed as product-owned scientific and quality gates; source-specific copy-first and signal-strength rules are excluded."
    if suffix in {".json", ".yaml", ".yml"}:
        return "configuration-or-generated-evaluation", "supersede", "Source-specific inventories and self-evaluation are replaced by the Workbench manifest, tests, and observed comparison report."
    return "other", "exclude", "No runtime or scientific product dependency is created from this file."


def build(source: Path) -> dict[str, object]:
    rows = []
    for relative in _tracked(source):
        path = source / relative
        classification, disposition, rationale = _classify(relative)
        row: dict[str, object] = {
            "path": relative,
            "byte_count": path.stat().st_size,
            "sha256": _sha256(path),
            "classification": classification,
            "disposition": disposition,
            "rationale": rationale,
        }
        if path.suffix.lower() == ".py":
            try:
                ast.parse(path.read_text(encoding="utf-8"))
                row["python_syntax"] = "pass"
            except (SyntaxError, UnicodeDecodeError) as exc:
                row["python_syntax"] = "fail"
                row["python_syntax_error"] = f"{type(exc).__name__}:{getattr(exc, 'lineno', 'unknown')}"
        rows.append(row)
    by_classification: dict[str, int] = {}
    by_disposition: dict[str, int] = {}
    for row in rows:
        by_classification[str(row["classification"])] = by_classification.get(str(row["classification"]), 0) + 1
        by_disposition[str(row["disposition"])] = by_disposition.get(str(row["disposition"]), 0) + 1
    return {
        "schema_version": 1,
        "source": {"repository": SOURCE_URL, "commit": _commit(source), "license": "Apache-2.0"},
        "inventory": {"tracked_file_count": len(rows), "by_classification": dict(sorted(by_classification.items())), "by_disposition": dict(sorted(by_disposition.items()))},
        "source_execution_findings": {
            "hardcoded_repository_folder_dependency": True,
            "python_syntax_failure_count": sum(row.get("python_syntax") == "fail" for row in rows),
            "self_reported_ready_count": 29,
            "self_report_limitation": "The source evaluation checks one selected script syntax and preview existence per figure type; it does not execute and reload every plot implementation.",
        },
        "product_boundary": {
            "source_tree_vendored": False,
            "source_runtime_import": False,
            "preview_pixels_used_as_output": False,
            "manual_template_editing": False,
            "assimilated_principles": [
                "scientific claim and evidence role before plot selection",
                "final-size typography and stroke validation",
                "vector and high-resolution raster delivery",
                "panel-level source-data traceability",
                "code-level plus rendered-output quality review",
            ],
            "rejected_patterns": [
                "copy and manually edit one plotting script per project",
                "embed a pre-rendered example image as a native run",
                "treat arbitrary effect-strength thresholds as rendering success",
                "adjust simulated data until a visual signal passes",
                "infer scientific column roles from semantic similarity",
                "claim journal specifications without a current official guide",
            ],
        },
        "files": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    payload = build(args.source.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": args.output.as_posix(), "file_count": payload["inventory"]["tracked_file_count"], "commit": payload["source"]["commit"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
