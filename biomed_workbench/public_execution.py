"""Public, stateful execution surface for one registry module."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .kernel.artifact_store import ProjectArtifactStore
from .kernel.artifacts import ScientificArtifact
from .kernel.context import ProjectContext
from .kernel.hypotheses import Hypothesis
from .kernel.identity import digest_value
from .kernel.plans import PlanNode, ResearchDAG
from .kernel.scientific_dependency import AnalysisAdmission
from .kernel.state import ProjectState, apply_event
from .modules.compatibility import EnvironmentSnapshot, detect_environment
from .modules.contract import ModuleManifest
from .modules.index import BUILTIN_ROOT
from .modules.registry import ModuleRegistry
from .orchestration.controller import ResearchController


class PublicExecutionError(ValueError):
    """A safe, structured public-entry execution error."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PublicExecutionResult:
    module_id: str
    execution_status: str
    stop_reason: str
    project_id: str
    project_state_digest: str
    execution: Mapping[str, Any]
    output_artifacts: tuple[Mapping[str, Any], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "module_id": self.module_id,
            "status": self.execution_status,
            "stop_reason": self.stop_reason,
            "project_id": self.project_id,
            "project_state_digest": self.project_state_digest,
            "execution": dict(self.execution),
            "output_artifacts": [dict(value) for value in self.output_artifacts],
        }


def _project_root(path: str | Path) -> Path:
    root = Path(path).expanduser()
    if not root.exists() or root.is_symlink() or not root.is_dir():
        raise PublicExecutionError("PROJECT_ROOT_INVALID", "--project-root must identify an existing non-symlink directory")
    return root.resolve(strict=True)


def _context(payload: Mapping[str, Any]) -> ProjectContext:
    raw = payload.get("project_context")
    if not isinstance(raw, Mapping):
        raise PublicExecutionError(
            "PROJECT_CONTEXT_REQUIRED",
            "artifact bindings must include a complete project_context object",
        )
    try:
        return ProjectContext.from_dict(raw)
    except (KeyError, TypeError, ValueError) as exc:
        raise PublicExecutionError("PROJECT_CONTEXT_INVALID", "project_context is incomplete or invalid") from exc


def _hypotheses(payload: Mapping[str, Any]) -> tuple[Hypothesis, ...]:
    raw = payload.get("hypotheses")
    if not isinstance(raw, list) or not raw:
        raise PublicExecutionError("HYPOTHESIS_REQUIRED", "artifact bindings must include at least one falsifiable hypothesis")
    try:
        values = tuple(Hypothesis.from_dict(item) for item in raw)
    except (KeyError, TypeError, ValueError) as exc:
        raise PublicExecutionError("HYPOTHESIS_INVALID", "one or more project hypotheses are incomplete or invalid") from exc
    if len({item.id for item in values}) != len(values):
        raise PublicExecutionError("HYPOTHESIS_INVALID", "project hypothesis IDs must be unique")
    return values


_ADMISSION_FIELDS = {
    "rationale_zh",
    "rationale_en",
    "method",
    "official_sources",
    "alternatives_considered",
    "assumptions",
    "parameter_justifications",
    "acceptance_criteria",
    "falsification_criteria",
    "approved",
}


