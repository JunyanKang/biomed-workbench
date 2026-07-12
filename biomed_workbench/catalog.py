"""Backward-compatible capability projection of the scientific module registry."""

from __future__ import annotations

import importlib
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from .models import Capability
from .modules.index import BUILTIN_ROOT
from .modules.registry import ModuleRegistry, ModuleRegistryError


BUILTIN_MODULE_ROOT = BUILTIN_ROOT


class CapabilityResolutionError(LookupError):
    """Raised when a capability ID or entrypoint cannot be resolved."""


class ModuleCatalogError(ValueError):
    """Raised when modules cannot be projected onto the v0.2 capability API."""


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
        raise ModuleCatalogError("invalid scientific module registry") from exc
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
