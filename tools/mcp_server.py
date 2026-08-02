#!/usr/bin/env python3
"""Optional read-only MCP adapter for the Codex-first Biomed Workbench plugin."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.catalog import all_capabilities, resolve  # noqa: E402
from biomed_workbench.router import route  # noqa: E402
from biomed_workbench.runner import run  # noqa: E402
from biomed_workbench.version import VERSION  # noqa: E402

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:
    raise SystemExit("Install the optional requirements-mcp.txt environment before starting the MCP server.") from exc


mcp = FastMCP("Biomed Workbench Interoperability Adapter")


def _public_capability(item: Any) -> dict[str, Any]:
    return {
        "id": item.id,
        "workflow": item.workflow,
        "kind": item.kind,
        "title": item.title,
        "description": item.description,
        "input_schema": item.input_schema,
        "requirements": list(item.requirements),
        "access": item.access,
        "mutability": item.mutability,
    }


@mcp.tool()
def list_biomedical_capabilities(workflow: str | None = None) -> dict[str, Any]:
    """List registered scientific capabilities, optionally for one workflow."""
    records = [_public_capability(item) for item in all_capabilities() if workflow is None or item.workflow == workflow]
    return {"version": VERSION, "count": len(records), "capabilities": records}


@mcp.tool()
def route_biomedical_research(objective: str, per_workflow: int = 3) -> dict[str, Any]:
    """Compile a natural-language research objective into a bounded capability plan."""
    return route(objective, per_workflow=per_workflow)


@mcp.tool()
def describe_biomedical_capability(capability_id: str) -> dict[str, Any]:
    """Return the exact contract for one registered capability."""
    return _public_capability(resolve(capability_id))


@mcp.tool()
def run_read_only_biomedical_capability(capability_id: str, request_json: str) -> dict[str, Any]:
    """Run one read-only capability through the same schema and permission gates as the local plugin."""
    capability = resolve(capability_id)
    if capability.mutability != "read_only":
        raise ValueError("MCP execution is restricted to read-only capabilities; use the Codex plugin or an independently validated host workflow for output-writing modules")
    request = json.loads(request_json)
    if not isinstance(request, dict):
        raise ValueError("request_json must decode to an object")
    return run(capability_id, request).to_dict()


if __name__ == "__main__":
    mcp.run(transport="stdio")
