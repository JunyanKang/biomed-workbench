"""Deterministic support loop used by Codex to execute scientific plans.

This module does not call another language model. Codex supplies the objective
and structured actions; the loop records execution, evidence, limitations, and
delivery state so multi-step research remains auditable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from .models import EvidenceItem, ExecutionResult
from .research import ResearchAction, ResearchRecord, StageRecord
from .runner import run


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
    def __init__(self, *, executor: Executor = run) -> None:
        self._executor = executor

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
