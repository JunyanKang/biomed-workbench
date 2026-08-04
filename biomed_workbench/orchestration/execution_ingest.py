"""Validated re-entry for externally observed packaged workflow executions."""

from __future__ import annotations

import importlib
import hashlib
from pathlib import Path
from typing import Any, Mapping

from ..kernel.artifact_store import ProjectArtifactStore
from ..kernel.execution_receipts import ArtifactReloadReceipt, ObservedExecutionReceipt, ScientificReviewReceipt
from ..kernel.identity import digest_value
from ..kernel.state import ProjectState, apply_event
from ..modules.registry import ModuleRegistry
from ..modules.contract import ObservedOutputContract, observed_output_contract_digest
from ..runner import validate_schema_value
from .execution import _output_artifacts


_BUNDLE_FIELDS = {"handoff_id", "process_exit_code", "runtime_versions", "outputs", "postflight_results"}
_OUTPUT_FIELDS = {"port", "content", "payload_files"}
_POSTFLIGHT_FIELDS = {"gate_id"}


def _reload_validator(identifier: str):
    module_name, function_name = identifier.split(":", 1)
    if not module_name.startswith("biomed_workbench."):
        raise ValueError("reload validator must be packaged inside biomed_workbench")
    function = getattr(importlib.import_module(module_name), function_name)
    if not callable(function):
        raise ValueError("reload validator entrypoint is not callable")
    return function


def _validator_source_sha256(identifier: str) -> str:
    module_name, _ = identifier.split(":", 1)
    module = importlib.import_module(module_name)
    source_path = Path(str(getattr(module, "__file__", "")))
    if not source_path.is_file() or source_path.suffix != ".py":
        raise ValueError("semantic validator must resolve to packaged Python source")
    return hashlib.sha256(source_path.read_bytes()).hexdigest()


