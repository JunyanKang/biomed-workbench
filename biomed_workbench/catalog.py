"""Validated registry for source-neutral scientific capability specifications."""

from __future__ import annotations

import importlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from .models import Capability
from .modules.index import BUILTIN_ROOT
from .modules.registry import ModuleRegistry, ModuleRegistryError


SPECIFICATION_ROOT = Path(__file__).with_name("capability_specs")
BUILTIN_MODULE_ROOT = BUILTIN_ROOT
SPECIFICATION_FIELDS = {
    "id",
    "workflow",
    "kind",
    "title",
    "description",
    "entrypoint",
    "input_schema",
    "requirements",
    "access",
    "mutability",
}


class CapabilityResolutionError(LookupError):
    """Raised when a capability ID or entrypoint cannot be resolved."""


class CapabilitySpecificationError(ValueError):
    """Raised when a domain capability specification violates the registry contract."""


def _read_specification(path: Path) -> tuple[str, list[dict[str, object]]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CapabilitySpecificationError(f"invalid capability specification: {path.name}") from exc
    if set(payload) != {"schema_version", "workflow", "capabilities"} or payload.get("schema_version") != 1:
        raise CapabilitySpecificationError(f"unsupported capability specification contract: {path.name}")
    workflow = payload.get("workflow")
    rows = payload.get("capabilities")
    if not isinstance(workflow, str) or not workflow or not isinstance(rows, list) or not rows:
        raise CapabilitySpecificationError(f"capability specification is empty or malformed: {path.name}")
    return workflow, rows


def load_capabilities(specification_root: Path = SPECIFICATION_ROOT) -> tuple[Capability, ...]:
    paths = sorted(specification_root.glob("*.json"))
    if not paths:
        raise CapabilitySpecificationError("no capability specifications were found")
    capabilities: dict[str, Capability] = {}
    workflows: set[str] = set()
    for path in paths:
        workflow, rows = _read_specification(path)
        if workflow in workflows:
            raise CapabilitySpecificationError(f"duplicate workflow specification: {workflow}")
        workflows.add(workflow)
        if path.stem != workflow:
            raise CapabilitySpecificationError(f"specification filename must match workflow: {path.name}")
        for row in rows:
            if not isinstance(row, dict) or set(row) != SPECIFICATION_FIELDS:
                raise CapabilitySpecificationError(f"invalid capability fields in {path.name}")
            if row.get("workflow") != workflow or not isinstance(row.get("requirements"), list):
                raise CapabilitySpecificationError(f"capability workflow or requirements mismatch in {path.name}")
            values = dict(row)
            values["requirements"] = tuple(values["requirements"])
            try:
                capability = Capability(**values)
            except (TypeError, ValueError) as exc:
                raise CapabilitySpecificationError(f"invalid capability contract in {path.name}") from exc
            if capability.id in capabilities:
                raise CapabilitySpecificationError(f"duplicate capability id: {capability.id}")
            capabilities[capability.id] = capability
    return tuple(capabilities[capability_id] for capability_id in sorted(capabilities))


def _module_capability(module) -> Capability:
    values = {
        "id": module.id,
        "workflow": module.domains[0],
        "kind": module.execution.kind,
        "title": module.title,
        "description": module.description,
        "entrypoint": module.entrypoint,
        "input_schema": dict(module.input_schema),
        "requirements": (),
        "access": module.access,
        "mutability": module.mutability,
    }
    return Capability(**values)


def load_module_capabilities(module_root: Path = BUILTIN_MODULE_ROOT) -> tuple[Capability, ...]:
    try:
        registry = ModuleRegistry.discover(module_root)
    except ModuleRegistryError as exc:
        raise CapabilitySpecificationError("invalid scientific module registry") from exc
    return tuple(_module_capability(module) for module in registry.all())


_MODULE_REGISTRY = ModuleRegistry.discover(BUILTIN_MODULE_ROOT)
_CAPABILITIES = tuple(_module_capability(module) for module in _MODULE_REGISTRY.all())
_REGISTRY = {capability.id: capability for capability in _CAPABILITIES}


def resolve(capability_id: str) -> Capability:
    try:
        return _REGISTRY[capability_id]
    except KeyError:
        raise CapabilityResolutionError(f"unknown capability: {capability_id}") from None


def resolve_entrypoint(capability: Capability) -> Callable[..., object] | Path:
    registered = _REGISTRY.get(capability.id)
    if registered is not None and registered.entrypoint == capability.entrypoint:
        try:
            return _MODULE_REGISTRY.resolve_entrypoint(capability.id)
        except ModuleRegistryError:
            raise CapabilityResolutionError(f"entrypoint cannot be resolved: {capability.id}") from None
    if capability.kind == "workflow" and ":" not in capability.entrypoint:
        path = Path(capability.entrypoint)
        if not path.is_file():
            raise CapabilityResolutionError(f"workflow entrypoint does not exist: {capability.id}")
        return path
    module_name, separator, attribute_name = capability.entrypoint.partition(":")
    if not separator or not module_name or not attribute_name:
        raise CapabilityResolutionError(f"invalid entrypoint for {capability.id}")
    try:
        module = importlib.import_module(module_name)
        entrypoint = getattr(module, attribute_name)
    except (ImportError, AttributeError):
        raise CapabilityResolutionError(f"entrypoint cannot be resolved: {capability.id}") from None
    if not callable(entrypoint):
        raise CapabilityResolutionError(f"entrypoint is not callable: {capability.id}")
    return entrypoint


def all_capabilities() -> tuple[Capability, ...]:
    return _CAPABILITIES


def capability_to_dict(capability: Capability) -> dict[str, object]:
    payload = asdict(capability)
    payload["requirements"] = list(capability.requirements)
    return payload
