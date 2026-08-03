"""Deterministic support loop used by Codex to execute scientific plans.

This module does not call another language model. Codex supplies the objective
and structured actions; the loop records execution, evidence, limitations, and
delivery state so multi-step research remains auditable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping

from .models import EvidenceItem, ExecutionResult
from .research import ResearchAction, ResearchRecord, StageRecord
from .runner import run
from .kernel.artifacts import ScientificArtifact
from .kernel.artifact_store import ProjectArtifactStore
from .kernel.context import ProjectContext
from .kernel.hypotheses import Hypothesis
from .kernel.scientific_dependency import AnalysisAdmission
from .kernel.state import ProjectState, apply_event
from .modules.compatibility import detect_environment
from .modules.index import BUILTIN_ROOT
from .modules.registry import ModuleRegistry
from .orchestration.controller import CycleResult, ResearchController
from .orchestration.graph import build_capability_graph
from .orchestration.planner import PlanningRequest, plan_research


Executor = Callable[..., ExecutionResult]


@dataclass(frozen=True)
class AssistantResult:
    record: ResearchRecord
    summary: str
    evidence: tuple[EvidenceItem, ...]
    user_output: str


def _evidence_from_execution(execution: ExecutionResult) -> tuple[EvidenceItem, ...]:
    evidence = list(execution.evidence)
    output = execution.output
    summary = output.get("summary") if isinstance(output, dict) else None
    if isinstance(summary, dict):
        database = str(summary.get("database", "NCBI"))
        for record in summary.get("records", ()):
            if not isinstance(record, dict):
                continue
            identifier = str(record.get("uid") or record.get("id") or record.get("accessionversion") or "record")
            label = str(record.get("name") or record.get("title") or record.get("caption") or identifier)
            description = str(record.get("description") or record.get("summary") or "Database record returned")
            evidence.append(
                EvidenceItem(
                    identifier=identifier,
                    source=f"NCBI {database}",
                    claim=f"{label}: {description}",
                )
            )
    return tuple(evidence)


class ResearchAssistant:
    def __init__(
        self,
        *,
        executor: Executor = run,
        registry: ModuleRegistry | None = None,
        controller: ResearchController | None = None,
        artifact_store: ProjectArtifactStore | None = None,
        allow_mutation: bool = False,
    ) -> None:
        self._executor = executor
        self._registry = registry or ModuleRegistry.discover(BUILTIN_ROOT)
        self._controller = controller or ResearchController(
            self._registry,
            environment_provider=detect_environment,
            artifact_store=artifact_store,
            allow_mutation=allow_mutation,
        )

    def start(
        self,
        context: ProjectContext,
        *,
        artifacts: tuple[ScientificArtifact, ...],
        hypotheses: tuple[Hypothesis, ...],
        requests: tuple[PlanningRequest, ...],
        admissions: tuple[AnalysisAdmission, ...] = (),
    ) -> CycleResult:
        if not isinstance(context, ProjectContext) or not artifacts or not hypotheses or not requests:
            raise ValueError("stateful research requires context, artifacts, hypotheses, and planning requests")
        state = ProjectState.create(context)
        for hypothesis in hypotheses:
            state = apply_event(
                state,
                "hypothesis_added",
                {"hypothesis": hypothesis.to_dict()},
                rationale="Register a falsifiable hypothesis through the unified assistant entry.",
                affected_hypothesis_ids=(hypothesis.id,),
            )
        for artifact in artifacts:
            state = apply_event(
                state,
                "artifact_registered",
                {"artifact": artifact.to_dict()},
                rationale="Register a typed project artifact through the unified assistant entry.",
                affected_artifact_ids=(artifact.id,),
            )
        graph = build_capability_graph(self._registry)
        plan = plan_research(state, self._registry, graph, requests)
        if admissions:
            if {item.plan_node_id for item in admissions} != {node.id for node in plan.nodes}:
                raise ValueError("assistant admissions must cover every planned analysis node exactly once")
            state = apply_event(
                state,
                "plan_created",
                {"plan": plan.to_dict(), "activate": True},
                rationale="Register the exact assistant-generated plan before scientific admission.",
                replacement_action_ids=tuple(node.id for node in plan.nodes),
            )
            for admission in admissions:
                state = apply_event(
                    state,
                    "analysis_admission_recorded",
                    {"admission": admission.to_dict()},
                    rationale="Record an explicit analysis admission before execution.",
                    affected_hypothesis_ids=admission.hypothesis_ids,
                    replacement_action_ids=(admission.plan_node_id,),
                )
        return self._controller.advance(state, plan)

    def continue_project(
        self,
        state: ProjectState | Mapping[str, object],
        *,
        requests: tuple[PlanningRequest, ...] = (),
        admissions: tuple[AnalysisAdmission, ...] = (),
    ) -> CycleResult:
        current = state if isinstance(state, ProjectState) else ProjectState.from_dict(state)
        if requests:
            plan = plan_research(current, self._registry, build_capability_graph(self._registry), requests)
            if admissions:
                if {item.plan_node_id for item in admissions} != {node.id for node in plan.nodes}:
                    raise ValueError("assistant admissions must cover every revised plan node exactly once")
                current = apply_event(
                    current,
                    "plan_created" if plan.parent_plan_id is None else "plan_revised",
                    {"plan": plan.to_dict(), "activate": True},
                    rationale="Register the requested continuation plan before scientific admission.",
                    replacement_action_ids=tuple(node.id for node in plan.nodes),
                )
                for admission in admissions:
                    current = apply_event(
                        current,
                        "analysis_admission_recorded",
                        {"admission": admission.to_dict()},
                        rationale="Record an explicit continuation admission before execution.",
                        affected_hypothesis_ids=admission.hypothesis_ids,
                        replacement_action_ids=(admission.plan_node_id,),
                    )
            return self._controller.advance(current, plan)
        return self._controller.resume(current.to_dict())

    def run(
        self,
        objective: str,
        *,
        actions: Iterable[ResearchAction] = (),
        inputs: dict[str, object] | None = None,
        require_design: bool = False,
        allow_mutation: bool = False,
    ) -> AssistantResult:
        if not objective.strip():
            raise ValueError("research objective must not be empty")
        plan = tuple(actions)
        stages: list[StageRecord] = [StageRecord("frame", "completed", "The scientific objective was captured explicitly.")]
        stages.append(
            StageRecord(
                "plan",
                "completed" if plan else "skipped",
                "A structured capability sequence was supplied." if plan else "No external capability was needed or supplied.",
            )
        )
        executions: list[ExecutionResult] = []
        evidence: list[EvidenceItem] = []
        for action in plan:
            execution = self._executor(action.capability_id, action.inputs, allow_mutation=allow_mutation)
            if not isinstance(execution, ExecutionResult):
                raise TypeError("executor must return ExecutionResult")
            executions.append(execution)
            evidence.extend(_evidence_from_execution(execution))
        stages.append(
            StageRecord(
                "investigate",
                "completed" if executions else "skipped",
                f"Executed {len(executions)} bounded scientific action(s)." if executions else "No external investigation was requested.",
            )
        )
        stages.append(
            StageRecord(
                "design",
                "completed" if require_design else "skipped",
                "Validation design was retained as an explicit downstream decision." if require_design else "The objective did not require a new validation design.",
            )
        )
        stages.append(
            StageRecord(
                "interpret",
                "completed",
                f"Normalized {len(evidence)} evidence record(s) for Codex synthesis." if evidence else "Interpretation is limited to the supplied objective.",
            )
        )
        summary = (
            f"Completed {len(executions)} research action(s) and grounded the objective with {len(evidence)} evidence record(s)."
            if executions
            else "The objective was framed without external execution."
        )
        limitations = () if evidence else ("No external evidence record was retrieved in this run.",)
        next_decisions = (
            ("Select an orthogonal experimental or computational validation strategy.",) if require_design else ()
        )
        stages.append(StageRecord("deliver", "completed", "A scientific summary and evidence ledger were prepared."))
        stages.append(StageRecord("audit", "completed", "Execution status, evidence, and limitations were recorded."))
        record = ResearchRecord(
            objective=objective,
            inputs=dict(inputs or {}),
            plan=plan,
            stages=tuple(stages),
            executions=tuple(executions),
            evidence=tuple(evidence),
            conclusions=tuple(item.claim for item in evidence),
            limitations=limitations,
            next_decisions=next_decisions,
            summary=summary,
        )
        evidence_text = " ".join(item.claim for item in evidence[:5])
        user_output = " ".join(part for part in (summary, evidence_text, " ".join(next_decisions), " ".join(limitations)) if part)
        return AssistantResult(record=record, summary=summary, evidence=tuple(evidence), user_output=user_output)
