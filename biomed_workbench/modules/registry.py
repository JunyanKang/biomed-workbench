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
            source_inputs = {port.name: port for port in manifest.input_artifacts}
            source_outputs = {port.name: port for port in manifest.output_artifacts}
            source_parameters = set(manifest.input_schema.get("properties", {}))
            for relation in manifest.revision_alternatives:
                if relation.target_module_id not in installed:
                    raise ModuleRegistryError(
                        f"module {manifest.id} references unknown revision alternative: {relation.target_module_id}"
                    )
                if relation.target_module_id not in manifest.alternatives:
                    raise ModuleRegistryError(
                        f"module {manifest.id} revision alternative must also be a routing alternative: {relation.target_module_id}"
                    )
                target = modules[relation.target_module_id]
                target_inputs = {port.name: port for port in target.input_artifacts}
                target_outputs = {port.name: port for port in target.output_artifacts}
                target_parameters = set(target.input_schema.get("properties", {}))
                if set(relation.input_binding_map) - set(target_inputs) or set(relation.input_binding_map.values()) - set(source_inputs):
                    raise ModuleRegistryError(
                        f"module {manifest.id} revision alternative has an unknown input port: {relation.target_module_id}"
                    )
                if any(
                    target_inputs[target_port].artifact_type != source_inputs[source_port].artifact_type
                    for target_port, source_port in relation.input_binding_map.items()
                ):
                    raise ModuleRegistryError(
                        f"module {manifest.id} revision alternative input types differ: {relation.target_module_id}"
                    )
                unmapped_target_ports = set(target_inputs) - set(relation.input_binding_map)
                required_additional_types = tuple(
                    target_inputs[name].artifact_type for name in sorted(unmapped_target_ports)
                )
                if tuple(sorted(relation.required_additional_artifact_types)) != tuple(sorted(required_additional_types)):
                    raise ModuleRegistryError(
                        f"module {manifest.id} revision alternative additional inputs differ from target ports: {relation.target_module_id}"
                    )
                if (
                    set(relation.output_binding_map) != set(source_outputs)
                    or set(relation.output_binding_map.values()) != set(target_outputs)
                    or any(
                        source_outputs[source_port].artifact_type != target_outputs[target_port].artifact_type
                        for source_port, target_port in relation.output_binding_map.items()
                    )
                ):
                    raise ModuleRegistryError(
                        f"module {manifest.id} revision alternative output mapping is not contract-equivalent: {relation.target_module_id}"
                    )
                source_gate_ids = {gate.id for gate in manifest.quality_gates}
                target_gate_ids = {gate.id for gate in target.quality_gates}
                if (
                    relation.scientific_contract_equivalence == "contract-equivalent"
                    and source_gate_ids != target_gate_ids
                ):
                    raise ModuleRegistryError(
                        f"module {manifest.id} contract-equivalent revision has different quality gates: {relation.target_module_id}"
                    )
                if (
                    set(relation.parameter_mapping) != set(target_parameters)
                    or set(relation.parameter_mapping.values()) - source_parameters
                ):
                    raise ModuleRegistryError(
                        f"module {manifest.id} revision alternative parameter mapping is incomplete: {relation.target_module_id}"
                    )
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
        if manifest.agent_protocol is not None:
            from ..capabilities.agent_analysis import prepare_agent_analysis

            return lambda **inputs: prepare_agent_analysis(manifest, inputs)
        if manifest.execution.kind == "command" and manifest.entrypoint == "scientific-command":
            from .scientific_command import execute_scientific_command

            return execute_scientific_command
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
