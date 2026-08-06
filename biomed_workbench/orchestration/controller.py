"""Dependency-aware execute, inspect, revise, resume, and stop controller."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..kernel.evidence import EvidenceRecord
from ..kernel.execution_receipts import ArtifactReloadReceipt, ObservedExecutionReceipt, ScientificReviewReceipt
from ..kernel.execution_chain import validate_node_execution_chain, validated_delivery_publication_is_current
from ..kernel.artifact_store import ProjectArtifactStore
from ..kernel.identity import digest_value, thaw
from ..kernel.plans import PlanNode, ResearchDAG
from ..kernel.scientific_dependency import (
    EXCLUDE_DECISION_ACTIONS,
    INPUT_DECISION_ACTIONS,
    REEXECUTE_DECISION_ACTIONS,
    RETAIN_DECISION_ACTIONS,
    REVISION_DECISION_ACTIONS,
    STOP_DECISION_ACTIONS,
)
from ..kernel.state import ProjectState, apply_event
from ..modules.compatibility import EnvironmentSnapshot
from ..modules.contract import ModuleManifest, observed_output_contract_digest
from ..modules.registry import ModuleRegistry
from .execution import NodeExecution, execute_node
from .interpretation import HypothesisAssessment, assess_hypothesis
from .quality import QualityFinding


NodeExecutor = Callable[..., NodeExecution]
EnvironmentProvider = Callable[[ModuleManifest], EnvironmentSnapshot]
EvidenceMapper = Callable[[NodeExecution, PlanNode, ProjectState], tuple[EvidenceRecord, ...]]
Replanner = Callable[[ProjectState, ResearchDAG, tuple[NodeExecution, ...], tuple[QualityFinding, ...]], ResearchDAG | None]


@dataclass(frozen=True)
class ControllerPolicy:
    max_plan_revisions: int = 3
    max_node_attempts: int = 2
    parallel_workers: int = 4
    stop_on_fatal: bool = True
    require_approved_admission: bool = True
    require_scientific_review: bool = True
    require_evidence_map_for_publication: bool = True

    def __post_init__(self) -> None:
        if self.max_plan_revisions < 0 or self.max_node_attempts < 1 or not 1 <= self.parallel_workers <= 16:
            raise ValueError("controller policy bounds are invalid")
        if any(
            not isinstance(value, bool)
            for value in (
                self.stop_on_fatal,
                self.require_approved_admission,
                self.require_scientific_review,
                self.require_evidence_map_for_publication,
            )
        ):
            raise ValueError("controller policy flags must be boolean")


@dataclass(frozen=True)
class CycleResult:
    state: ProjectState
    active_plan: ResearchDAG
    executions: tuple[NodeExecution, ...]
    assessments: tuple[HypothesisAssessment, ...]
    stop_reason: str


class ResearchController:
    def __init__(
        self,
        registry: ModuleRegistry,
        *,
        environment_provider: EnvironmentProvider,
        node_executor: NodeExecutor = execute_node,
        evidence_mapper: EvidenceMapper | None = None,
        replanner: Replanner | None = None,
        policy: ControllerPolicy | None = None,
        artifact_store: ProjectArtifactStore | None = None,
        allow_mutation: bool = False,
        entrypoint_resolver: Callable[[str], Callable[..., object]] | None = None,
        command_executable_resolver: Callable[[str], str | None] | None = None,
        evidence_map_root: Path | None = None,
    ) -> None:
        self._registry = registry
        self._environment_provider = environment_provider
        self._node_executor = node_executor
        self._evidence_mapper = evidence_mapper or (lambda _execution, _node, _state: ())
        self._replanner = replanner
        self._policy = policy or ControllerPolicy()
        self._artifact_store = artifact_store
        self._allow_mutation = allow_mutation
        self._entrypoint_resolver = entrypoint_resolver
        self._command_executable_resolver = command_executable_resolver
        self._evidence_map_root = evidence_map_root.resolve(strict=False) if evidence_map_root is not None else None
        if not isinstance(allow_mutation, bool):
            raise ValueError("controller allow_mutation must be boolean")

    def _delivery_publication_is_reachable(self, state: ProjectState, node_id: str) -> bool:
        if not validated_delivery_publication_is_current(state, node_id) or self._evidence_map_root is None:
            return False
        publication = next(
            (
                item for item in reversed(state.evidence_map_versions)
                if item.map_kind == "delivery-authorization"
                and node_id in item.authorized_delivery_node_ids
            ),
            None,
        )
        if publication is None:
            return False
        try:
            from ..reporting.evidence_map_versions import verify_evidence_map_publication_store

            verify_evidence_map_publication_store(self._evidence_map_root, publication)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return False
        return True

    def _declared_alternative_replan(
        self,
        state: ProjectState,
        parent: ResearchDAG,
        _executions: tuple[NodeExecution, ...],
        _findings: tuple[QualityFinding, ...],
    ) -> ResearchDAG | None:
        """Replace one blocked node only when its manifest declares a port-compatible alternative."""
        attempted_modules = {
            node.module_id
            for plan in state.plans
            for node in plan.nodes
            if node.status in {"blocked", "failed"}
        }
        blocked = tuple(node for node in parent.nodes if node.status in {"blocked", "failed"})
        for original in blocked:
            source = self._registry.get(original.module_id)
            for alternative_id in source.alternatives:
                if alternative_id in attempted_modules:
                    continue
                alternative = self._registry.get(alternative_id)
                if not self._replacement_is_compatible(source, alternative):
                    continue
                replacement_id = f"node-{alternative.id}-{digest_value({'parent': parent.id, 'node': original.id})[:10]}"
                replacement = PlanNode(
                    id=replacement_id,
                    module_id=alternative.id,
                    input_bindings=original.input_bindings,
                    dependencies=original.dependencies,
                    branch_id=original.branch_id,
                    target_hypothesis_ids=original.target_hypothesis_ids,
                    expected_evidence_types=original.expected_evidence_types,
                    expected_output_artifact_types=original.expected_output_artifact_types,
                    planned_output_artifact_ids=original.planned_output_artifact_ids,
                    compatibility_row_candidates=tuple(row.id for row in alternative.compatibility_matrix),
                    status="pending",
                    attempt=0,
                )
                nodes = []
                for node in parent.nodes:
                    if node.id == original.id:
                        nodes.append(replacement)
                    else:
                        dependencies = tuple(replacement_id if dependency == original.id else dependency for dependency in node.dependencies)
                        nodes.append(
                            PlanNode(
                                **{
                                    **node.__dict__,
                                    "dependencies": dependencies,
                                }
                            )
                        )
                plan_type = self._plan_type(tuple(nodes))
                return ResearchDAG.create(
                    id=f"plan-{digest_value({'parent': parent.id, 'replacement': replacement_id})[:20]}",
                    objective=parent.objective,
                    nodes=tuple(nodes),
                    required_output_artifact_types=parent.required_output_artifact_types,
                    plan_type=plan_type,
                    revision=parent.revision + 1,
                    parent_plan_id=parent.id,
                    rationale=(
                        "A blocked module was replaced by its manifest-declared, port-compatible alternative.",
                        "Completed upstream artifacts and all remaining dependency bindings were retained for reproducible continuation.",
                    ),
                )
        return None

    @staticmethod
    def _replacement_is_compatible(source: ModuleManifest, alternative: ModuleManifest) -> bool:
        return (
            source.input_artifacts == alternative.input_artifacts
            and source.output_artifacts == alternative.output_artifacts
        )

    @staticmethod
    def _plan_type(nodes: tuple[PlanNode, ...]) -> str:
        has_dependencies = any(node.dependencies for node in nodes)
        root_branches = {node.branch_id for node in nodes if not node.dependencies}
        if len(nodes) == 1:
            return "single"
        if has_dependencies and len(root_branches) > 1:
            return "mixed"
        if has_dependencies:
            return "serial"
        return "parallel"

    @staticmethod
    def _active_plan(state: ProjectState) -> ResearchDAG:
        if state.active_plan_id is None:
            raise ValueError("project state has no active plan")
        return next(plan for plan in state.plans if plan.id == state.active_plan_id)

    @staticmethod
    def _status(state: ProjectState, plan_id: str, node: PlanNode, status: str, attempt: int) -> ProjectState:
        return apply_event(
            state,
            "node_status_changed",
            {"plan_id": plan_id, "node_id": node.id, "status": status, "attempt": attempt},
            rationale=f"Record node {node.id} as {status} for deterministic execution state.",
            replacement_action_ids=(node.id,),
        )

    def _execute(self, state: ProjectState, plan: ResearchDAG, node: PlanNode) -> NodeExecution:
        return self._node_executor(
            state,
            plan,
            node,
            self._registry,
            environment_provider=self._environment_provider,
            entrypoint_resolver=self._entrypoint_resolver,
            artifact_store=self._artifact_store,
            command_executable_resolver=self._command_executable_resolver,
            allow_mutation=self._allow_mutation,
        )

    @staticmethod
    def _recorded_execution(state: ProjectState, node_id: str) -> NodeExecution | None:
        for event in reversed(state.decisions):
            if event.event_type != "node_execution_recorded":
                continue
            execution = NodeExecution.from_dict(thaw(event.payload)["execution"])
            if execution.node_id == node_id:
                return execution
        return None

    @classmethod
    def _resolved_completed_execution(cls, state: ProjectState, node: PlanNode) -> NodeExecution:
        """Resolve direct execution or reconstruct a read-only handoff completion view."""
        recorded = cls._recorded_execution(state, node.id)
        if recorded is not None and recorded.status == "completed":
            return recorded
        output_ids = validate_node_execution_chain(
            state,
            node.id,
            require_completed_node=False,
            require_active_decisions=True,
        )
        observed = next(item for item in state.observed_executions if item.plan_node_id == node.id)
        artifacts = tuple(
            next(item for item in state.artifacts if item.id == artifact_id)
            for artifact_id in output_ids
        )
        return NodeExecution(
            node_id=node.id,
            module_id=observed.module_id,
            module_version=observed.module_version,
            status="completed",
            compatibility_row_id=observed.compatibility_row_id,
            input_artifact_ids=tuple(node.input_bindings.values()),
            output_artifact_ids=output_ids,
            artifacts=artifacts,
            quality_findings=(),
            compatibility_finding_codes=(),
            provenance={
                "parameters_digest": observed.parameters_digest,
                "tools": thaw(observed.runtime_versions),
                "observed_execution_receipt_id": observed.id,
                "observed_output_contract_digest": observed.observed_output_contract_digest,
            },
            safe_error_class=None,
        )

    def _record_completed_receipt_chain(
        self,
        state: ProjectState,
        node: PlanNode,
        execution: NodeExecution,
    ) -> ProjectState:
        """Atomically register each output only through an observed-and-reloaded receipt chain."""
        manifest = self._registry.get(execution.module_id)
        provenance = thaw(execution.provenance)
        parameters_digest = str(provenance.get("parameters_digest") or digest_value(provenance))
        runtime_versions = {
            **{str(key): str(value) for key, value in dict(provenance.get("tools", {})).items()},
            **{str(key): str(value) for key, value in dict(provenance.get("dependencies", {})).items()},
        }
        if not runtime_versions:
            runtime_versions = {"module-runtime": execution.module_version}
        request_digest = digest_value(execution.to_dict())
        observed = ObservedExecutionReceipt.create(
            plan_node_id=node.id,
            module_id=execution.module_id,
            module_version=execution.module_version,
            compatibility_row_id=str(execution.compatibility_row_id),
            observed_output_contract_digest=(
                observed_output_contract_digest(manifest)
                if manifest.observed_output_contracts
                else digest_value(manifest.output_schema)
            ),
            parameters_digest=parameters_digest,
            runtime_versions=runtime_versions,
            output_artifact_digests={artifact.id: artifact.content_digest for artifact in execution.artifacts},
            # Direct/command quality findings are already recorded as project events;
            # manifest gate results are reserved for the handoff ingest protocol.
            postflight_result_digests={},
            postflight_results={},
            process_exit_code=0,
            source_kind="command" if manifest.execution.kind == "command" else "direct",
            execution_request_digest=request_digest,
        )
        state = apply_event(
            state,
            "execution_observed",
            {"receipt": observed.to_dict()},
            rationale="Record observed process completion against the exact execution request and compatibility row.",
            affected_hypothesis_ids=node.target_hypothesis_ids,
            replacement_action_ids=(node.id,),
        )
        reloads = []
        for artifact in execution.artifacts:
            reload_receipt = ArtifactReloadReceipt.create(
                observed_execution=observed,
                artifact_id=artifact.id,
                payload_digests={payload.role: payload.sha256 for payload in artifact.payloads},
                observed_output_contract_digest=observed.observed_output_contract_digest,
                reload_validator_id=None,
                output_schema_valid=True,
                content_digest=artifact.content_digest,
            )
            state = apply_event(
                state,
                "artifact_reloaded",
                {"receipt": reload_receipt.to_dict(), "artifact": artifact.to_dict()},
                rationale="Register one output only after content-addressed reload and output-contract validation.",
                affected_artifact_ids=(artifact.id,),
                affected_hypothesis_ids=node.target_hypothesis_ids,
                replacement_action_ids=(node.id,),
            )
            reloads.append(reload_receipt)
        integrity_review = ScientificReviewReceipt.create(
            observed_execution=observed,
            reload_receipts=tuple(reloads),
            finding_ids=tuple(item.id for item in execution.quality_findings),
        )
        return apply_event(
            state,
            "execution_reviewed",
            {"receipt": integrity_review.to_dict()},
            rationale="Accept the complete observed-execution and output-reload chain for scientific artifact review.",
            trigger_finding_ids=integrity_review.finding_ids,
            affected_artifact_ids=tuple(artifact.id for artifact in execution.artifacts),
            affected_hypothesis_ids=node.target_hypothesis_ids,
            replacement_action_ids=(node.id,),
        )

    def _release_reviewed_nodes(self, state: ProjectState, plan: ResearchDAG) -> ProjectState:
        """Dispatch reviewed outputs according to their explicit scientific decision family."""
        decisions = {item.artifact_id: item for item in state.scientific_decisions}
        evidence_ids = {item.id for item in state.evidence}
        for node in tuple(item for item in plan.nodes if item.status == "awaiting_review"):
            output_ids = tuple(node.planned_output_artifact_ids.values())
            if not output_ids or not set(output_ids) <= set(decisions):
                continue
            node_decisions = tuple(decisions[artifact_id] for artifact_id in output_ids)
            families = {
                "retain" if item.action in RETAIN_DECISION_ACTIONS
                else "exclude" if item.action in EXCLUDE_DECISION_ACTIONS
                else "reexecute" if item.action in REEXECUTE_DECISION_ACTIONS
                else "input" if item.action in INPUT_DECISION_ACTIONS
                else "revision" if item.action in REVISION_DECISION_ACTIONS
                else "stop"
                for item in node_decisions
            }
            if len(families) != 1:
                raise ValueError("one plan node cannot resolve its outputs with conflicting decision families")
            family = next(iter(families))
            if family != "retain":
                next_ids = {value for item in node_decisions for value in item.next_plan_node_ids}
                plan_nodes = {item.id: item for item in plan.nodes}
                if next_ids - set(plan_nodes) or node.id in next_ids:
                    raise ValueError("scientific decision triggers an unknown or self-referential plan node")
                if family == "reexecute" and any(plan_nodes[value].status not in {"pending", "ready"} for value in next_ids):
                    raise ValueError("rerun or method-switch target must be a pending revision node")
                status = {
                    "exclude": "skipped",
                    "reexecute": "superseded",
                    "input": "blocked",
                    "revision": "blocked",
                    "stop": "skipped",
                }[family]
                state = self._status(state, plan.id, node, status, node.attempt)
                plan = self._active_plan(state)
                continue
            execution = self._resolved_completed_execution(state, node)
            for evidence in self._evidence_mapper(execution, node, state):
                if evidence.id in evidence_ids:
                    continue
                state = apply_event(
                    state,
                    "evidence_added",
                    {"evidence": evidence.to_dict()},
                    rationale="Release reviewed module evidence after an explicit retain decision.",
                    affected_artifact_ids=(evidence.artifact_id,),
                    affected_hypothesis_ids=(evidence.hypothesis_id,),
                    replacement_action_ids=(node.id,),
                )
                evidence_ids.add(evidence.id)
            state = self._status(state, plan.id, node, "completed", node.attempt)
            plan = self._active_plan(state)
        return state

    @staticmethod
    def _decision_triggered_node_is_ready(state: ProjectState, plan: ResearchDAG, node: PlanNode) -> bool:
        """Allow a declared revision node to replace a reviewed, superseded dependency."""
        decisions = tuple(
            item
            for item in state.scientific_decisions
            if item.action in REEXECUTE_DECISION_ACTIONS and node.id in item.next_plan_node_ids
        )
        if not decisions:
            return False
        producer_by_artifact = {
            artifact_id: candidate
            for candidate in plan.nodes
            for artifact_id in candidate.planned_output_artifact_ids.values()
        }
        source_nodes = {
            producer_by_artifact[item.artifact_id].id
            for item in decisions
            if item.artifact_id in producer_by_artifact
        }
        by_id = {item.id: item for item in plan.nodes}
        return all(
            dependency in source_nodes and by_id[dependency].status == "superseded"
            for dependency in node.dependencies
            if by_id[dependency].status != "completed"
        )

    def advance(self, state: ProjectState, plan: ResearchDAG) -> CycleResult:
        if plan.id not in {item.id for item in state.plans}:
            parent = next((item for item in state.plans if item.id == plan.parent_plan_id), None)
            state = apply_event(
                state,
                "plan_created" if plan.parent_plan_id is None else "plan_revised",
                {"plan": plan.to_dict(), "activate": True},
                rationale="Register and activate the validated research DAG before execution.",
                superseded_action_ids=tuple(node.id for node in parent.nodes if node.status in {"blocked", "failed", "superseded"}) if parent else (),
                replacement_action_ids=tuple(node.id for node in plan.nodes),
            )
        elif state.active_plan_id != plan.id:
            raise ValueError("supplied plan is not the active project plan")
        executions: list[NodeExecution] = []
        findings: list[QualityFinding] = []
        stop_reason = "blocked"

        while True:
            active = self._active_plan(state)
            if self._policy.require_scientific_review:
                state = self._release_reviewed_nodes(state, active)
            active = self._active_plan(state)
            completed_ids = {node.id for node in active.nodes if node.status == "completed"}
            dependency_ready = tuple(
                node
                for node in active.nodes
                if node.status in {"pending", "ready"}
                and (
                    set(node.dependencies) <= completed_ids
                    or self._decision_triggered_node_is_ready(state, active, node)
                )
            )
            approved_nodes = {item.plan_node_id for item in state.analysis_admissions if item.approved}
            publication_blocked = {
                node.id
                for node in dependency_ready
                if self._policy.require_evidence_map_for_publication
                and self._registry.get(node.module_id).module_type == "delivery"
                and "publication" in self._registry.get(node.module_id).domains
                and not self._delivery_publication_is_reachable(state, node.id)
            }
            pending = tuple(
                node for node in dependency_ready
                if (not self._policy.require_approved_admission or node.id in approved_nodes)
                and node.id not in publication_blocked
            )
            if not pending:
                statuses = {node.status for node in active.nodes}
                active_output_artifact_ids = {
                    artifact_id
                    for node in active.nodes
                    for artifact_id in node.planned_output_artifact_ids.values()
                }
                active_decisions = tuple(
                    item
                    for item in state.scientific_decisions
                    if item.artifact_id in active_output_artifact_ids
                )
                if statuses == {"completed"}:
                    stop_reason = "plan_completed"
                elif publication_blocked:
                    stop_reason = "awaiting_evidence_map"
                elif dependency_ready and self._policy.require_approved_admission:
                    stop_reason = "awaiting_analysis_admission"
                elif "awaiting_review" in statuses and self._policy.require_scientific_review:
                    stop_reason = "awaiting_artifact_review"
                elif "awaiting_observed_execution" in statuses or "prepared" in statuses:
                    stop_reason = "awaiting_observed_execution"
                elif any(
                    item.action in INPUT_DECISION_ACTIONS
                    for item in active_decisions
                ) and "blocked" in statuses:
                    stop_reason = "awaiting_additional_data"
                elif any(
                    item.action in REVISION_DECISION_ACTIONS
                    for item in active_decisions
                ) and "blocked" in statuses:
                    stop_reason = "awaiting_plan_revision"
                elif any(
                    item.action in STOP_DECISION_ACTIONS
                    for item in active_decisions
                ) and "skipped" in statuses:
                    stop_reason = "scientific_branch_stopped"
                elif any(
                    item.action in EXCLUDE_DECISION_ACTIONS
                    for item in active_decisions
                ) and "skipped" in statuses:
                    stop_reason = "scientific_evidence_excluded"
                elif "superseded" in statuses:
                    stop_reason = "awaiting_revision_node"
                elif "failed" in statuses:
                    stop_reason = "failed"
                else:
                    stop_reason = "blocked"
                break
            ready = tuple(sorted(pending, key=lambda node: node.id))
            for node in ready:
                state = self._status(state, active.id, node, "running", node.attempt + 1)
            running_plan = self._active_plan(state)
            running = tuple(next(item for item in running_plan.nodes if item.id == node.id) for node in ready)
            snapshot = state
            with ThreadPoolExecutor(max_workers=min(self._policy.parallel_workers, len(running)), thread_name_prefix="biomed-node") as pool:
                futures = {node.id: pool.submit(self._execute, snapshot, running_plan, node) for node in running}
                batch = tuple(futures[node_id].result() for node_id in sorted(futures))
            for execution in batch:
                current_plan = self._active_plan(state)
                node = next(item for item in current_plan.nodes if item.id == execution.node_id)
                for finding in execution.quality_findings:
                    findings.append(finding)
                    state = apply_event(
                        state,
                        "quality_finding_recorded",
                        {"finding": finding.to_dict()},
                        rationale="Preserve a structured scientific quality finding from node execution.",
                        trigger_finding_ids=(finding.id,),
                        affected_artifact_ids=tuple(value for value in execution.input_artifact_ids if value in {item.id for item in state.artifacts}),
                    )
                state = apply_event(
                    state,
                    "node_execution_recorded",
                    {"execution": execution.to_dict()},
                    rationale="Preserve the bounded module execution and compatibility provenance.",
                    affected_artifact_ids=tuple(value for value in execution.input_artifact_ids if value in {item.id for item in state.artifacts}),
                    affected_hypothesis_ids=node.target_hypothesis_ids,
                    replacement_action_ids=(node.id,),
                )
                if execution.status == "completed":
                    state = self._record_completed_receipt_chain(state, node, execution)
                    if self._policy.require_scientific_review:
                        state = self._status(state, current_plan.id, node, "awaiting_review", node.attempt)
                    else:
                        for evidence in self._evidence_mapper(execution, node, state):
                            state = apply_event(
                                state,
                                "evidence_added",
                                {"evidence": evidence.to_dict()},
                                rationale="Link normalized module evidence to its target hypothesis.",
                                affected_artifact_ids=(evidence.artifact_id,),
                                affected_hypothesis_ids=(evidence.hypothesis_id,),
                                replacement_action_ids=(node.id,),
                            )
                        state = self._status(state, current_plan.id, node, "completed", node.attempt)
                elif execution.status == "awaiting_observed_execution":
                    state = apply_event(
                        state,
                        "execution_handoff_recorded",
                        {"handoff": execution.execution_handoff.to_dict()},
                        rationale="Record the prepared execution handoff without creating a scientific artifact.",
                        affected_hypothesis_ids=node.target_hypothesis_ids,
                        replacement_action_ids=(node.id,),
                    )
                    state = self._status(
                        state,
                        current_plan.id,
                        node,
                        "awaiting_observed_execution",
                        node.attempt,
                    )
                elif execution.status == "failed" and node.attempt < self._policy.max_node_attempts:
                    state = self._status(state, current_plan.id, node, "pending", node.attempt)
                else:
                    state = self._status(state, current_plan.id, node, execution.status, node.attempt)
                executions.append(execution)
            if self._policy.stop_on_fatal and any(finding.severity == "fatal" for finding in findings):
                stop_reason = "fatal_quality_gate"
                break

        active = self._active_plan(state)
        if stop_reason in {"blocked", "failed", "awaiting_plan_revision"} and active.revision < self._policy.max_plan_revisions:
            replanner = self._replanner if stop_reason == "awaiting_plan_revision" else (self._replanner or self._declared_alternative_replan)
            if replanner is None:
                return CycleResult(state, active, tuple(executions), (), stop_reason)
            revised = replanner(state, active, tuple(executions), tuple(findings))
            if revised is not None:
                if revised.parent_plan_id != active.id or revised.revision != active.revision + 1:
                    raise ValueError("replanner must create the next child revision of the active plan")
                old_modules = {node.module_id for node in active.nodes if node.status in {"blocked", "failed"}}
                replacement_modules = {node.module_id for node in revised.nodes}
                declared_alternatives = set()
                for module_id in old_modules:
                    declared_alternatives.update(self._registry.get(module_id).alternatives)
                if declared_alternatives and not replacement_modules & declared_alternatives:
                    raise ValueError("replanner did not replace a blocked module with one of its declared alternatives")
                if not replacement_modules <= {module.id for module in self._registry.all()}:
                    raise ValueError("replanner selected an unregistered module")
                followup = self.advance(state, revised)
                return CycleResult(
                    followup.state,
                    followup.active_plan,
                    (*tuple(executions), *followup.executions),
                    followup.assessments,
                    followup.stop_reason,
                )

        if stop_reason in {
            "awaiting_analysis_admission",
            "awaiting_artifact_review",
            "awaiting_observed_execution",
            "awaiting_evidence_map",
            "awaiting_additional_data",
            "awaiting_plan_revision",
            "awaiting_revision_node",
            "scientific_branch_stopped",
            "scientific_evidence_excluded",
        }:
            return CycleResult(state, self._active_plan(state), tuple(executions), (), stop_reason)

        assessments = []
        for hypothesis in state.hypotheses:
            assessment = assess_hypothesis(hypothesis, state.evidence, tuple(findings))
            assessments.append(assessment)
            if assessment.new_status != hypothesis.status:
                state = apply_event(
                    state,
                    "hypothesis_assessed",
                    {"hypothesis_id": hypothesis.id, "status": assessment.new_status},
                    rationale=assessment.rationale,
                    trigger_finding_ids=tuple(finding.id for finding in findings if finding.blocks_interpretation),
                    affected_hypothesis_ids=(hypothesis.id,),
                )
        return CycleResult(state, self._active_plan(state), tuple(executions), tuple(assessments), stop_reason)

    def resume(self, serialized_state: dict[str, object]) -> CycleResult:
        state = ProjectState.from_dict(serialized_state)
        plan = self._active_plan(state)
        if all(node.status == "completed" for node in plan.nodes):
            assessments = tuple(assess_hypothesis(item, state.evidence, ()) for item in state.hypotheses)
            return CycleResult(state, plan, (), assessments, "already_complete")
        return self.advance(state, plan)
