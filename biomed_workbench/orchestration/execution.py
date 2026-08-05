"""Strict compatibility-gated execution and normalized scientific artifacts."""

from __future__ import annotations

from dataclasses import dataclass
import multiprocessing
import os
import queue
import threading
from typing import Any, Callable, Mapping

from ..kernel.artifact_store import ArtifactPayload, ProjectArtifactStore
from ..kernel.artifacts import ScientificArtifact
from ..kernel.execution_receipts import ExecutionHandoff
from ..kernel.identity import digest_value, freeze_mapping, thaw
from ..kernel.plans import PlanNode, ResearchDAG
from ..kernel.state import ProjectState
from ..kernel.execution_chain import validate_artifact_execution_chain
from ..modules.compatibility import ArtifactSnapshot, CompatibilityError, EnvironmentSnapshot, evaluate_compatibility, invoke_compatible
from ..modules.contract import (
    ArtifactPort,
    FormatContract,
    ModuleManifest,
    compatibility_contract_digest,
    observed_output_contract_digest,
    observed_output_protocol_version,
)
from ..modules.registry import ModuleRegistry, ModuleRegistryError
from ..modules.scientific_command import ScientificCommandError, execute_scientific_command
from ..runner import InputValidationError, validate_schema_value
from .quality import QualityFinding, evaluate_project_quality


EnvironmentProvider = Callable[[ModuleManifest], EnvironmentSnapshot]
EntrypointResolver = Callable[[str], Callable[..., object]]


def _entrypoint_worker(result_queue, entrypoint, inputs) -> None:
    try:
        result_queue.put(("completed", entrypoint(**inputs)))
    except BaseException as exc:
        result_queue.put(("failed", type(exc).__name__))


def _bounded_invoke(entrypoint: Callable[..., object], inputs: dict[str, Any], timeout_seconds: int) -> object:
    method = "fork" if hasattr(os, "fork") and threading.current_thread() is threading.main_thread() else "spawn"
    context = multiprocessing.get_context(method)
    result_queue = context.Queue(maxsize=1)
    process = context.Process(target=_entrypoint_worker, args=(result_queue, entrypoint, inputs), daemon=True)
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(2)
        if process.is_alive():
            process.kill()
            process.join(2)
        result_queue.close()
        raise TimeoutError("module entrypoint exceeded its declared timeout")
    try:
        status, payload = result_queue.get(timeout=1)
    except queue.Empty:
        raise RuntimeError("module entrypoint process returned no result") from None
    finally:
        result_queue.close()
    if status != "completed":
        raise RuntimeError(f"module entrypoint failed with {payload}")
    return payload


@dataclass(frozen=True)
class NodeExecution:
    node_id: str
    module_id: str
    module_version: str
    status: str
    compatibility_row_id: str | None
    input_artifact_ids: tuple[str, ...]
    output_artifact_ids: tuple[str, ...]
    artifacts: tuple[ScientificArtifact, ...]
    quality_findings: tuple[QualityFinding, ...]
    compatibility_finding_codes: tuple[str, ...]
    provenance: Mapping[str, Any]
    safe_error_class: str | None
    execution_handoff: ExecutionHandoff | None = None

    def __post_init__(self) -> None:
        if self.status not in {"awaiting_observed_execution", "completed", "blocked", "failed"}:
            raise ValueError("node execution status is unsupported")
        object.__setattr__(self, "provenance", freeze_mapping(self.provenance))
        if self.status == "completed" and (self.safe_error_class is not None or not self.artifacts or not self.compatibility_row_id):
            raise ValueError("completed execution requires artifacts and compatibility provenance")
        if self.status == "completed" and self.execution_handoff is not None:
            raise ValueError("completed execution cannot retain an unobserved handoff")
        if self.status == "awaiting_observed_execution" and (
            self.safe_error_class is not None
            or self.execution_handoff is None
            or self.artifacts
            or self.output_artifact_ids
            or not self.compatibility_row_id
        ):
            raise ValueError("awaiting execution requires one handoff and no scientific output artifact")
        if self.status in {"blocked", "failed"} and self.safe_error_class is None:
            raise ValueError("blocked or failed execution requires a safe error class")
        if self.status in {"blocked", "failed"} and self.execution_handoff is not None:
            raise ValueError("blocked or failed execution cannot expose a handoff")

    def to_dict(self) -> dict[str, object]:
        payload = {
            "node_id": self.node_id,
            "module_id": self.module_id,
            "module_version": self.module_version,
            "status": self.status,
            "compatibility_row_id": self.compatibility_row_id,
            "input_artifact_ids": list(self.input_artifact_ids),
            "output_artifact_ids": list(self.output_artifact_ids),
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "quality_findings": [finding.to_dict() for finding in self.quality_findings],
            "compatibility_finding_codes": list(self.compatibility_finding_codes),
            "provenance": thaw(self.provenance),
            "safe_error_class": self.safe_error_class,
        }
        if self.execution_handoff is not None:
            payload["execution_handoff"] = self.execution_handoff.to_dict()
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "NodeExecution":
        values = dict(payload)
        values["input_artifact_ids"] = tuple(values["input_artifact_ids"])
        values["output_artifact_ids"] = tuple(values["output_artifact_ids"])
        values["artifacts"] = tuple(ScientificArtifact.from_dict(item) for item in values["artifacts"])
        values["quality_findings"] = tuple(QualityFinding.from_dict(item) for item in values["quality_findings"])
        values["compatibility_finding_codes"] = tuple(values["compatibility_finding_codes"])
        handoff = values.get("execution_handoff")
        if handoff is not None:
            values["execution_handoff"] = ExecutionHandoff.from_dict(handoff)
        return cls(**values)


