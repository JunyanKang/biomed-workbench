#!/usr/bin/env python3
"""Capture and validate the optional MCP adapter without changing scientific evidence."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import platform
import sys


ROOT = Path(__file__).resolve().parents[1]
MCP_SOURCE = ROOT / "tools" / "mcp_server.py"
MCP_REQUIREMENTS = ROOT / "requirements-mcp.txt"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.catalog import all_capabilities  # noqa: E402
from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def capture() -> dict[str, object]:
    spec = importlib.util.spec_from_file_location("biomed_workbench_mcp_adapter", MCP_SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError("MCP adapter cannot be loaded")
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    listed = adapter.list_biomedical_capabilities()
    routed = adapter.route_biomedical_research(
        "Use AlphaFold 3 and HADDOCK3 to assess a protein complex", 3
    )
    described = adapter.describe_biomedical_capability("protein-complex-docking")
    executed = adapter.run_read_only_biomedical_capability(
        "sequence-inspect", '{"sequence":"ACGT","alphabet":"dna"}'
    )
    read_only_completed = (
        executed.get("capability_id") == "sequence-inspect"
        and executed.get("status") == "completed"
        and executed.get("output", {}).get("gc_percent") == 50.0
    )
    mutable = next(item for item in all_capabilities() if item.mutability != "read_only")
    write_blocked = False
    try:
        adapter.run_read_only_biomedical_capability(mutable.id, "{}")
    except ValueError as exc:
        write_blocked = "restricted to read-only" in str(exc)
    selected = routed.get("selected_module_ids", [])
    passed = (
        listed.get("count") == len(registry.all())
        and described.get("id") == "protein-complex-docking"
        and "protein-complex-docking" in selected
        and "alphafold3-complex-prediction" in selected
        and read_only_completed
        and write_blocked
    )
    return {
        "schema_version": 1,
        "passed": passed,
        "adapter": "optional-read-only-mcp",
        "scientific_maturity_effect": "none",
        "server_name": adapter.mcp.name,
        "module_count": listed.get("count"),
        "registry_digest": registry.digest,
        "route_selected_module_ids": selected,
        "described_module_id": described.get("id"),
        "read_only_execution": {
            "module_id": executed.get("capability_id"),
            "status": executed.get("status"),
            "gc_percent": executed.get("output", {}).get("gc_percent"),
        },
        "write_capability_blocked": write_blocked,
        "dependency_versions": {
            "mcp": importlib.metadata.version("mcp"),
            "python": platform.python_version(),
        },
        "source_sha256": {
            "mcp_server.py": sha256(MCP_SOURCE),
            "requirements-mcp.txt": sha256(MCP_REQUIREMENTS),
        },
    }


def validate_report(report: dict[str, object]) -> bool:
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    source = report.get("source_sha256", {})
    return bool(
        report.get("passed") is True
        and report.get("adapter") == "optional-read-only-mcp"
        and report.get("scientific_maturity_effect") == "none"
        and report.get("module_count") == len(registry.all())
        and report.get("registry_digest") == registry.digest
        and isinstance(source, dict)
        and source.get("mcp_server.py") == sha256(MCP_SOURCE)
        and source.get("requirements-mcp.txt") == sha256(MCP_REQUIREMENTS)
        and report.get("read_only_execution") == {
            "module_id": "sequence-inspect",
            "status": "completed",
            "gc_percent": 50.0,
        }
        and report.get("write_capability_blocked") is True
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "mcp-adapter-live-verification.json")
    args = parser.parse_args()
    report = capture()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "module_count": report["module_count"], "registry_digest": report["registry_digest"]}, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
