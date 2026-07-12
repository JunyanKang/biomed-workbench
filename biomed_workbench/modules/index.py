"""Deterministic generated indexes for scientific modules and v0.2 clients."""

from __future__ import annotations

import json
from pathlib import Path

from ..version import VERSION
from .contract import manifest_to_dict
from .registry import ModuleRegistry


BUILTIN_ROOT = Path(__file__).with_name("builtin")
MODULE_INDEX = Path(__file__).with_name("index.json")
COMPATIBILITY_CATALOG = Path(__file__).resolve().parents[2] / "tools" / "catalog.json"


def build_index(registry: ModuleRegistry) -> dict[str, object]:
    return {
        "schema_version": 1,
        "plugin_version": VERSION,
        "module_count": len(registry.all()),
        "registry_digest": registry.digest,
        "modules": [manifest_to_dict(module) for module in registry.all()],
    }


def build_compatibility_catalog(registry: ModuleRegistry) -> dict[str, object]:
    entries = []
    for module in registry.all():
        entries.append(
            {
                "id": module.id,
                "workflow": module.domains[0],
                "kind": module.execution.kind,
                "title": module.title,
                "description": module.description,
                "entrypoint": module.entrypoint,
                "input_schema": dict(module.input_schema),
                "requirements": [],
                "access": module.access,
                "mutability": module.mutability,
            }
        )
    return {"schema_version": 2, "version": VERSION, "entry_count": len(entries), "entries": entries}


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_generated_indexes(registry: ModuleRegistry, module_index: Path, catalog: Path) -> None:
    _write(module_index, build_index(registry))
    _write(catalog, build_compatibility_catalog(registry))
