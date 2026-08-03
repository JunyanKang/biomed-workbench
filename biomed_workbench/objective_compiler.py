"""Compile one selected manifest set into the single authoritative objective graph."""

from __future__ import annotations

import re
from typing import Any

from .modules.contract import ModuleManifest


def ports_compatible(produced, required) -> bool:
    if produced.artifact_type != required.artifact_type:
        return False
    for output_format in produced.formats:
        for input_format in required.formats:
            if output_format.name != input_format.name or not set(output_format.versions) & set(input_format.versions):
                continue
            if not set(output_format.compression) & set(input_format.compression):
                continue
            if not set(output_format.orientations) & set(input_format.orientations):
                continue
            if input_format.coordinate_systems and not set(output_format.coordinate_systems) & set(input_format.coordinate_systems):
                continue
            if input_format.genome_build_policy != "not_applicable" and not set(output_format.genome_builds) & set(input_format.genome_builds):
                continue
            if input_format.annotation_releases and not set(output_format.annotation_releases) & set(input_format.annotation_releases):
                continue
            return True
    return False


def _port_bindings(selected: tuple[ModuleManifest, ...]) -> dict[str, dict[str, str]]:
    position = {module.id: index for index, module in enumerate(selected)}
    bindings: dict[str, dict[str, str]] = {}
    for consumer in selected:
        bound = {}
        for port in consumer.input_artifacts:
            candidates = [
                producer
                for producer in selected
                if producer.id != consumer.id
                and position[producer.id] < position[consumer.id]
                and any(ports_compatible(output, port) for output in producer.output_artifacts)
            ]
            if candidates:
                bound[port.name] = candidates[-1].id
        bindings[consumer.id] = bound
    return bindings


def _dependencies(objective: str, selected: tuple[ModuleManifest, ...], bindings: dict[str, dict[str, str]]) -> dict[str, tuple[str, ...]]:
    dependencies = {
        module.id: set(bindings[module.id].values())
        for module in selected
    }
    non_publication = {module.id for module in selected if module.domains[0] != "publication"}
    if non_publication:
        for module in selected:
            if module.domains[0] == "publication":
                dependencies[module.id].update(non_publication)
    normalized = objective.lower()
    parallel_requested = bool(re.search(r"\b(?:parallel|concurrently|independently|separately)\b|并行|独立|分别", normalized))
    sequential_requested = bool(re.search(r"\b(?:then|finally|subsequently|followed by)\b|然后|最后|随后|再进行|后用|之后", normalized))
    if sequential_requested and not parallel_requested:
        def mention_position(module: ModuleManifest) -> tuple[int, int]:
            positions = [normalized.find(alias.lower()) for alias in module.routing.method_aliases]
            observed = [value for value in positions if value >= 0]
            return (min(observed) if observed else len(normalized), selected.index(module))

        ordered = sorted(selected, key=mention_position)
        for index, module in enumerate(ordered[1:], start=1):
            upstream_id = ordered[index - 1].id
            stack = [upstream_id]
            seen = set()
            while stack:
                current = stack.pop()
                if current in seen:
                    continue
                seen.add(current)
                stack.extend(dependencies.get(current, ()))
            if module.id not in seen:
                dependencies[module.id].add(upstream_id)
    return {module_id: tuple(sorted(values)) for module_id, values in dependencies.items()}


def _layers(selected: tuple[ModuleManifest, ...], dependencies: dict[str, tuple[str, ...]]) -> list[dict[str, object]]:
    remaining = {module.id: set(dependencies[module.id]) for module in selected}
    order = {module.id: index for index, module in enumerate(selected)}
    layers = []
    while remaining:
        ready = sorted((module_id for module_id, needs in remaining.items() if not needs), key=order.__getitem__)
        if not ready:
            raise ValueError("selected manifest orchestration metadata contains a dependency cycle")
        layers.append({"mode": "parallel" if len(ready) > 1 else "serial", "module_ids": ready})
        for module_id in ready:
            del remaining[module_id]
        for needs in remaining.values():
            needs.difference_update(ready)
    return layers


def _plan_type(layers: list[dict[str, object]]) -> str:
    if len(layers) == 1 and len(layers[0]["module_ids"]) == 1:
        return "single"
    if len(layers) == 1:
        return "parallel"
    if any(len(layer["module_ids"]) > 1 for layer in layers):
        return "mixed"
    return "serial"


def compile_objective(objective: str, selected: tuple[ModuleManifest, ...]) -> dict[str, Any]:
    """Return the one graph consumed by both routing and execution-plan views."""
    if not objective.strip() or not selected:
        raise ValueError("objective compilation requires an objective and selected modules")
    bindings = _port_bindings(selected)
    dependencies = _dependencies(objective, selected, bindings)
    layers = _layers(selected, dependencies)
    return {
        "objective": objective,
        "selected_module_ids": [module.id for module in selected],
        "port_bindings": bindings,
        "dependencies": {key: list(value) for key, value in dependencies.items()},
        "execution_layers": layers,
        "plan_type": _plan_type(layers),
    }