def _validate_payload_contract(
    contract: ObservedOutputContract,
    payload_files: object,
) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(payload_files, list):
        raise ValueError("observed output payload_files must be an array")
    payloads = tuple(payload_files)
    if any(not isinstance(item, Mapping) or set(item) != {"role", "path", "media_type"} for item in payloads):
        raise ValueError("observed payload file requires role, path, and media_type")
    by_role = {item.role: item for item in contract.payloads}
    supplied_roles = [str(item["role"]) for item in payloads]
    if len(set(supplied_roles)) != len(supplied_roles) or not set(supplied_roles) <= set(by_role):
        raise ValueError("observed payload roles are duplicate or outside the output contract")
    for role, role_contract in by_role.items():
        count = supplied_roles.count(role)
        if not role_contract.minimum <= count <= role_contract.maximum:
            raise ValueError(f"observed payload role cardinality failed for {role}")
    for item in payloads:
        role_contract = by_role[str(item["role"])]
        if item["media_type"] not in role_contract.media_types:
            raise ValueError(f"observed payload media type is invalid for role {item['role']}")
    return payloads


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
    current_contract_digest = observed_output_contract_digest(manifest)
    if handoff.observed_output_contract_digest != current_contract_digest:
        raise ValueError("observed output contract changed after the execution handoff")
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
    contracts = {item.port: item for item in manifest.observed_output_contracts}
    row = next(item for item in manifest.compatibility_matrix if item.id == handoff.compatibility_row_id)
    for port in manifest.output_artifacts:
        item = by_port[port.name]
        if not isinstance(item["content"], Mapping):
            raise ValueError("observed output content must be an object")
        contract = contracts[port.name]
        content = dict(item["content"])
        validate_schema_value(contract.content_schema, content, f"observed output {port.name}")
        expected_formats = {
            str(value).split("@", 1)[0]
            for value in row.output_formats[port.name]
        }
        provenance = content["provenance"]
        workflow = provenance["workflow"]
        if (
            content["artifact_type"] != port.artifact_type
            or content["format"] not in expected_formats
            or provenance["parameters_digest"] != handoff.request_digest
            or provenance["compatibility_row_id"] != handoff.compatibility_row_id
            or workflow not in runtime_versions
            or provenance["workflow_version"] != runtime_versions[workflow]
        ):
            raise ValueError("observed output identity or provenance differs from the prepared contract")
        content_by_port[port.name] = content
        payload_files = _validate_payload_contract(contract, item["payload_files"])
        imported = []
        for payload in payload_files:
            imported.append(
                artifact_store.import_file(
                    Path(str(payload["path"])),
                    role=str(payload["role"]),
                    media_type=str(payload["media_type"]),
                )
            )
        payloads_by_port[port.name] = tuple(imported)
        reloaded_payloads = tuple(
            {
                **payload.to_dict(),
                "path": str(artifact_store.resolve(payload)),
            }
            for payload in payloads_by_port[port.name]
        )
        accepted = _reload_validator(contract.container_reload_validator)(
            content=content,
            payloads=reloaded_payloads,
            context={"module_id": manifest.id, "module_version": manifest.version, "port": port.name},
        )
        if accepted is not True:
            raise ValueError(f"observed output container reload validator rejected port {port.name}")
        if _validator_source_sha256(contract.semantic_validator) != contract.semantic_validator_sha256:
            raise ValueError(f"semantic validator source digest differs from the frozen contract for port {port.name}")
        accepted = _reload_validator(contract.semantic_validator)(
                content=content,
                payloads=reloaded_payloads,
                context={"module_id": manifest.id, "module_version": manifest.version, "port": port.name},
                profile=contract.semantic_profile,
        )
        if accepted is not True:
            raise ValueError(f"observed output semantic validator rejected port {port.name}")
    normalized_output = next(iter(content_by_port.values())) if len(content_by_port) == 1 else content_by_port
    postflight_results = bundle["postflight_results"]
    if not isinstance(postflight_results, list) or any(
        not isinstance(item, Mapping) or set(item) != _POSTFLIGHT_FIELDS for item in postflight_results
    ):
        raise ValueError("execution receipt bundle postflight results are invalid")
    by_gate = {str(item["gate_id"]): item for item in postflight_results}
    required_gate_ids = {
        gate_id
        for contract in manifest.observed_output_contracts
        for gate_id in contract.required_postflight_gate_ids
    }
    if len(by_gate) != len(postflight_results) or set(by_gate) != required_gate_ids:
        raise ValueError("postflight results must cover every required manifest gate exactly once")
    evaluated_results: dict[str, dict[str, object]] = {}
    for gate_id in sorted(by_gate):
        evaluations = []
        for contract in manifest.observed_output_contracts:
            evaluator = next(item for item in contract.gate_evaluators if item.gate_id == gate_id)
            payloads = tuple(
                {
                    **payload.to_dict(),
                    "path": str(artifact_store.resolve(payload)),
                }
                for payload in payloads_by_port[contract.port]
            )
            result = _reload_validator(evaluator.evaluator)(
                payloads=payloads,
                metric_key=evaluator.metric_key,
                metric_type=evaluator.metric_type,
                operator=evaluator.operator,
                threshold=evaluator.threshold,
            )
            if not isinstance(result, Mapping) or set(result) != {
                "status", "observed_metric", "threshold", "evidence_payload_sha256"
            }:
                raise ValueError(f"packaged gate evaluator returned an invalid result: {gate_id}")
            if result["status"] != "passed":
                raise ValueError(f"required postflight gate did not pass: {gate_id}")
            evaluations.append({"port": contract.port, **dict(result)})
        evaluated_results[gate_id] = {
            "gate_id": gate_id,
            "evaluations": evaluations,
            "status": "passed",
        }
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
        observed_output_contract_digest=current_contract_digest,
        parameters_digest=handoff.request_digest,
        runtime_versions={str(key): str(value) for key, value in runtime_versions.items()},
        output_artifact_digests={artifact.id: artifact.content_digest for artifact in artifacts},
        postflight_result_digests={gate_id: digest_value(result) for gate_id, result in evaluated_results.items()},
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
    contract_by_artifact_id = {
        node.planned_output_artifact_ids[port.name]: contracts[port.name]
        for port in manifest.output_artifacts
    }
    for artifact in artifacts:
        contract = contract_by_artifact_id[artifact.id]
        validator_identity = digest_value(
            {
                "container": contract.container_reload_validator,
                "semantic": contract.semantic_validator,
                "semantic_sha256": contract.semantic_validator_sha256,
            }
        )
        receipt = ArtifactReloadReceipt.create(
            observed_execution=observed,
            artifact_id=artifact.id,
            payload_digests={payload.role: payload.sha256 for payload in artifact.payloads},
            observed_output_contract_digest=current_contract_digest,
            reload_validator_id=f"validator-{validator_identity[:24]}",
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
    integrity = ScientificReviewReceipt.create(
        observed_execution=observed,
        reload_receipts=tuple(reloads),
        finding_ids=(),
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