def _blocked(node: PlanNode, manifest: ModuleManifest, input_ids: tuple[str, ...], error_class: str, *, quality=(), compatibility_codes=()) -> NodeExecution:
    return NodeExecution(
        node_id=node.id,
        module_id=manifest.id,
        module_version=manifest.version,
        status="blocked",
        compatibility_row_id=None,
        input_artifact_ids=input_ids,
        output_artifact_ids=(),
        artifacts=(),
        quality_findings=tuple(quality),
        compatibility_finding_codes=tuple(compatibility_codes),
        provenance={},
        safe_error_class=error_class,
    )


def _inputs(manifest: ModuleManifest, node: PlanNode, artifacts: dict[str, ScientificArtifact]) -> tuple[dict[str, Any], tuple[ScientificArtifact, ...]]:
    bound = []
    for port in manifest.input_artifacts:
        artifact_id = node.input_bindings.get(port.name)
        if artifact_id is None or artifact_id not in artifacts:
            raise ValueError(f"missing materialized artifact for input port: {port.name}")
        bound.append(artifacts[artifact_id])
    if set(node.input_bindings) != {port.name for port in manifest.input_artifacts}:
        raise ValueError("node input bindings differ from module input ports")
    merged = {}
    for artifact in bound:
        for key, value in artifact.content.items():
            if key in merged and merged[key] != value:
                raise ValueError(f"input artifacts contain conflicting field: {key}")
            merged[key] = thaw(value)
    return merged, tuple(bound)


def _validate_reviewed_upstream(
    state: ProjectState,
    dag: ResearchDAG,
    manifest: ModuleManifest,
    node: PlanNode,
    artifacts: dict[str, ScientificArtifact],
) -> None:
    required_types = set(manifest.orchestration.requires_reviewed_upstream_types)
    active_artifacts = {item.artifact_id for item in state.scientific_decisions if item.active_evidence}
    for port in manifest.input_artifacts:
        if port.source_policy != "upstream_required" and port.artifact_type not in required_types:
            continue
        artifact = artifacts.get(node.input_bindings.get(port.name, ""))
        if artifact is None or artifact.producing_module_id is None:
            raise ValueError(f"input port {port.name} requires a produced upstream artifact")
        producer_node_id = validate_artifact_execution_chain(state, artifact.id)
        if producer_node_id not in node.dependencies or producer_node_id not in {item.id for item in dag.nodes}:
            raise ValueError(f"input port {port.name} is not bound to a declared upstream dependency")
        if artifact.id not in active_artifacts:
            raise ValueError(f"input port {port.name} requires a reviewed and retained upstream artifact")


