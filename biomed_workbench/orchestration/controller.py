"""Dependency-aware execute, inspect, revise, resume, and stop controller."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable

from ..kernel.evidence import EvidenceRecord
from ..kernel.plans import PlanNode, ResearchDAG
from ..kernel.state import ProjectState, apply_event
from ..modules.compatibility import EnvironmentSnapshot
from ..modules.contract import ModuleManifest
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

    def __post_init__(self) -> None:
        if self.max_plan_revisions < 0 or self.max_node_attempts < 1 or not 1 <= self.parallel_workers <= 16:
            raise ValueError("controller policy bounds are invalid")
        if not isinstance(self.stop_on_fatal, bool):
            raise ValueError("controller stop_on_fatal must be boolean")


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
    ) -> None:
        self._registry = registry
        self._environment_provider = environment_provider
        self._node_executor = node_executor
        self._evidence_mapper = evidence_mapper or (lambda _execution, _node, _state: ())
        self._replanner = replanner
        self._policy = policy or ControllerPolicy()

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
            completed_ids = {node.id for node in active.nodes if node.status == "completed"}
            pending = tuple(node for node in active.nodes if node.status in {"pending", "ready"} and set(node.dependencies) <= completed_ids)
            if not pending:
                statuses = {node.status for node in active.nodes}
                if statuses == {"completed"}:
                    stop_reason = "plan_completed"
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
                    for value in execution.artifacts:
                        state = apply_event(
                            state,
                            "artifact_registered",
                            {"artifact": value.to_dict()},
                            rationale="Register a validated module output artifact for downstream dependencies.",
                            affected_artifact_ids=(value.id,),
                            affected_hypothesis_ids=node.target_hypothesis_ids,
                            replacement_action_ids=(node.id,),
                        )
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
                elif execution.status == "failed" and node.attempt < self._policy.max_node_attempts:
                    state = self._status(state, current_plan.id, node, "pending", node.attempt)
                else:
                    state = self._status(state, current_plan.id, node, execution.status, node.attempt)
                executions.append(execution)
            if self._policy.stop_on_fatal and any(finding.severity == "fatal" for finding in findings):
                stop_reason = "fatal_quality_gate"
                break

        active = self._active_plan(state)
        if stop_reason in {"blocked", "failed"} and self._replanner is not None and active.revision < self._policy.max_plan_revisions:
            revised = self._replanner(state, active, tuple(executions), tuple(findings))
            if revised is not None:
                if revised.parent_plan_id != active.id or revised.revision != active.revision + 1:
                    raise ValueError("replanner must create the next child revision of the active plan")
                old_modules = {node.module_id for node in active.nodes if node.status in {"blocked", "failed"}}
                replacement_modules = {node.module_id for node in revised.nodes}
                allowed_replacements = set(old_modules)
                for module_id in old_modules:
                    allowed_replacements.update(self._registry.get(module_id).alternatives)
                if not replacement_modules <= allowed_replacements | {node.module_id for node in active.nodes if node.status == "completed"}:
                    raise ValueError("replanner selected a module that is not a declared alternative")
                followup = self.advance(state, revised)
                return CycleResult(
                    followup.state,
                    followup.active_plan,
                    (*tuple(executions), *followup.executions),
                    followup.assessments,
                    followup.stop_reason,
                )

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
