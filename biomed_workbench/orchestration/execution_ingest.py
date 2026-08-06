"""Validated re-entry for externally observed packaged workflow executions."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Mapping

from ..kernel.artifact_store import ProjectArtifactStore
from ..kernel.execution_chain import automatic_failed_gate_adjudication
from ..kernel.execution_receipts import ArtifactReloadReceipt, ObservedExecutionReceipt, ScientificReviewReceipt
from ..kernel.identity import digest_value
from ..kernel.observed_output_protocol import (
    validate_handoff_receipt_gate_coverage,
    validate_observed_output_protocol,
)
from ..kernel.state import ProjectState, apply_event
from ..modules.registry import ModuleRegistry
from ..modules.contract import (
    ModuleManifest,
    ObservedOutputContract,
    CompatibilityRow,
    compatibility_contract_digest,
    GATE_EVALUATOR_CONTRACT_VERSION,
    observed_output_contract_digest,
    observed_output_protocol_version,
    packaged_callable_source_sha256,
    version_is_allowed,
)
from ..runner import validate_schema_value
from .execution import _output_artifacts


_BUNDLE_FIELDS = {"handoff_id", "process_exit_code", "runtime_versions", "outputs", "postflight_results"}
_OUTPUT_FIELDS = {"port", "content", "payload_files"}
_POSTFLIGHT_FIELDS = {"gate_id"}
_RUNTIME_FIELDS = {
    "workflow",
    "tools",
    "dependencies",
    "version_policy",
    "compatibility_contract_digest",
}
_WORKFLOW_FIELDS = {"identity", "version"}


def _validate_runtime_versions(
    manifest: ModuleManifest,
    row: CompatibilityRow,
    handoff: object,
    value: object,
) -> tuple[dict[str, str], dict[str, str], dict[str, str], str, str]:
    """Require the complete observed runtime to satisfy the frozen compatibility row."""
    if not isinstance(value, Mapping) or set(value) != _RUNTIME_FIELDS:
        raise ValueError("runtime_versions must contain workflow, tools, dependencies, policy, and contract digest")
    workflow = value["workflow"]
    tools = value["tools"]
    dependencies = value["dependencies"]
    policy = value["version_policy"]
    contract_digest = value["compatibility_contract_digest"]
    if not isinstance(workflow, Mapping) or set(workflow) != _WORKFLOW_FIELDS:
        raise ValueError("runtime workflow identity and version are required")
    if not isinstance(tools, Mapping) or not isinstance(dependencies, Mapping):
        raise ValueError("runtime tools and dependencies must be version mappings")
    tool_versions = {str(key): str(observed) for key, observed in tools.items()}
    dependency_versions = {str(key): str(observed) for key, observed in dependencies.items()}
    if set(tool_versions) != set(row.tool_versions):
        raise ValueError("runtime tools must exactly cover the selected compatibility row")
    if set(dependency_versions) != set(row.dependency_versions):
        raise ValueError("runtime dependencies must exactly cover the selected compatibility row")
    for name, rules in row.tool_versions.items():
        if not version_is_allowed(tool_versions[name], rules):
            raise ValueError(f"runtime tool version is outside the selected compatibility row: {name}")
    for name, rules in row.dependency_versions.items():
        if not version_is_allowed(dependency_versions[name], rules):
            raise ValueError(f"runtime dependency version is outside the selected compatibility row: {name}")
    if policy not in {"tested", "compatible"}:
        raise ValueError("runtime version_policy must be tested or compatible")
    requirement_tools = {item.name: item for item in manifest.tool_requirements}
    requirement_dependencies = {item.name: item for item in manifest.dependencies}
    if policy == "tested":
        if not set(tool_versions) <= set(requirement_tools) or not set(dependency_versions) <= set(
            requirement_dependencies
        ):
            raise ValueError("tested runtime policy references an undeclared tool or dependency")
        if any(tool_versions[name] not in requirement_tools[name].tested_versions for name in tool_versions):
            raise ValueError("tested runtime policy requires exact manifest-tested tool versions")
        if any(
            dependency_versions[name] not in requirement_dependencies[name].tested_versions
            for name in dependency_versions
        ):
            raise ValueError("tested runtime policy requires exact manifest-tested dependency versions")
    expected_digest = compatibility_contract_digest(manifest, row.id)
    handoff_protocol = getattr(handoff, "protocol", {})
    if (
        contract_digest != expected_digest
        or not isinstance(handoff_protocol, Mapping)
        or handoff_protocol.get("compatibility_contract_digest") != expected_digest
    ):
        raise ValueError("runtime compatibility contract is not bound to the prepared handoff")
    workflow_identity = str(workflow["identity"])
    workflow_version = str(workflow["version"])
    if workflow_identity not in tool_versions or tool_versions[workflow_identity] != workflow_version:
        raise ValueError("runtime workflow must identify one observed tool from the selected row")
    return tool_versions, dependency_versions, {
        **{f"tool:{key}": item for key, item in tool_versions.items()},
        **{f"dependency:{key}": item for key, item in dependency_versions.items()},
        f"workflow:{workflow_identity}": workflow_version,
    }, workflow_identity, workflow_version


def _reload_validator(identifier: str):
    module_name, function_name = identifier.split(":", 1)
    if not module_name.startswith("biomed_workbench."):
        raise ValueError("reload validator must be packaged inside biomed_workbench")
    function = getattr(importlib.import_module(module_name), function_name)
    if not callable(function):
        raise ValueError("reload validator entrypoint is not callable")
    return function


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
    with artifact_store.transaction() as transaction:
        return _ingest_execution_bundle(
            state,
            bundle,
            registry=registry,
            artifact_store=transaction,
        )


def _ingest_execution_bundle(
    state: ProjectState,
    bundle: Mapping[str, Any],
    *,
    registry: ModuleRegistry,
    artifact_store: object,
) -> ProjectState:
    """Implement one atomic external-result admission transaction."""
    if set(bundle) != _BUNDLE_FIELDS:
        raise ValueError("execution receipt bundle fields are incomplete or unsupported")
    handoff = next((item for item in state.execution_handoffs if item.id == bundle["handoff_id"]), None)
    if handoff is None:
        raise ValueError("execution receipt bundle references an unknown handoff")
    validate_observed_output_protocol(handoff.protocol)
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
    if handoff.protocol.get("observed_output_protocol_version") != observed_output_protocol_version(manifest):
        raise ValueError("observed output protocol version differs from the current admission contract")
    expected_gate_ids = sorted(gate.id for gate in manifest.quality_gates)
    if (
        list(handoff.protocol.get("required_postflight_gate_ids", ())) != expected_gate_ids
        or handoff.protocol.get("required_postflight_gate_set_digest") != digest_value(expected_gate_ids)
    ):
        raise ValueError("execution handoff required gate set differs from the current module")
    if (
        not isinstance(bundle["process_exit_code"], int)
        or isinstance(bundle["process_exit_code"], bool)
        or bundle["process_exit_code"] != 0
    ):
        raise ValueError("only an observed zero-exit workflow can be ingested")
    outputs = bundle["outputs"]
    if not isinstance(outputs, list) or any(not isinstance(item, Mapping) or set(item) != _OUTPUT_FIELDS for item in outputs):
        raise ValueError("execution receipt bundle outputs are invalid")
    by_port = {str(item["port"]): item for item in outputs}
    expected_ports = {port.name for port in manifest.output_artifacts}
    if set(by_port) != expected_ports or len(outputs) != len(by_port):
        raise ValueError("execution receipt bundle must cover every output port exactly once")
    payloads_by_port = {}
    content_by_port = {}
    semantic_results_by_port: dict[str, Mapping[str, object]] = {}
    contracts = {item.port: item for item in manifest.observed_output_contracts}
    row = next(item for item in manifest.compatibility_matrix if item.id == handoff.compatibility_row_id)
    input_artifact_ids = set(node.input_bindings.values())
    input_artifacts = {
        artifact.id: artifact.content_digest
        for artifact in state.artifacts
        if artifact.id in input_artifact_ids
    }
    if set(input_artifacts) != input_artifact_ids:
        raise ValueError("execution handoff input artifact identities are unavailable")
    compatibility_digest = compatibility_contract_digest(manifest, handoff.compatibility_row_id)
    (
        tool_versions,
        dependency_versions,
        receipt_runtime_versions,
        workflow_identity,
        workflow_version,
    ) = _validate_runtime_versions(manifest, row, handoff, bundle["runtime_versions"])
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
        if (
            content["artifact_type"] != port.artifact_type
            or content["format"] not in expected_formats
            or provenance["parameters_digest"] != handoff.request_digest
            or provenance["compatibility_row_id"] != handoff.compatibility_row_id
            or provenance["workflow"] != workflow_identity
            or provenance["workflow_version"] != workflow_version
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
        if packaged_callable_source_sha256(contract.semantic_validator) != contract.semantic_validator_sha256:
            raise ValueError(f"semantic validator source digest differs from the frozen contract for port {port.name}")
        semantic_result = _reload_validator(contract.semantic_validator)(
            content=content,
            payloads=reloaded_payloads,
            context={
                "module_id": manifest.id,
                "module_version": manifest.version,
                "port": port.name,
                "handoff_request_digest": handoff.request_digest,
                "compatibility_contract_digest": compatibility_digest,
                "input_artifacts": input_artifacts,
            },
            profile=contract.semantic_profile,
        )
        if not isinstance(semantic_result, Mapping) or semantic_result.get("family_admission_status") != "passed":
            raise ValueError(f"observed output semantic validator rejected port {port.name}")
        semantic_results_by_port[port.name] = dict(semantic_result)
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
    if digest_value(sorted(by_gate)) != handoff.protocol["required_postflight_gate_set_digest"]:
        raise ValueError("postflight results differ from the frozen handoff gate set")
    evaluated_results: dict[str, dict[str, object]] = {}
    for gate_id in sorted(by_gate):
        evaluations = []
        for contract in manifest.observed_output_contracts:
            evaluator = next((item for item in contract.gate_evaluators if item.gate_id == gate_id), None)
            if evaluator is None:
                continue
            payloads = tuple(
                {
                    **payload.to_dict(),
                    "path": str(artifact_store.resolve(payload)),
                }
                for payload in payloads_by_port[contract.port]
            )
            result = _reload_validator(evaluator.evaluator)(
                payloads=payloads,
                gate_id=gate_id,
                evaluator_type=evaluator.evaluator_type,
                evidence_payload_role=evaluator.evidence_payload_role,
                metric_key=evaluator.metric_key,
                metric_type=evaluator.metric_type,
                operator=evaluator.operator,
                threshold=evaluator.threshold,
                semantic_result=semantic_results_by_port[contract.port],
            )
            if not isinstance(result, Mapping) or set(result) != {
                "status", "observed_metric", "threshold", "evidence_payload_sha256", "reason", "evaluator_type"
            }:
                raise ValueError(f"packaged gate evaluator returned an invalid result: {gate_id}")
            if result["status"] not in {"passed", "failed", "requires_review", "not_evaluable"}:
                raise ValueError(f"packaged gate evaluator returned an unsupported status: {gate_id}")
            evidence = next(
                (payload for payload in payloads if payload["role"] == evaluator.evidence_payload_role),
                None,
            )
            if evidence is None:
                if result["status"] != "not_evaluable" or result["evidence_payload_sha256"] is not None:
                    raise ValueError(f"gate evaluator did not honor its absent evidence payload role: {gate_id}")
            elif result["evidence_payload_sha256"] != evidence["sha256"]:
                raise ValueError(f"gate evaluator evidence digest differs from its declared payload role: {gate_id}")
            evaluations.append({
                "port": contract.port,
                **dict(result),
                "evaluator_identity": evaluator.evaluator,
                "evaluator_version": GATE_EVALUATOR_CONTRACT_VERSION,
                "evaluator_sha256": packaged_callable_source_sha256(evaluator.evaluator),
            })
        if not evaluations:
            raise ValueError(f"required postflight gate has no assigned output port: {gate_id}")
        statuses = {str(item["status"]) for item in evaluations}
        overall_status = (
            "failed" if "failed" in statuses
            else "requires_review" if "requires_review" in statuses
            else "not_evaluable" if "not_evaluable" in statuses
            else "passed"
        )
        evaluated_results[gate_id] = {
            "gate_id": gate_id,
            "evaluations": evaluations,
            "status": overall_status,
        }
    provenance = {
        "module_id": manifest.id,
        "module_version": manifest.version,
        "compatibility_row_id": handoff.compatibility_row_id,
        "tools": tool_versions,
        "dependencies": dependency_versions,
        "compatibility_contract_digest": compatibility_contract_digest(
            manifest, handoff.compatibility_row_id
        ),
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
        quality_status_by_port={
            str(evaluation["port"]): "major"
            for result in evaluated_results.values()
            if result["status"] == "failed"
            for evaluation in result["evaluations"]
            if evaluation["status"] == "failed"
        },
    )
    observed = ObservedExecutionReceipt.create(
        plan_node_id=node.id,
        module_id=manifest.id,
        module_version=manifest.version,
        compatibility_row_id=handoff.compatibility_row_id,
        observed_output_contract_digest=current_contract_digest,
        parameters_digest=handoff.request_digest,
        runtime_versions=receipt_runtime_versions,
        output_artifact_digests={artifact.id: artifact.content_digest for artifact in artifacts},
        postflight_result_digests={gate_id: digest_value(result) for gate_id, result in evaluated_results.items()},
        postflight_results=evaluated_results,
        process_exit_code=int(bundle["process_exit_code"]),
        source_kind="handoff",
        execution_request_digest=digest_value(handoff.to_dict()),
        handoff=handoff,
    )
    validate_handoff_receipt_gate_coverage(handoff, observed)
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
    source_urls = tuple(
        value
        for value in manifest.provenance.concept_sources
        if value.startswith(("https://", "http://"))
    ) or (
        "https://github.com/JunyanKang/biomed-workbench",
    )
    for artifact in artifacts:
        port = next(
            name for name, artifact_id in node.planned_output_artifact_ids.items()
            if artifact_id == artifact.id
        )
        failed_gate_ids = tuple(
            gate_id
            for gate_id, result in evaluated_results.items()
            if result["status"] == "failed"
            and any(
                evaluation["port"] == port and evaluation["status"] == "failed"
                for evaluation in result["evaluations"]
            )
        )
        for gate_id in failed_gate_ids:
            adjudication = automatic_failed_gate_adjudication(
                state,
                artifact.id,
                gate_id,
                source_urls=source_urls,
            )
            state = apply_event(
                state,
                "scientific_gate_adjudicated",
                {"adjudication": adjudication.to_dict()},
                rationale="Record the registered evaluator's automatic rejection of one failed scientific gate.",
                affected_artifact_ids=(artifact.id,),
                affected_hypothesis_ids=node.target_hypothesis_ids,
                replacement_action_ids=(node.id,),
            )
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