def _snapshots(manifest: ModuleManifest, node: PlanNode, artifacts: dict[str, ScientificArtifact]) -> tuple[ArtifactSnapshot, ...]:
    snapshots = []
    for port in manifest.input_artifacts:
        artifact = artifacts[node.input_bindings[port.name]]
        metadata = set(artifact.scientific_scope) | set(artifact.content) | {
            "module_version" if artifact.producing_module_version else "",
            "compatibility_row_id" if artifact.producing_module_version else "",
        }
        snapshots.append(
            ArtifactSnapshot(
                port=port.name,
                format=artifact.format_name,
                format_version=artifact.format_version,
                compression=artifact.compression,
                indexes=artifact.indexes,
                coordinate_system=artifact.coordinate_system,
                genome_build=artifact.genome_build,
                annotation_release=artifact.annotation_release,
                orientation=artifact.orientation,
                metadata_fields=tuple(sorted(metadata - {""})),
                representation=artifact.representation,
                sort_order=artifact.sort_order or "unsorted",
                reference_sequence_digest=artifact.reference_sequence_digest,
                identifier_namespace=artifact.identifier_namespace,
                sample_manifest_digest=artifact.sample_manifest_digest,
                payload_roles=tuple(payload.role for payload in artifact.payloads),
                processing_level=artifact.processing_level,
            )
        )
    return tuple(snapshots)


def _format_contract(port: ArtifactPort, token: str) -> tuple[FormatContract, str]:
    name, separator, version = token.partition("@")
    if not separator:
        raise ValueError("compatibility output format token is invalid")
    for contract in port.formats:
        if contract.name == name and version in contract.versions:
            return contract, version
    raise ValueError("compatibility row references an unavailable output format")


def _output_artifacts(
    state: ProjectState,
    node: PlanNode,
    manifest: ModuleManifest,
    output: dict[str, Any],
    provenance: Mapping[str, Any],
    quality_findings: tuple[QualityFinding, ...],
    payloads_by_port: Mapping[str, tuple[ArtifactPayload, ...]] | None = None,
) -> tuple[ScientificArtifact, ...]:
    row = next(item for item in manifest.compatibility_matrix if item.id == provenance["compatibility_row_id"])
    source_ids = tuple(node.input_bindings[port.name] for port in manifest.input_artifacts)
    source_artifacts = {artifact.id: artifact for artifact in state.artifacts}
    denominators = {source_artifacts[artifact_id].denominator for artifact_id in source_ids}
    if len(denominators) != 1:
        raise ValueError("output artifact requires one validated input denominator")
    values = []
    for port in manifest.output_artifacts:
        tokens = row.output_formats[port.name]
        contract, version = _format_contract(port, tokens[0])
        content = output if len(manifest.output_artifacts) == 1 else output.get(port.name)
        if not isinstance(content, dict):
            raise ValueError(f"module output port {port.name} must be an object")
        artifact_id = node.planned_output_artifact_ids.get(port.name)
        if artifact_id is None:
            raise ValueError(f"node does not declare output artifact for port: {port.name}")
        scope = {**thaw(state.context.biological_scope), "species": list(state.context.species)}
        values.append(
            ScientificArtifact.create(
                id=artifact_id,
                artifact_type=port.artifact_type,
                schema_version="1.0",
                format_name=contract.name,
                format_version=version,
                compression=contract.compression[0],
                orientation=contract.orientations[0],
                indexes=contract.required_indexes,
                producing_module_id=manifest.id,
                producing_module_version=manifest.version,
                source_artifact_ids=source_ids,
                scientific_scope=scope,
                experimental_unit=state.context.experimental_unit,
                denominator=next(iter(denominators)),
                processing_level=port.processing_levels[0],
                quality_status="warning" if any(item.severity == "warning" for item in quality_findings) else "passed",
                coordinate_system=contract.coordinate_systems[0] if contract.coordinate_systems else None,
                genome_build=contract.genome_builds[0] if contract.genome_builds else None,
                annotation_release=contract.annotation_releases[0] if contract.annotation_releases else None,
                identifier_namespace=None,
                producer_tool_versions=thaw(provenance["tools"]),
                content=content,
                payloads=tuple((payloads_by_port or {}).get(port.name, ())),
            )
        )
    return tuple(values)