def _admission(
    payload: Mapping[str, Any],
    *,
    node: PlanNode,
    hypothesis_ids: tuple[str, ...],
) -> AnalysisAdmission:
    raw = payload.get("analysis_admission")
    if not isinstance(raw, Mapping) or set(raw) != _ADMISSION_FIELDS:
        raise PublicExecutionError(
            "ANALYSIS_ADMISSION_REQUIRED",
            "artifact bindings require one complete analysis_admission with rationale, sources, alternatives, criteria, and approval",
        )
    values = dict(raw)
    for field in (
        "official_sources",
        "alternatives_considered",
        "assumptions",
        "acceptance_criteria",
        "falsification_criteria",
    ):
        values[field] = tuple(values[field])
    try:
        return AnalysisAdmission(
            id=f"admission-{node.id}",
            plan_node_id=node.id,
            hypothesis_ids=hypothesis_ids,
            expected_artifact_types=node.expected_output_artifact_types,
            **values,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise PublicExecutionError("ANALYSIS_ADMISSION_INVALID", "analysis_admission violates the scientific admission contract") from exc


_BINDING_FIELDS = {
    "artifact_id",
    "format_name",
    "format_version",
    "compression",
    "orientation",
    "indexes",
    "scientific_scope",
    "denominator",
    "processing_level",
    "quality_status",
    "coordinate_system",
    "genome_build",
    "annotation_release",
    "identifier_namespace",
    "content",
    "payload_files",
    "sort_order",
    "reference_sequence_digest",
    "sample_manifest_digest",
    "metadata_fields",
    "representation",
}


def _artifact(
    *,
    port,
    binding: Mapping[str, Any],
    parameters: Mapping[str, Any],
    include_parameters: bool,
    context: ProjectContext,
    store: ProjectArtifactStore,
) -> ScientificArtifact:
    extra = sorted(set(binding) - _BINDING_FIELDS)
    if extra:
        raise PublicExecutionError("ARTIFACT_BINDING_INVALID", f"artifact binding has unsupported fields: {', '.join(extra)}")
    required = {"format_name", "format_version", "compression", "orientation", "denominator", "processing_level", "quality_status", "scientific_scope"}
    missing = sorted(required - set(binding))
    if missing:
        raise PublicExecutionError("ARTIFACT_BINDING_INVALID", f"artifact binding is missing: {', '.join(missing)}")
    content = binding.get("content", {})
    if not isinstance(content, Mapping):
        raise PublicExecutionError("ARTIFACT_BINDING_INVALID", "artifact binding content must be an object")
    merged = dict(content)
    if include_parameters:
        conflicts = sorted(key for key, value in parameters.items() if key in merged and merged[key] != value)
        if conflicts:
            raise PublicExecutionError("PARAMETER_BINDING_CONFLICT", f"parameters conflict with artifact content: {', '.join(conflicts)}")
        merged.update(parameters)
    payload_specs = binding.get("payload_files", [])
    if not isinstance(payload_specs, list):
        raise PublicExecutionError("ARTIFACT_BINDING_INVALID", "payload_files must be an array")
    payloads = []
    for item in payload_specs:
        if not isinstance(item, Mapping) or set(item) != {"role", "path", "media_type"}:
            raise PublicExecutionError("ARTIFACT_BINDING_INVALID", "each payload file requires role, path, and media_type")
        try:
            payloads.append(store.import_file(str(item["path"]), role=str(item["role"]), media_type=str(item["media_type"])))
        except (OSError, TypeError, ValueError) as exc:
            raise PublicExecutionError("INPUT_PAYLOAD_INVALID", f"input payload for role {item.get('role')} is unavailable or invalid") from exc
    artifact_id = str(binding.get("artifact_id") or f"artifact-input-{port.name}-{digest_value(binding)[:12]}")
    try:
        return ScientificArtifact.create(
            id=artifact_id,
            artifact_type=port.artifact_type,
            schema_version="1.0",
            format_name=str(binding["format_name"]),
            format_version=str(binding["format_version"]),
            compression=str(binding["compression"]),
            orientation=str(binding["orientation"]),
            indexes=tuple(binding.get("indexes", ())),
            producing_module_id=None,
            producing_module_version=None,
            source_artifact_ids=(),
            scientific_scope=dict(binding["scientific_scope"]),
            experimental_unit=context.experimental_unit,
            denominator=str(binding["denominator"]),
            processing_level=str(binding["processing_level"]),
            quality_status=str(binding["quality_status"]),
            coordinate_system=binding.get("coordinate_system"),
            genome_build=binding.get("genome_build"),
            annotation_release=binding.get("annotation_release"),
            identifier_namespace=binding.get("identifier_namespace"),
            producer_tool_versions={},
            content=merged,
            payloads=tuple(payloads),
            sort_order=binding.get("sort_order"),
            reference_sequence_digest=binding.get("reference_sequence_digest"),
            sample_manifest_digest=binding.get("sample_manifest_digest"),
            metadata_fields=tuple(binding.get("metadata_fields", ())),
            representation=str(binding.get("representation", "structured")),
        )
    except (TypeError, ValueError) as exc:
        raise PublicExecutionError("ARTIFACT_BINDING_INVALID", f"artifact binding for port {port.name} violates its scientific contract") from exc


def _bound_artifacts(
    manifest: ModuleManifest,
    payload: Mapping[str, Any],
    parameters: Mapping[str, Any],
    context: ProjectContext,
    store: ProjectArtifactStore,
) -> tuple[ScientificArtifact, ...]:
    raw = payload.get("artifacts")
    if not isinstance(raw, Mapping):
        raise PublicExecutionError("INPUT_ARTIFACT_REQUIRED", "artifact bindings require an artifacts object keyed by input port")
    expected = {port.name for port in manifest.input_artifacts}
    if set(raw) != expected:
        missing = sorted(expected - set(raw))
        extra = sorted(set(raw) - expected)
        detail = ", ".join((*[f"missing:{value}" for value in missing], *[f"extra:{value}" for value in extra]))
        raise PublicExecutionError("INPUT_ARTIFACT_REQUIRED", f"artifact bindings differ from module ports: {detail}")
    artifacts = []
    for index, port in enumerate(manifest.input_artifacts):
        binding = raw[port.name]
        if not isinstance(binding, Mapping):
            raise PublicExecutionError("ARTIFACT_BINDING_INVALID", f"artifact binding for port {port.name} must be an object")
        artifacts.append(
            _artifact(
                port=port,
                binding=binding,
                parameters=parameters,
                include_parameters=index == 0,
                context=context,
                store=store,
            )
        )
    if manifest.execution.kind == "command" and manifest.execution.command is not None:
        by_port = {port.name: artifact for port, artifact in zip(manifest.input_artifacts, artifacts, strict=True)}
        for command_input in manifest.execution.command.inputs:
            matches = [payload for payload in by_port[command_input.port].payloads if payload.role == command_input.role]
            if len(matches) != 1:
                raise PublicExecutionError(
                    "INPUT_PAYLOAD_REQUIRED",
                    f"command input {command_input.name} requires exactly one payload with role {command_input.role}",
                )
    return tuple(artifacts)


def execute_public_module(
    module_id: str,
    parameters: Mapping[str, Any],
    *,
    project_root: str | Path,
    artifact_bindings: Mapping[str, Any],
    compatibility_row_id: str,
    allow_mutation: bool = False,
    environment_provider: Callable[[ModuleManifest], EnvironmentSnapshot] = detect_environment,
    command_executable_resolver: Callable[[str], str | None] | None = None,
) -> PublicExecutionResult:
    """Execute one exact module through the stateful strict controller."""
    if not isinstance(parameters, Mapping):
        raise PublicExecutionError("INPUT_INVALID", "--input must decode to an object")
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    try:
        manifest = registry.get(module_id)
    except ValueError as exc:
        raise PublicExecutionError("CAPABILITY_UNKNOWN", f"unknown capability: {module_id}") from exc
    row_ids = {row.id for row in manifest.compatibility_matrix}
    if compatibility_row_id not in row_ids:
        raise PublicExecutionError("COMPATIBILITY_ROW_INVALID", "--compatibility-row is not declared by the module")
    root = _project_root(project_root)
    store = ProjectArtifactStore(root / ".biomed-workbench" / "artifacts")
    context = _context(artifact_bindings)
    hypotheses = _hypotheses(artifact_bindings)
    artifacts = _bound_artifacts(manifest, artifact_bindings, parameters, context, store)
    state = ProjectState.create(context)
    for hypothesis in hypotheses:
        state = apply_event(
            state,
            "hypothesis_added",
            {"hypothesis": hypothesis.to_dict()},
            rationale="Register one falsifiable project hypothesis before admitting public execution.",
            affected_hypothesis_ids=(hypothesis.id,),
        )
    for artifact in artifacts:
        state = apply_event(
            state,
            "artifact_registered",
            {"artifact": artifact.to_dict()},
            rationale="Register one public-entry input artifact after content-addressed import and contract validation.",
            affected_artifact_ids=(artifact.id,),
        )
    bindings = {port.name: artifact.id for port, artifact in zip(manifest.input_artifacts, artifacts, strict=True)}
    output_ids = {
        port.name: f"artifact-output-{port.name}-{digest_value({'module': module_id, 'inputs': bindings, 'parameters': dict(parameters)})[:12]}"
        for port in manifest.output_artifacts
    }
    node = PlanNode(
        id=f"node-{manifest.id}-{digest_value({'inputs': bindings, 'row': compatibility_row_id})[:12]}",
        module_id=manifest.id,
        input_bindings=bindings,
        dependencies=(),
        branch_id="branch-public-entry",
        target_hypothesis_ids=tuple(item.id for item in hypotheses),
        expected_evidence_types=(),
        expected_output_artifact_types=tuple(dict.fromkeys(port.artifact_type for port in manifest.output_artifacts)),
        planned_output_artifact_ids=output_ids,
        compatibility_row_candidates=(compatibility_row_id,),
        status="ready",
        attempt=0,
    )
    plan = ResearchDAG.create(
        id=f"plan-{manifest.id}-{digest_value({'node': node.to_dict(), 'context': context.to_dict()})[:12]}",
        objective=context.objective,
        nodes=(node,),
        required_output_artifact_types=tuple(dict.fromkeys(port.artifact_type for port in manifest.output_artifacts)),
        plan_type="single",
        revision=1,
        parent_plan_id=None,
        rationale=("The public entry bound an explicit project context, artifacts, parameters, and compatibility row before execution.",),
    )
    state = apply_event(
        state,
        "plan_created",
        {"plan": plan.to_dict(), "activate": True},
        rationale="Register the exact public-entry analysis plan before scientific admission.",
        replacement_action_ids=(node.id,),
    )
    admission = _admission(
        artifact_bindings,
        node=node,
        hypothesis_ids=tuple(item.id for item in hypotheses),
    )
    state = apply_event(
        state,
        "analysis_admission_recorded",
        {"admission": admission.to_dict()},
        rationale="Admit the analysis only after its rationale, alternatives, parameters, and falsification criteria are explicit.",
        affected_hypothesis_ids=admission.hypothesis_ids,
        replacement_action_ids=(node.id,),
    )
    controller = ResearchController(
        registry,
        environment_provider=environment_provider,
        artifact_store=store,
        allow_mutation=allow_mutation,
        command_executable_resolver=command_executable_resolver,
    )
    cycle = controller.advance(state, plan)
    execution = cycle.executions[-1] if cycle.executions else None
    if execution is None:
        raise PublicExecutionError("EXECUTION_NOT_RECORDED", "strict controller produced no execution record")
    outputs = tuple(
        artifact.to_dict()
        for artifact in cycle.state.artifacts
        if artifact.id in set(execution.output_artifact_ids)
    )
    return PublicExecutionResult(
        module_id=manifest.id,
        execution_status=execution.status,
        stop_reason=cycle.stop_reason,
        project_id=context.project_id,
        project_state_digest=cycle.state.state_digest,
        execution=execution.to_dict(),
        output_artifacts=outputs,
    )
