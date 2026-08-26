"""Compile a natural-language objective into an agent-ready scientific run plan."""

from __future__ import annotations

from typing import Any

from .modules.contract import ArtifactPort, ModuleManifest
from .modules.index import BUILTIN_ROOT
from .modules.registry import ModuleRegistry
from .router import route


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


def _evidence_contract(module: ModuleManifest) -> dict[str, object]:
    return {
        "module_version": module.version,
        "compatibility_row_ids": [row.id for row in module.compatibility_matrix],
        "regression_evidence_ids": sorted(
            {evidence_id for row in module.compatibility_matrix for evidence_id in row.regression_evidence_ids}
        ),
        "end_to_end_evidence_ids": sorted(
            {evidence_id for row in module.compatibility_matrix for evidence_id in row.end_to_end_evidence_ids}
        ),
        "required_tool_identities": [tool.identity for tool in module.tool_requirements if tool.required],
        "required_dependency_identities": [dependency.identity for dependency in module.dependencies if dependency.required],
        "provenance_fields": (
            list(module.agent_protocol.provenance_fields)
            if module.agent_protocol is not None
            else [
                "input-artifact-digest",
                "module-version",
                "template-digest",
                "actual-tool-versions",
                "quality-gate-results",
            ]
        ),
        "claim_level": module.maturity,
    }


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
    candidate_ids = tuple(dict.fromkeys(routed["selected_module_ids"]))
    execution_ids = tuple(dict.fromkeys(routed.get("execution_module_ids", candidate_ids)))
    selected_ids = candidate_ids
    selected = tuple(active.get(module_id) for module_id in selected_ids)
    objective_graph = routed["objective_graph"]
    port_bindings = {module_id: dict(values) for module_id, values in objective_graph["port_bindings"].items()}
    dependencies = {module_id: tuple(values) for module_id, values in objective_graph["dependencies"].items()}
    execution_layers = objective_graph["execution_layers"]
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
                "version": module.version,
                "title": module.title,
                "domain": module.domains[0],
                "registry_contract_label": module.maturity,
                "registry_contract_label_is_scientific_completion": False,
                "validation_scope": next(
                    (
                        candidate["validation_scope"]
                        for step in routed["steps"]
                        for candidate in step["candidates"]
                        if candidate["id"] == module.id
                    ),
                    {"engineering_validated": None, "method_validated": None, "project_promoted": False},
                ),
                "access": module.access,
                "depends_on": list(dependencies[module.id]),
                "compatibility_row_ids": [row.id for row in module.compatibility_matrix],
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
                "evidence_contract": _evidence_contract(module),
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
        "schema_version": 2,
        "objective": objective,
        "plan_type": objective_graph["plan_type"],
        "matched_workflows": routed["matched_workflows"],
        "selected_module_ids": list(selected_ids),
        "semantically_eligible_module_ids": list(candidate_ids),
        "execution_module_ids": list(execution_ids),
        "minimal_sufficient_analysis": routed.get("minimal_sufficient_analysis"),
        "execution_layers": execution_layers,
        "minimal_execution_layers": (
            routed["execution_graph"]["execution_layers"]
            if routed.get("execution_graph") is not None
            else []
        ),
        "modules": modules,
        "unresolved_project_inputs": unresolved_inputs,
        "unresolved_required_inputs": unresolved_required_inputs,
        "execution_boundary": (
            "This is an agent-ready plan, not an execution record. Codex must inspect real project inputs, "
            "validate every declared contract, and record observed results before scientific interpretation."
        ),
    }
