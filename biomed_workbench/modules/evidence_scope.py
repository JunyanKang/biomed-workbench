"""Dependency-scoped identity for scientific execution evidence.

Registry digests identify a complete installation snapshot.  They are useful
for packaging checks, but are intentionally not evidence identities: adding an
unrelated module must not invalidate an observed execution for another module.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ..kernel.identity import digest_value
from .contract import manifest_to_dict
from .index import BUILTIN_ROOT
from .registry import ModuleRegistry, ModuleRegistryError
from .template_quality import referenced_template_paths


@dataclass(frozen=True)
class EvidenceScope:
    schema_version: int
    module_ids: tuple[str, ...]
    module_slice_digest: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("evidence scope schema is unsupported")
        if not self.module_ids or self.module_ids != tuple(sorted(set(self.module_ids))):
            raise ValueError("evidence scope module IDs must be nonempty, unique, and sorted")
        if len(self.module_slice_digest) != 64:
            raise ValueError("evidence scope digest must be SHA-256")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "module_ids": list(self.module_ids),
            "module_slice_digest": self.module_slice_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidenceScope":
        if set(payload) != {"schema_version", "module_ids", "module_slice_digest"}:
            raise ValueError("evidence scope fields are incomplete or unsupported")
        return cls(
            schema_version=payload["schema_version"],
            module_ids=tuple(payload["module_ids"]),
            module_slice_digest=payload["module_slice_digest"],
        )


def _template_digests(module_id: str, registry: ModuleRegistry, module_root: Path) -> dict[str, str]:
    manifest = registry.get(module_id)
    result: dict[str, str] = {}
    for relative in referenced_template_paths(manifest):
        path = module_root / module_id / relative
        if not path.is_file():
            raise ModuleRegistryError(f"evidence scope references a missing template: {module_id}/{relative}")
        result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def module_slice_basis(
    registry: ModuleRegistry,
    module_ids: tuple[str, ...] | list[str],
    *,
    module_root: Path = BUILTIN_ROOT,
) -> dict[str, object]:
    """Return the exact module/template slice on which execution evidence depends."""
    ordered = tuple(sorted(set(module_ids)))
    if not ordered:
        raise ValueError("evidence scope requires at least one module")
    def execution_manifest(module_id: str) -> dict[str, object]:
        payload = manifest_to_dict(registry.get(module_id))
        # Routing, cross-module scheduling, and external-result admission affect
        # discovery or controller re-entry, not the already observed scientific
        # computation represented by a public-case scope.  Their independent
        # digests still bind installation state and each future handoff.
        payload.pop("routing", None)
        payload.pop("orchestration", None)
        payload.pop("observed_output_contracts", None)
        # Scientific semantics govern future routing and minimal-sufficient
        # selection.  They do not alter a previously observed implementation,
        # input, parameter, output, or template identity.
        payload.pop("scientific_semantics", None)
        return payload

    return {
        "schema_version": 1,
        "modules": [
            {
                "manifest": execution_manifest(module_id),
                "templates": _template_digests(module_id, registry, module_root),
            }
            for module_id in ordered
        ],
    }


def module_evidence_scope(
    registry: ModuleRegistry,
    module_ids: tuple[str, ...] | list[str],
    *,
    module_root: Path = BUILTIN_ROOT,
) -> EvidenceScope:
    ordered = tuple(sorted(set(module_ids)))
    return EvidenceScope(
        schema_version=1,
        module_ids=ordered,
        module_slice_digest=hashlib.sha256(
            json.dumps(
                module_slice_basis(registry, ordered, module_root=module_root),
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
    )


def report_module_ids(report: Mapping[str, Any]) -> tuple[str, ...]:
    """Extract module identities from supported live/public evidence layouts."""
    values: list[str] = []
    if isinstance(report.get("module_id"), str):
        values.append(report["module_id"])
    if isinstance(report.get("module_ids"), list):
        values.extend(item for item in report["module_ids"] if isinstance(item, str))
    nested = report.get("module")
    if isinstance(nested, Mapping) and isinstance(nested.get("id"), str):
        values.append(nested["id"])
    return tuple(sorted(set(values)))


def evidence_scope_is_current(
    report: Mapping[str, Any],
    registry: ModuleRegistry,
    *,
    module_root: Path = BUILTIN_ROOT,
) -> bool:
    module_ids = report_module_ids(report)
    raw_scope = report.get("evidence_scope")
    if not module_ids or not isinstance(raw_scope, Mapping):
        return False
    try:
        observed = EvidenceScope.from_dict(raw_scope)
        expected = module_evidence_scope(registry, module_ids, module_root=module_root)
    except (ValueError, ModuleRegistryError):
        return False
    return observed == expected