def execute_node(
    state: ProjectState,
    dag: ResearchDAG,
    node: PlanNode,
    registry: ModuleRegistry,
    *,
    environment_provider: EnvironmentProvider,
    entrypoint_resolver: EntrypointResolver | None = None,
    artifact_store: ProjectArtifactStore | None = None,
    command_executable_resolver: Callable[[str], str | os.PathLike[str] | None] | None = None,
    allow_mutation: bool = False,
) -> NodeExecution:
    if node.id not in {item.id for item in dag.nodes}:
        raise ValueError("execution node is absent from the supplied DAG")
    manifest = registry.get(node.module_id)
    artifacts = {artifact.id: artifact for artifact in state.artifacts}
    input_ids = tuple(node.input_bindings[port.name] for port in manifest.input_artifacts if port.name in node.input_bindings)
    quality = evaluate_project_quality(state, node, manifest)
    if any(finding.blocks_execution for finding in quality):
        return _blocked(node, manifest, input_ids, "QualityGateError", quality=quality)
    try:
        _validate_reviewed_upstream(state, dag, manifest, node, artifacts)
        inputs, bound = _inputs(manifest, node, artifacts)
        validate_schema_value(manifest.input_schema, inputs, "input")
    except (InputValidationError, ValueError) as exc:
        error_class = "InputValidationError" if isinstance(exc, InputValidationError) else (
            "UpstreamReviewRequiredError" if "upstream" in str(exc) else "ArtifactBindingError"
        )
        return _blocked(node, manifest, input_ids, error_class, quality=quality)
    if manifest.mutability != "read_only" and manifest.access != "agent_generated" and not allow_mutation:
        return _blocked(node, manifest, input_ids, "MutationPermissionError", quality=quality)
    environment = environment_provider(manifest)
    snapshots = _snapshots(manifest, node, artifacts)
    decision = evaluate_compatibility(manifest, environment, snapshots)
    if not decision.allowed:
        return _blocked(node, manifest, input_ids, "CompatibilityError", quality=quality, compatibility_codes=tuple(item.code for item in decision.findings))
    if decision.compatibility_row_id not in node.compatibility_row_candidates:
        return _blocked(
            node,
            manifest,
            input_ids,
            "CompatibilityRowSelectionError",
            quality=quality,
            compatibility_codes=("UNREQUESTED_COMPATIBILITY_ROW",),
        )
    try:
        if manifest.execution.kind == "command":
            if artifact_store is None:
                return _blocked(node, manifest, input_ids, "ArtifactStoreRequiredError", quality=quality)
            command = manifest.execution.command
            if command is None:
                raise ValueError("command module is missing its scientific command contract")
            artifacts_by_port = {
                port.name: artifacts[node.input_bindings[port.name]] for port in manifest.input_artifacts
            }
            payload_bindings = {}
            for binding in command.inputs:
                matches = [payload for payload in artifacts_by_port[binding.port].payloads if payload.role == binding.role]
                if len(matches) != 1:
                    raise ValueError(f"command input role is missing or ambiguous: {binding.name}")
                payload_bindings[binding.name] = matches[0]
            command_result = execute_scientific_command(
                command,
                store=artifact_store,
                input_payloads=payload_bindings,
                parameters={name: inputs[name] for name in command.parameter_names},
                tool_versions=environment.tools,
                dependency_versions=environment.dependencies,
                compatibility_row_id=decision.compatibility_row_id,
                executable_resolver=command_executable_resolver,
            )
            payloads_by_port = {}
            for binding, payload in zip(command.outputs, command_result.output_payloads):
                payloads_by_port.setdefault(binding.port, []).append(payload)
            payloads_by_port = {port: tuple(values) for port, values in payloads_by_port.items()}
            port_content = {
                port.name: {"payload_roles": [payload.role for payload in payloads_by_port[port.name]]}
                for port in manifest.output_artifacts
            }
            output = next(iter(port_content.values())) if len(port_content) == 1 else port_content
            validate_schema_value(manifest.output_schema, output, "output")
            compatibility_row = next(item for item in manifest.compatibility_matrix if item.id == decision.compatibility_row_id)
            provenance = {
                "module_id": manifest.id,
                "module_version": manifest.version,
                "compatibility_row_id": decision.compatibility_row_id,
                "tools": thaw(command_result.provenance["tools"]),
                "dependencies": thaw(command_result.provenance["dependencies"]),
                "tested_version_baseline": {
                    "tools": {item.name: environment.tools.get(item.name) in item.tested_versions for item in manifest.tool_requirements if item.name in environment.tools},
                    "dependencies": {item.name: environment.dependencies.get(item.name) in item.tested_versions for item in manifest.dependencies if item.name in environment.dependencies},
                },
                "compatibility_policy": {
                    "tools": {key: list(value) for key, value in sorted(compatibility_row.tool_versions.items())},
                    "dependencies": {key: list(value) for key, value in sorted(compatibility_row.dependency_versions.items())},
                },
                "platform": environment.platform,
                "input_formats": {artifact.port: f"{artifact.format}@{artifact.format_version}" for artifact in snapshots},
                "parameters_digest": digest_value(thaw(command_result.provenance["parameters"])),
                "output_digest": digest_value(output),
                "command_contract_digest": command_result.provenance["command_contract_digest"],
                "executable_sha256": command_result.provenance["executable_sha256"],
                "input_payloads": thaw(command_result.provenance["inputs"]),
                "output_payloads": thaw(command_result.provenance["outputs"]),
            }
            output_artifacts = _output_artifacts(
                state,
                node,
                manifest,
                output,
                provenance,
                quality,
                payloads_by_port,
            )
            invocation_provenance = provenance
        else:
            resolver = entrypoint_resolver or registry.resolve_entrypoint
            entrypoint = resolver(manifest.id)
            invocation = invoke_compatible(
                manifest,
                inputs=inputs,
                environment=environment,
                artifacts=snapshots,
                entrypoint=lambda **kwargs: _bounded_invoke(entrypoint, kwargs, manifest.execution.timeout_seconds),
            )
            if manifest.access == "agent_generated":
                compatibility_row_id = str(invocation.provenance["compatibility_row_id"])
                required_gate_ids = sorted(gate.id for gate in manifest.quality_gates)
                handoff_protocol = {
                    **dict(invocation.output),
                    "observed_output_protocol_version": observed_output_protocol_version(manifest),
                    "required_postflight_gate_ids": required_gate_ids,
                    "required_postflight_gate_set_digest": digest_value(required_gate_ids),
                    "compatibility_contract_digest": compatibility_contract_digest(
                        manifest, compatibility_row_id
                    ),
                }
                handoff = ExecutionHandoff.create(
                    plan_node_id=node.id,
                    module_id=manifest.id,
                    module_version=manifest.version,
                    request_digest=str(invocation.output["request_digest"]),
                    compatibility_row_id=compatibility_row_id,
                    observed_output_contract_digest=observed_output_contract_digest(manifest),
                    planned_output_artifact_ids=node.planned_output_artifact_ids,
                    protocol=handoff_protocol,
                )
                return NodeExecution(
                    node_id=node.id,
                    module_id=manifest.id,
                    module_version=manifest.version,
                    status="awaiting_observed_execution",
                    compatibility_row_id=decision.compatibility_row_id,
                    input_artifact_ids=input_ids,
                    output_artifact_ids=(),
                    artifacts=(),
                    quality_findings=quality,
                    compatibility_finding_codes=(),
                    provenance=invocation.provenance,
                    safe_error_class=None,
                    execution_handoff=handoff,
                )
            output_artifacts = _output_artifacts(state, node, manifest, invocation.output, invocation.provenance, quality)
            invocation_provenance = invocation.provenance
    except CompatibilityError as exc:
        return _blocked(node, manifest, input_ids, "CompatibilityError", quality=quality, compatibility_codes=tuple(item.code for item in exc.decision.findings))
    except (ModuleRegistryError, InputValidationError, ValueError, TypeError, RuntimeError, TimeoutError) as exc:
        return NodeExecution(
            node.id,
            manifest.id,
            manifest.version,
            "failed",
            decision.compatibility_row_id,
            input_ids,
            (),
            (),
            quality,
            (),
            {},
            f"ScientificCommandError:{exc.code}" if isinstance(exc, ScientificCommandError) else type(exc).__name__,
        )
    return NodeExecution(
        node_id=node.id,
        module_id=manifest.id,
        module_version=manifest.version,
        status="completed",
        compatibility_row_id=decision.compatibility_row_id,
        input_artifact_ids=input_ids,
        output_artifact_ids=tuple(artifact.id for artifact in output_artifacts),
        artifacts=output_artifacts,
        quality_findings=quality,
        compatibility_finding_codes=(),
        provenance=invocation_provenance,
        safe_error_class=None,
    )
