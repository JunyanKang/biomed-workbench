"""Filesystem discovery for independent scientific module manifests."""

from __future__ import annotations

import hashlib
import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .contract import ModuleManifest, manifest_to_dict, parse_manifest


class ModuleRegistryError(ValueError):
    """Raised when discovery or resolution violates the module contract."""


@dataclass(frozen=True)
class ModuleRegistry:
    _modules: tuple[ModuleManifest, ...]
    digest: str

    @classmethod
    def discover(cls, root: Path) -> "ModuleRegistry":
        paths = sorted(Path(root).rglob("module.json"))
        if not paths:
            raise ModuleRegistryError("no scientific modules were found")
        modules: dict[str, ModuleManifest] = {}
        for path in paths:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                manifest = parse_manifest(payload)
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                raise ModuleRegistryError(f"invalid module manifest: {path.parent.name}") from exc
            if path.parent.name != manifest.id:
                raise ModuleRegistryError(f"module directory must match manifest id: {manifest.id}")
            if manifest.id in modules:
                raise ModuleRegistryError(f"duplicate module id: {manifest.id}")
            modules[manifest.id] = manifest
        installed = set(modules)
        for manifest in modules.values():
            for alternative in manifest.alternatives:
                if alternative not in installed:
                    raise ModuleRegistryError(f"module {manifest.id} references unknown alternative: {alternative}")
                if alternative == manifest.id:
                    raise ModuleRegistryError(f"module {manifest.id} cannot be its own alternative")
            for complement in manifest.complements:
                if complement not in installed:
                    raise ModuleRegistryError(f"module {manifest.id} references unknown complement: {complement}")
                if complement == manifest.id:
                    raise ModuleRegistryError(f"module {manifest.id} cannot complement itself")
        ordered = tuple(modules[module_id] for module_id in sorted(modules))
        canonical = json.dumps([manifest_to_dict(item) for item in ordered], sort_keys=True, separators=(",", ":"))
        return cls(ordered, hashlib.sha256(canonical.encode("utf-8")).hexdigest())

    def all(self) -> tuple[ModuleManifest, ...]:
        return self._modules

    def get(self, module_id: str) -> ModuleManifest:
        for manifest in self._modules:
            if manifest.id == module_id:
                return manifest
        raise ModuleRegistryError(f"unknown module: {module_id}")

    def search_terms(self, module_id: str) -> tuple[str, ...]:
        manifest = self.get(module_id)
        values = (
            *manifest.intents,
            *manifest.questions,
            *manifest.domains,
            manifest.title,
            manifest.description,
            *(port.artifact_type for port in manifest.input_artifacts),
            *(port.artifact_type for port in manifest.output_artifacts),
        )
        return tuple(dict.fromkeys(value.strip().lower() for value in values if value.strip()))

    def resolve_entrypoint(self, module_id: str) -> Callable[..., object]:
        manifest = self.get(module_id)
        module_name, separator, attribute_name = manifest.entrypoint.partition(":")
        if not separator or not module_name or not attribute_name or attribute_name.startswith("_"):
            raise ModuleRegistryError(f"invalid entrypoint for module: {module_id}")
        try:
            module = importlib.import_module(module_name)
            entrypoint = getattr(module, attribute_name)
        except (ImportError, AttributeError):
            raise ModuleRegistryError(f"entrypoint cannot be resolved: {module_id}") from None
        if not callable(entrypoint):
            raise ModuleRegistryError(f"entrypoint is not callable: {module_id}")
        return entrypoint
