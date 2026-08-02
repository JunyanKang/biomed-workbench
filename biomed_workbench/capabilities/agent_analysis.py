"""Deterministic execution plans for packaged, parameterized analyses."""

from __future__ import annotations

from typing import Any

from ..kernel.identity import digest_value
from ..modules.contract import ModuleManifest


def prepare_agent_analysis(manifest: ModuleManifest, inputs: dict[str, Any]) -> dict[str, Any]:
    """Serialize a module-owned, no-code-edit execution and validation protocol."""
    protocol = manifest.agent_protocol
    if manifest.access != "agent_generated" or manifest.execution.kind != "workflow" or protocol is None:
        raise ValueError("module is not an agent-generated analysis protocol")
    tool_profiles = [
        {
            "name": item.name,
            "identity": item.identity,
            "tested_versions": list(item.tested_versions),
            "allowed_versions": list(item.allowed_versions),
            "mismatch_policy": item.mismatch_policy,
            "version_differences": [
                {
                    "id": difference.id,
                    "affected_versions": list(difference.affected_versions),
                    "required_action": difference.required_action,
                }
                for difference in item.version_differences
            ],
        }
        for item in manifest.tool_requirements
    ]
    dependency_profiles = [
        {
            "name": item.name,
            "identity": item.identity,
            "tested_versions": list(item.tested_versions),
            "allowed_versions": list(item.allowed_versions),
            "conflicts": [
                {
                    "dependency": conflict.dependency,
                    "versions": list(conflict.versions),
                    "required_action": conflict.required_action,
                }
                for conflict in item.conflicts
            ],
        }
        for item in manifest.dependencies
    ]
    return {
        "handoff_type": "packaged_parameterized_project_analysis",
        "module": {"id": manifest.id, "version": manifest.version},
        "request_digest": digest_value(inputs),
        "request_fields": sorted(inputs),
        "languages": list(protocol.languages),
        "code_plan": [
            {
                "id": section.id,
                "purpose": section.purpose,
                "required_logic": list(section.required_logic),
                "output_artifact_types": list(section.output_artifact_types),
                "template_files": list(section.template_files),
                "manual_code_editing_required": False,
            }
            for section in protocol.template_sections
        ],
        "parameter_rules": [
            {
                "id": rule.id,
                "parameter": rule.parameter,
                "decision_inputs": list(rule.decision_inputs),
                "selection_rule": rule.selection_rule,
                "validation_rule": rule.validation_rule,
            }
            for rule in protocol.parameter_rules
        ],
        "preflight_checks": list(protocol.preflight_checks),
        "postflight_checks": list(protocol.postflight_checks),
        "provenance_fields": list(protocol.provenance_fields),
        "forbidden_actions": list(protocol.forbidden_actions),
        "tool_profiles": tool_profiles,
        "dependency_profiles": dependency_profiles,
        "quality_gate_ids": [gate.id for gate in manifest.quality_gates],
        "execution_policy": {
            "generate_project_specific_code": False,
            "use_packaged_parameterized_templates": True,
            "manual_code_editing_required": False,
            "inspect_before_execution": True,
            "execute_in_user_scientific_environment": True,
            "manage_environment_or_compute_infrastructure": False,
            "observed_execution_required": protocol.requires_observed_execution,
            "planned_output_is_not_evidence": True,
        },
    }
