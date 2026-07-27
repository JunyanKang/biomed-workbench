"""Compile a natural-language objective into an agent-ready scientific run plan."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .modules.contract import ArtifactPort, ModuleManifest
from .modules.index import BUILTIN_ROOT
from .modules.registry import ModuleRegistry
from .router import ports_compatible, route


def _format_tokens(port: ArtifactPort) -> list[str]:
    return sorted(
        f"{format_contract.name}@{version}"
        for format_contract in port.formats
        for version in format_contract.versions
    )


def _port_summary(port: ArtifactPort) -> dict[str, object]:
    return {
        "name": port.name,
        "artifact_type": port.artifact_type,
        "source_policy": port.source_policy,
        "accepted_formats": _format_tokens(port),
        "processing_levels": list(port.processing_levels),
        "required_metadata": list(port.required_metadata),
    }


def _execution_templates(module: ModuleManifest) -> list[dict[str, object]]:
    templates = [
        {
            "kind": "code_template",
            "path": template.path,
            "language": template.language,
            "purpose": template.purpose,
            "quality_gate_ids": list(template.quality_gate_ids),
            "requires_adaptation": template.requires_adaptation,
        }
        for template in module.code_templates
    ]
    if module.agent_protocol is not None:
        templates.extend(
            {
                "kind": "agent_protocol_section",
                "id": section.id,
                "purpose": section.purpose,
                "template_files": list(section.template_files),
                "required_logic": list(section.required_logic),
                "output_artifact_types": list(section.output_artifact_types),
            }
            for section in module.agent_protocol.template_sections
        )
    return templates


def _port_bindings(selected: tuple[ModuleManifest, ...]) -> dict[str, dict[str, str]]:
    """Bind compatible selected producers to consumer ports in a routed plan."""
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


def _dependencies(bindings: dict[str, dict[str, str]]) -> dict[str, tuple[str, ...]]:
    return {
        module_id: tuple(dict.fromkeys(port_bindings.values()))
        for module_id, port_bindings in bindings.items()
    }


def _layers(selected: tuple[ModuleManifest, ...], dependencies: dict[str, tuple[str, ...]]) -> list[dict[str, object]]:
    remaining = {module.id: set(dependencies[module.id]) for module in selected}
    order = {module.id: index for index, module in enumerate(selected)}
    layers = []
    while remaining:
        ready = sorted((module_id for module_id, needs in remaining.items() if not needs), key=order.__getitem__)
        if not ready:
            raise ValueError("selected module contracts contain a dependency cycle")
        layers.append({"mode": "parallel" if len(ready) > 1 else "serial", "module_ids": ready})
        deltas = set(ready)
        for module_id in ready:
            del remaining[module_id]
        for needs in remaining.values():
            needs.difference_update(deltas)
    return layers


def compile_research_plan(
    objective: str,
    *,
    per_workflow: int = 3,
    registry: ModuleRegistry | None = None,
) -> dict[str, Any]:
    """Return the bounded, non-evidentiary execution briefing for one objective.

    This bridges natural-language routing and actual Codex-led execution. It
    intentionally does not invent project artifacts, parameters, environment
    versions, or scientific conclusions.
    """
    active = registry or ModuleRegistry.discover(BUILTIN_ROOT)
    routed = route(objective, per_workflow=per_workflow, registry=active)
    selected_ids = tuple(dict.fromkeys(routed["selected_module_ids"]))
    selected = tuple(active.get(module_id) for module_id in selected_ids)
    port_bindings = _port_bindings(selected)
    dependencies = _dependencies(port_bindings)
    candidate_reasons = {
        candidate["id"]: candidate["selection_reasons"]
        for step in routed["steps"]
        for candidate in step["candidates"]
        if candidate["id"] in selected_ids
    }
    modules = []
    unresolved_inputs = []
    unresolved_required_inputs = []
    for module in selected:
        bound_port_names = set(port_bindings[module.id])
        project_inputs = [
            port
            for port in module.input_artifacts
            if port.name not in bound_port_names and port.source_policy != "upstream_required"
        ]
        upstream_inputs = [port for port in module.input_artifacts if port.name in bound_port_names or port.source_policy == "upstream_required"]

        def input_summary(port: ArtifactPort) -> dict[str, object]:
            summary = _port_summary(port)
            producer_id = port_bindings[module.id].get(port.name)
            if producer_id is not None:
                summary["selected_upstream_module_id"] = producer_id
            return summary

        modules.append(
            {
                "id": module.id,
                "title": module.title,
                "domain": module.domains[0],
                "maturity": module.maturity,
                "access": module.access,
                "depends_on": list(dependencies[module.id]),
                "selection_reasons": candidate_reasons.get(module.id, []),
                "project_inputs": [input_summary(port) for port in project_inputs],
                "upstream_inputs": [input_summary(port) for port in upstream_inputs],
                "outputs": [_port_summary(port) for port in module.output_artifacts],
                "quality_gate_ids": [gate.id for gate in module.quality_gates],
                "optional_credentials": list(module.credentials),
                "execution": {
                    "kind": module.execution.kind,
                    "timeout_seconds": module.execution.timeout_seconds,
                    "max_output_bytes": module.execution.max_output_bytes,
                },
                "input_schema": module.input_schema,
                "execution_templates": _execution_templates(module),
            }
        )
        for port in project_inputs:
            unresolved_inputs.append({"module_id": module.id, **_port_summary(port)})
        for port in module.input_artifacts:
            if port.name in bound_port_names:
                continue
            unresolved_required_inputs.append(
                {
                    "module_id": module.id,
                    **_port_summary(port),
                    "resolution": (
                        "missing_selected_upstream_producer"
                        if port.source_policy == "upstream_required"
                        else "project_artifact_required"
                    ),
                }
            )
    return {
        "schema_version": 1,
        "objective": objective,
        "plan_type": routed["plan_type"],
        "matched_workflows": routed["matched_workflows"],
        "selected_module_ids": list(selected_ids),
        "execution_layers": _layers(selected, dependencies),
        "modules": modules,
        "unresolved_project_inputs": unresolved_inputs,
        "unresolved_required_inputs": unresolved_required_inputs,
        "execution_boundary": (
            "This is an agent-ready plan, not an execution record. Codex must inspect real project inputs, "
            "validate every declared contract, and record observed results before scientific interpretation."
        ),
    }
