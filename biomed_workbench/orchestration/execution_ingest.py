"""Validated re-entry for externally observed packaged workflow executions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ..kernel.artifact_store import ProjectArtifactStore
from ..kernel.execution_receipts import ArtifactReloadReceipt, ObservedExecutionReceipt, ScientificReviewReceipt
from ..kernel.identity import digest_value
from ..kernel.state import ProjectState, apply_event
from ..modules.registry import ModuleRegistry
from ..runner import validate_schema_value
from .execution import _output_artifacts


_BUNDLE_FIELDS = {"handoff_id", "process_exit_code", "runtime_versions", "outputs", "postflight_finding_ids"}
_OUTPUT_FIELDS = {"port", "content", "payload_files", "quality_status"}


def ingest_execution_bundle(
    state: ProjectState,
    bundle: Mapping[str, Any],
    *,
    registry: ModuleRegistry,
    artifact_store: ProjectArtifactStore,
) -> ProjectState:
    """Create all receipt identities from one handoff and imported observed outputs."""
    if set(bundle) != _BUNDLE_FIELDS:
        raise ValueError("execution receipt bundle fields are incomplete or unsupported")
    handoff = next((item for item in state.execution_handoffs if item.id == bundle["handoff_id"]), None)
    if handoff is None:
        raise ValueError("execution receipt bundle references an unknown handoff")
    if any(item.handoff_id == handoff.id for item in state.observed_executions):
        raise ValueError("execution handoff has already been observed")
    plan = next((item for item in state.plans if any(node.id == handoff.plan_node_id for node in item.nodes)), None)
    if plan is None:
        raise ValueError("execution handoff plan is unavailable")
    node = next(item for item in plan.nodes if item.id == handoff.plan_node_id)
    if node.status != "awaiting_observed_execution":
        raise ValueError("execution handoff is not awaiting observed completion")
    manifest = registry.get(handoff.module_id)
    if manifest.version != handoff.module_version or manifest.access != "agent_generated":
        raise ValueError("execution handoff module contract is unavailable or no longer matches")
    runtime_versions = bundle["runtime_versions"]
    if not isinstance(runtime_versions, Mapping) or not runtime_versions:
        raise ValueError("execution receipt bundle requires observed runtime versions")
    outputs = bundle["outputs"]
    if not isinstance(outputs, list) or any(not isinstance(item, Mapping) or set(item) != _OUTPUT_FIELDS for item in outputs):
        raise ValueError("execution receipt bundle outputs are invalid")
    by_port = {str(item["port"]): item for item in outputs}
    expected_ports = {port.name for port in manifest.output_artifacts}
    if set(by_port) != expected_ports or len(outputs) != len(by_port):
        raise ValueError("execution receipt bundle must cover every output port exactly once")
    payloads_by_port = {}
    content_by_port = {}
    for port in manifest.output_artifacts:
        item = by_port[port.name]
        if item["quality_status"] not in {"passed", "warning"}:
            raise ValueError("observed output quality status must be passed or warning")
        if not isinstance(item["content"], Mapping):
            raise ValueError("observed output content must be an object")
        content_by_port[port.name] = dict(item["content"])
        payload_files = item["payload_files"]
        if not isinstance(payload_files, list):
            raise ValueError("observed output payload_files must be an array")
        imported = []
        for payload in payload_files:
            if not isinstance(payload, Mapping) or set(payload) != {"role", "path", "media_type"}:
                raise ValueError("observed payload file requires role, path, and media_type")
            imported.append(
                artifact_store.import_file(
                    Path(str(payload["path"])),
                    role=str(payload["role"]),
                    media_type=str(payload["media_type"]),
                )
            )
        payloads_by_port[port.name] = tuple(imported)
    normalized_output = next(iter(content_by_port.values())) if len(content_by_port) == 1 else content_by_port
    schema_properties = manifest.output_schema.get("properties", {})
    if not isinstance(schema_properties, Mapping) or "handoff_type" not in schema_properties:
        validate_schema_value(manifest.output_schema, normalized_output, "observed output")
    provenance = {
        "module_id": manifest.id,
        "module_version": manifest.version,
        "compatibility_row_id": handoff.compatibility_row_id,
        "tools": {str(key): str(value) for key, value in runtime_versions.items()},
        "dependencies": {},
        "parameters_digest": handoff.request_digest,
        "output_digest": digest_value(normalized_output),
    }
    artifacts = _output_artifacts(
        state,
        node,
        manifest,
        normalized_output,
        provenance,
        (),
        payloads_by_port,
    )
    observed = ObservedExecutionReceipt.create(
        plan_node_id=node.id,
        module_id=manifest.id,
        module_version=manifest.version,
        compatibility_row_id=handoff.compatibility_row_id,
        parameters_digest=handoff.request_digest,
        runtime_versions={str(key): str(value) for key, value in runtime_versions.items()},
        output_artifact_digests={artifact.id: artifact.content_digest for artifact in artifacts},
        process_exit_code=int(bundle["process_exit_code"]),
        source_kind="handoff",
        execution_request_digest=digest_value(handoff.to_dict()),
        handoff=handoff,
    )
    state = apply_event(
        state,
        "execution_observed",
        {"receipt": observed.to_dict()},
        rationale="Ingest observed completion for the exact packaged execution handoff.",
        affected_hypothesis_ids=node.target_hypothesis_ids,
        replacement_action_ids=(node.id,),
    )
    reloads = []
    for artifact in artifacts:
        receipt = ArtifactReloadReceipt.create(
            observed_execution=observed,
            artifact_id=artifact.id,
            payload_digests={payload.role: payload.sha256 for payload in artifact.payloads},
            output_schema_valid=True,
            content_digest=artifact.content_digest,
        )
        state = apply_event(
            state,
            "artifact_reloaded",
            {"receipt": receipt.to_dict(), "artifact": artifact.to_dict()},
            rationale="Import and reload one observed packaged-workflow output before scientific review.",
            affected_artifact_ids=(artifact.id,),
            affected_hypothesis_ids=node.target_hypothesis_ids,
            replacement_action_ids=(node.id,),
        )
        reloads.append(receipt)
    finding_ids = tuple(str(value) for value in bundle["postflight_finding_ids"])
    integrity = ScientificReviewReceipt.create(
        observed_execution=observed,
        reload_receipts=tuple(reloads),
        finding_ids=finding_ids,
    )
    state = apply_event(
        state,
        "execution_reviewed",
        {"receipt": integrity.to_dict()},
        rationale="Accept the complete packaged-workflow execution and reload chain for scientific artifact review.",
        trigger_finding_ids=integrity.finding_ids,
        affected_artifact_ids=tuple(item.id for item in artifacts),
        affected_hypothesis_ids=node.target_hypothesis_ids,
        replacement_action_ids=(node.id,),
    )
    return apply_event(
        state,
        "node_status_changed",
        {"plan_id": plan.id, "node_id": node.id, "status": "awaiting_review", "attempt": node.attempt},
        rationale="Release reloaded outputs to bilingual scientific artifact review.",
        replacement_action_ids=(node.id,),
    )
