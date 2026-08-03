#!/usr/bin/env python3
"""Persist and advance the mandatory scientific project state machine."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.kernel.artifact_store import ProjectArtifactStore  # noqa: E402
from biomed_workbench.kernel.artifacts import ScientificArtifact  # noqa: E402
from biomed_workbench.kernel.context import ProjectContext  # noqa: E402
from biomed_workbench.kernel.hypotheses import Hypothesis  # noqa: E402
from biomed_workbench.kernel.plans import ResearchDAG  # noqa: E402
from biomed_workbench.kernel.scientific_dependency import (  # noqa: E402
    AnalysisAdmission,
    ArtifactReview,
    ScientificDecision,
    ScientificDependencyBundle,
)
from biomed_workbench.kernel.scientific_evidence_map import (  # noqa: E402
    EvidenceMapPublication,
    EvidenceMapVersion,
    EvidenceUnitSpec,
    build_scientific_evidence_map,
)
from biomed_workbench.kernel.state import ProjectState, apply_event  # noqa: E402
from biomed_workbench.modules.compatibility import detect_environment  # noqa: E402
from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402
from biomed_workbench.orchestration.controller import ResearchController  # noqa: E402
from biomed_workbench.reporting.evidence_map_versions import publish_evidence_map_version  # noqa: E402


def _read(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain one JSON object")
    return payload


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _state(path: Path) -> ProjectState:
    return ProjectState.from_dict(_read(path))


def _record(state: ProjectState, event_type: str, value, *, field: str, rationale: str) -> ProjectState:
    artifact_ids: tuple[str, ...] = ()
    hypothesis_ids: tuple[str, ...] = ()
    action_ids: tuple[str, ...] = ()
    if isinstance(value, AnalysisAdmission):
        hypothesis_ids = value.hypothesis_ids
        action_ids = (value.plan_node_id,)
    elif isinstance(value, ArtifactReview):
        artifact_ids = (value.artifact_id,)
    elif isinstance(value, ScientificDecision):
        artifact_ids = (value.artifact_id,)
        hypothesis_ids = value.hypothesis_ids
        action_ids = value.next_plan_node_ids
    return apply_event(
        state,
        event_type,
        {field: value.to_dict()},
        rationale=rationale,
        affected_artifact_ids=artifact_ids,
        affected_hypothesis_ids=hypothesis_ids,
        replacement_action_ids=action_ids,
    )


def _summary(state: ProjectState) -> dict[str, object]:
    active = next((plan for plan in state.plans if plan.id == state.active_plan_id), None)
    return {
        "project_id": state.context.project_id,
        "state_digest": state.state_digest,
        "revision": state.revision,
        "active_plan_id": state.active_plan_id,
        "node_statuses": {node.id: node.status for node in active.nodes} if active else {},
        "analysis_admissions": len(state.analysis_admissions),
        "artifact_reviews": len(state.artifact_reviews),
        "scientific_decisions": len(state.scientific_decisions),
        "evidence_map_versions": len(state.evidence_map_versions),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser("init", help="initialize an append-only project state")
    initialize.add_argument("--context", required=True, type=Path)
    initialize.add_argument("--state", required=True, type=Path)
    initialize.add_argument("--hypotheses", type=Path)
    initialize.add_argument("--artifacts", type=Path)
    initialize.add_argument("--plan", type=Path)
    for name in ("admit", "review", "decide"):
        command = commands.add_parser(name)
        command.add_argument("--state", required=True, type=Path)
        command.add_argument("--input", required=True, type=Path)
    mapping = commands.add_parser("map", help="build, validate, publish, and register an evidence-map version")
    mapping.add_argument("--state", required=True, type=Path)
    mapping.add_argument("--workspace", required=True, type=Path)
    mapping.add_argument("--specs", required=True, type=Path)
    mapping.add_argument("--version", required=True, type=Path)
    mapping.add_argument("--publish-root", required=True, type=Path)
    resume = commands.add_parser("resume", help="resume the active strict controller from persisted state")
    resume.add_argument("--state", required=True, type=Path)
    resume.add_argument("--project-root", required=True, type=Path)
    resume.add_argument("--allow-mutation", action="store_true")
    args = parser.parse_args()

    if args.command == "init":
        if args.state.exists():
            raise ValueError("state file already exists; initialization never overwrites project history")
        state = ProjectState.create(ProjectContext.from_dict(_read(args.context)))
        setup_files = (args.hypotheses, args.artifacts, args.plan)
        if any(setup_files) and not all(setup_files):
            raise ValueError("project initialization requires --hypotheses, --artifacts, and --plan together")
        if all(setup_files):
            hypotheses = json.loads(args.hypotheses.read_text(encoding="utf-8"))
            artifacts = json.loads(args.artifacts.read_text(encoding="utf-8"))
            if not isinstance(hypotheses, list) or not isinstance(artifacts, list):
                raise ValueError("project hypotheses and artifacts must each contain one JSON array")
            for item in hypotheses:
                hypothesis = Hypothesis.from_dict(item)
                state = apply_event(
                    state,
                    "hypothesis_added",
                    {"hypothesis": hypothesis.to_dict()},
                    rationale="Register a falsifiable hypothesis during project initialization.",
                    affected_hypothesis_ids=(hypothesis.id,),
                )
            for item in artifacts:
                artifact = ScientificArtifact.from_dict(item)
                state = apply_event(
                    state,
                    "artifact_registered",
                    {"artifact": artifact.to_dict()},
                    rationale="Register an input artifact during project initialization.",
                    affected_artifact_ids=(artifact.id,),
                )
            plan = ResearchDAG.from_dict(_read(args.plan))
            state = apply_event(
                state,
                "plan_created",
                {"plan": plan.to_dict(), "activate": True},
                rationale="Register the initial project analysis plan before any admission.",
                replacement_action_ids=tuple(node.id for node in plan.nodes),
            )
    elif args.command in {"admit", "review", "decide"}:
        state = _state(args.state)
        payload = _read(args.input)
        if args.command == "admit":
            value = AnalysisAdmission.from_dict(payload)
            state = _record(state, "analysis_admission_recorded", value, field="admission", rationale="Record a user-approved scientific analysis admission.")
        elif args.command == "review":
            value = ArtifactReview.from_dict(payload)
            state = _record(state, "artifact_review_recorded", value, field="review", rationale="Record a bilingual scientific artifact review.")
        else:
            value = ScientificDecision.from_dict(payload)
            state = _record(state, "scientific_decision_recorded", value, field="decision", rationale="Record the explicit retain, exclude, rerun, or revise decision.")
    elif args.command == "map":
        state = _state(args.state)
        bundle = ScientificDependencyBundle.create(
            state,
            admissions=state.analysis_admissions,
            reviews=state.artifact_reviews,
            decisions=state.scientific_decisions,
        )
        specs_payload = json.loads(args.specs.read_text(encoding="utf-8"))
        if not isinstance(specs_payload, list):
            raise ValueError("evidence map specs must contain one JSON array")
        evidence_map = build_scientific_evidence_map(
            state,
            bundle,
            tuple(EvidenceUnitSpec.from_dict(item) for item in specs_payload),
            workspace_root=args.workspace.resolve(strict=True),
            version=EvidenceMapVersion.from_dict(_read(args.version)),
        )
        publish_evidence_map_version(
            evidence_map,
            args.publish_root,
            workspace_root=args.workspace.resolve(strict=True),
        )
        publication = EvidenceMapPublication.from_map(evidence_map)
        state = apply_event(
            state,
            "evidence_map_published",
            {"publication": publication.to_dict()},
            rationale="Publish a file-verified evidence map and bind its immutable digest to project state.",
            affected_artifact_ids=tuple(item.id for item in state.artifacts),
            affected_hypothesis_ids=tuple(item.id for item in state.hypotheses),
        )
    else:
        state = _state(args.state)
        if state.active_plan_id is None:
            raise ValueError("project state has no active plan to resume")
        root = args.project_root.resolve(strict=True)
        controller = ResearchController(
            ModuleRegistry.discover(BUILTIN_ROOT),
            environment_provider=detect_environment,
            artifact_store=ProjectArtifactStore(root / ".biomed-workbench" / "artifacts"),
            allow_mutation=args.allow_mutation,
        )
        cycle = controller.resume(state.to_dict())
        state = cycle.state
        summary = {**_summary(state), "stop_reason": cycle.stop_reason, "executions": [item.to_dict() for item in cycle.executions]}
        _write(args.state, state.to_dict())
        print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False))
        return 0

    _write(args.state, state.to_dict())
    print(json.dumps(_summary(state), indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"code": type(exc).__name__, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        raise SystemExit(2)
