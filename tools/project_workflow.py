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
    ScientificGateAdjudication,
    validate_minimal_sufficient_admission,
)
from biomed_workbench.kernel.scientific_evidence_map import (  # noqa: E402
    EvidenceMapPublication,
    EvidenceMapVersion,
    EvidenceUnitSpec,
    build_scientific_evidence_map,
)
from biomed_workbench.kernel.state import ProjectState, apply_event  # noqa: E402
from biomed_workbench.kernel.project_governance import (  # noqa: E402
    ProjectLock,
    ResultStatusLedger,
    create_project_lock,
    transition_result_status,
)
from biomed_workbench.kernel.execution_chain import validate_revision_target_contract  # noqa: E402
from biomed_workbench.kernel.environment_identity import persist_analysis_environment_record  # noqa: E402
from biomed_workbench.modules.compatibility import detect_environment  # noqa: E402
from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402
from biomed_workbench.orchestration.controller import ResearchController  # noqa: E402
from biomed_workbench.orchestration.execution_ingest import ingest_execution_bundle  # noqa: E402
from biomed_workbench.orchestration.revision import prepare_plan_revision  # noqa: E402
from biomed_workbench.orchestration.state_migration import (  # noqa: E402
    assess_republication_prerequisites,
    migrate_map_bound_v1_state,
    upgrade_state_migration_contract_1_1,
)
from biomed_workbench.reporting.evidence_map_versions import (  # noqa: E402
    abort_prepared_evidence_map_publication,
    complete_evidence_map_publication_recovery,
    inspect_evidence_map_publication_recovery,
    publish_evidence_map_transaction,
)
from biomed_workbench.reporting.result_view import build_result_view  # noqa: E402
from biomed_workbench.reporting.analysis_html import write_analysis_report  # noqa: E402
from biomed_workbench.project_import import (  # noqa: E402
    confirm_existing_project_map,
    discover_existing_project,
)
from biomed_workbench.research_modes import assess_research_mode  # noqa: E402
from biomed_workbench.domain_context import validate_domain_context  # noqa: E402


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
    elif isinstance(value, ScientificGateAdjudication):
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
        "gate_adjudications": len(state.gate_adjudications),
        "scientific_decisions": len(state.scientific_decisions),
        "execution_handoffs": len(state.execution_handoffs),
        "observed_executions": len(state.observed_executions),
        "artifact_reloads": len(state.artifact_reloads),
        "execution_reviews": len(state.execution_reviews),
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
    for name in ("admit", "adjudicate", "review", "decide"):
        command = commands.add_parser(name)
        command.add_argument("--state", required=True, type=Path)
        command.add_argument("--input", required=True, type=Path)
    prepare_revision = commands.add_parser(
        "prepare-revision",
        help="prepare a registry-validated child plan after source-output review and before decision",
    )
    prepare_revision.add_argument("--state", required=True, type=Path)
    prepare_revision.add_argument("--input", required=True, type=Path)
    mapping = commands.add_parser("map", help="build, validate, publish, and register an evidence-map version")
    mapping.add_argument("--state", required=True, type=Path)
    mapping.add_argument("--workspace", required=True, type=Path)
    mapping.add_argument("--specs", required=True, type=Path)
    mapping.add_argument("--version", required=True, type=Path)
    mapping.add_argument("--publish-root", required=True, type=Path)
    mapping.add_argument(
        "--authorize-delivery-node",
        action="append",
        default=[],
        help="authorize one exact publication-delivery node from its retained upstream evidence slice",
    )
    recovery = commands.add_parser("map-recovery", help="inspect interrupted evidence-map publication state without modifying files")
    recovery.add_argument("--state", required=True, type=Path)
    recovery.add_argument("--publish-root", required=True, type=Path)
    recovery.add_argument("--complete", action="store_true", help="complete a verified files-published/state-pending transaction")
    recovery.add_argument("--abort-prepared", action="store_true", help="abandon a verified prepared transaction before immutable files exist")
    ingest = commands.add_parser("ingest-execution", help="validate and ingest one observed execution against its recorded handoff")
    ingest.add_argument("--state", required=True, type=Path)
    ingest.add_argument("--input", required=True, type=Path)
    ingest.add_argument("--project-root", required=True, type=Path)
    resume = commands.add_parser("resume", help="resume the active strict controller from persisted state")
    resume.add_argument("--state", required=True, type=Path)
    resume.add_argument("--project-root", required=True, type=Path)
    resume.add_argument(
        "--evidence-map-root",
        type=Path,
        help="immutable evidence-map publication root; required before a publication delivery can be released",
    )
    resume.add_argument("--allow-mutation", action="store_true")
    lock = commands.add_parser("lock", help="freeze project-wide analysis and figure identities")
    lock.add_argument("--state", required=True, type=Path)
    lock.add_argument("--workspace", required=True, type=Path)
    lock.add_argument("--input", required=True, type=Path)
    lock.add_argument("--output", required=True, type=Path)
    status = commands.add_parser("result-status", help="apply a lock-bound result status transition")
    status.add_argument("--state", required=True, type=Path)
    status.add_argument("--workspace", required=True, type=Path)
    status.add_argument("--lock", required=True, type=Path)
    status.add_argument("--ledger", required=True, type=Path)
    status.add_argument("--artifact", required=True)
    status.add_argument("--to", required=True, choices=("FORMAL", "CANDIDATE", "SENSITIVITY", "DEPRECATED"))
    status.add_argument("--rationale", required=True)
    status.add_argument("--figure-contract-digest")
    view = commands.add_parser("view", help="show scientific results first; reproducibility and audit detail are opt-in")
    view.add_argument("--state", required=True, type=Path)
    view.add_argument("--ledger", type=Path)
    view.add_argument("--mode", choices=("result", "reproducibility", "audit"), default="result")
    report = commands.add_parser("report", help="deliver reviewed project results as a verified HTML report")
    report.add_argument("--state", required=True, type=Path)
    report.add_argument("--ledger", type=Path)
    report.add_argument("--project-root", required=True, type=Path)
    report.add_argument("--output-directory", required=True, type=Path)
    report.add_argument("--title", default="")
    report.add_argument("--language", choices=("auto", "zh-CN", "en"), default="auto")
    report.add_argument("--without-markdown-companion", action="store_true")
    import_existing = commands.add_parser("import-existing", help="scan an established project without modifying it")
    import_existing.add_argument("--project-root", required=True, type=Path)
    import_existing.add_argument("--output", required=True, type=Path)
    confirm_import = commands.add_parser("confirm-import", help="confirm or reject every proposed project relation")
    confirm_import.add_argument("--candidate-map", required=True, type=Path)
    confirm_import.add_argument("--decisions", required=True, type=Path)
    confirm_import.add_argument("--output", required=True, type=Path)
    mode = commands.add_parser("mode", help="inspect the requirements of an exploration, formalization, or submission phase")
    mode.add_argument("--state", required=True, type=Path)
    mode.add_argument("--name", required=True, choices=("EXPLORE", "FORMALIZE", "SUBMISSION"))
    domain_context = commands.add_parser(
        "domain-context",
        help="validate project-owned biological context, literature anchors, and inference boundaries",
    )
    domain_context.add_argument("--input", required=True, type=Path)
    migrate = commands.add_parser(
        "migrate-state-v1",
        help="verify a map-bound v1 state and write a distinct v2 state awaiting map republication",
    )
    migrate.add_argument("--legacy-state", required=True, type=Path)
    migrate.add_argument("--state", required=True, type=Path)
    migrate.add_argument("--evidence-map-root", required=True, type=Path)
    migrate.add_argument(
        "--delivery-node",
        action="append",
        default=[],
        help="evaluate the exact delivery node with the normal delivery validator; repeat as needed",
    )
    upgrade = commands.add_parser(
        "upgrade-state-migration-1-1",
        help="verify a contract-1.1.0 v2 state and write a distinct contract-1.2.0 successor",
    )
    upgrade.add_argument("--prior-state", required=True, type=Path)
    upgrade.add_argument("--state", required=True, type=Path)
    upgrade.add_argument("--evidence-map-root", required=True, type=Path)
    upgrade.add_argument(
        "--delivery-node",
        action="append",
        default=[],
        help="evaluate the exact delivery node with the normal delivery validator; repeat as needed",
    )
    args = parser.parse_args()

    if args.command == "import-existing":
        if args.output.exists():
            raise ValueError("project import never overwrites an existing candidate map")
        payload = discover_existing_project(args.project_root)
        _write(args.output, payload)
        print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
        return 0
    if args.command == "confirm-import":
        if args.output.exists():
            raise ValueError("confirmed project mapping never overwrites an existing file")
        payload = confirm_existing_project_map(_read(args.candidate_map), _read(args.decisions))
        _write(args.output, payload)
        print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
        return 0
    if args.command == "mode":
        payload = assess_research_mode(_state(args.state), args.name)
        print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
        return 0
    if args.command == "domain-context":
        payload = validate_domain_context(_read(args.input))
        print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
        return 0

    if args.command == "lock":
        if args.output.exists():
            raise ValueError("project lock publication never overwrites an existing revision")
        state = _state(args.state)
        project_lock = create_project_lock(_read(args.input), state, args.workspace)
        _write(args.output, project_lock.to_dict())
        print(json.dumps(project_lock.to_dict(), indent=2, sort_keys=True, ensure_ascii=False))
        return 0
    if args.command == "result-status":
        state = _state(args.state)
        project_lock = ProjectLock.from_dict(_read(args.lock))
        ledger = (
            ResultStatusLedger.from_dict(_read(args.ledger))
            if args.ledger.exists()
            else ResultStatusLedger.create(state.context.project_id, project_lock.digest)
        )
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        readiness_path = ROOT / "reports" / "execution-readiness.json"
        readiness = _read(readiness_path)
        if readiness.get("registry_digest") != registry.digest:
            raise ValueError("execution-readiness report is not bound to the active module registry")
        artifact = next((item for item in state.artifacts if item.id == args.artifact), None)
        record = next(
            (
                item for item in readiness.get("records", [])
                if artifact is not None and item.get("module_id") == artifact.producing_module_id
            ),
            {},
        )
        ledger = transition_result_status(
            ledger,
            state=state,
            lock=project_lock,
            workspace_root=args.workspace,
            artifact_id=args.artifact,
            to_status=args.to,
            validation_scope=record,
            rationale=args.rationale,
            figure_contract_digest=args.figure_contract_digest,
        )
        _write(args.ledger, ledger.to_dict())
        print(json.dumps(build_result_view(state, ledger), indent=2, sort_keys=True, ensure_ascii=False))
        return 0
    if args.command == "view":
        state = _state(args.state)
        ledger = ResultStatusLedger.from_dict(_read(args.ledger)) if args.ledger else None
        if args.mode == "result":
            payload = build_result_view(state, ledger)
        elif args.mode == "reproducibility":
            payload = build_result_view(state, ledger, include_reproducibility=True)
        else:
            payload = _summary(state)
        print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
        return 0
    if args.command == "report":
        state = _state(args.state)
        ledger = ResultStatusLedger.from_dict(_read(args.ledger)) if args.ledger else None
        payload = build_result_view(state, ledger, project_root=args.project_root)
        files = write_analysis_report(
            payload,
            args.output_directory,
            title=args.title,
            language=args.language,
            markdown_companion=not args.without_markdown_companion,
        )
        print(json.dumps({"ready_for_delivery": True, "report_files": files}, indent=2, sort_keys=True, ensure_ascii=False))
        return 0

    if args.command == "migrate-state-v1":
        if args.state.exists():
            raise ValueError("state migration never overwrites an existing target")
        if args.legacy_state.resolve() == args.state.resolve():
            raise ValueError("state migration target must differ from the legacy state")
        state = migrate_map_bound_v1_state(
            _read(args.legacy_state),
            evidence_map_root=args.evidence_map_root.resolve(strict=True),
        )
        _write(args.state, state.to_dict())
        summary = {
            **_summary(state),
            **assess_republication_prerequisites(
                state,
                delivery_node_ids=tuple(args.delivery_node),
            ),
            "legacy_state_preserved": True,
            "verified_legacy_evidence_maps": sum(
                len(item.legacy_evidence_maps) for item in state.state_migrations
            ),
        }
        print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False))
        return 0
    if args.command == "upgrade-state-migration-1-1":
        if args.state.exists():
            raise ValueError("state migration contract upgrade never overwrites an existing target")
        if args.prior_state.resolve() == args.state.resolve():
            raise ValueError("state migration contract upgrade target must differ from the prior state")
        prior_payload = _read(args.prior_state)
        state = upgrade_state_migration_contract_1_1(
            prior_payload,
            evidence_map_root=args.evidence_map_root.resolve(strict=True),
        )
        prior_state_digest = prior_payload["state_digest"]
        prior_migration = prior_payload["state_migrations"][0]
        _write(args.state, state.to_dict())
        migration = state.state_migrations[0]
        summary = {
            **_summary(state),
            **assess_republication_prerequisites(
                state,
                delivery_node_ids=tuple(args.delivery_node),
            ),
            "prior_state_preserved": True,
            "source_project_state_digest": prior_state_digest,
            "upgraded_project_state_digest": state.state_digest,
            "source_migration_digest": prior_migration.get("digest"),
            "upgraded_migration_digest": migration.digest,
            "verified_legacy_map_digests": [
                item.publication.map_digest for item in migration.legacy_evidence_maps
            ],
            "contract_upgrade_reason": migration.contract_upgrade.reason,
            "target_state_path": str(args.state.resolve()),
        }
        print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False))
        return 0
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
    elif args.command in {"admit", "adjudicate", "review", "decide"}:
        state = _state(args.state)
        payload = _read(args.input)
        if args.command == "admit":
            value = AnalysisAdmission.from_dict(payload)
            # Historical append-only states predate the minimal-sufficient
            # fields and must replay byte-for-byte. Newly policy-bound
            # admissions are enforced; legacy records remain readable without
            # being silently reclassified as a new scientific decision.
            if value.minimal_sufficient_policy_version is not None:
                validate_minimal_sufficient_admission(state, value)
            state = _record(state, "analysis_admission_recorded", value, field="admission", rationale="Record a user-approved scientific analysis admission.")
        elif args.command == "adjudicate":
            value = ScientificGateAdjudication.from_dict(payload)
            state = _record(
                state, "scientific_gate_adjudicated", value, field="adjudication",
                rationale="Record an independent adjudication of one exact observed scientific gate.",
            )
        elif args.command == "review":
            value = ArtifactReview.from_dict(payload)
            state = _record(state, "artifact_review_recorded", value, field="review", rationale="Record a bilingual scientific artifact review.")
        else:
            value = ScientificDecision.from_dict(payload)
            if value.action in {"rerun-same-method", "rerun-adjusted-parameters", "switch-method"}:
                validate_revision_target_contract(
                    state,
                    value,
                    registry=ModuleRegistry.discover(BUILTIN_ROOT),
                    require_pending=True,
                )
            state = _record(state, "scientific_decision_recorded", value, field="decision", rationale="Record the explicit retain, exclude, rerun, or revise decision.")
    elif args.command == "prepare-revision":
        state = _state(args.state)
        payload = _read(args.input)
        required = {
            "source_artifact_id", "action", "target_module_id", "parameter_overrides", "rationale"
        }
        allowed = required | {"target_input_bindings"}
        target_input_bindings = payload.get("target_input_bindings", {})
        if (
            not required <= set(payload)
            or set(payload) - allowed
            or not isinstance(payload["parameter_overrides"], dict)
            or not isinstance(target_input_bindings, dict)
        ):
            raise ValueError("prepare-revision input fields are incomplete or unsupported")
        revised = prepare_plan_revision(
            state,
            ModuleRegistry.discover(BUILTIN_ROOT),
            source_artifact_id=str(payload["source_artifact_id"]),
            action=str(payload["action"]),
            target_module_id=(str(payload["target_module_id"]) if payload["target_module_id"] is not None else None),
            parameter_overrides=payload["parameter_overrides"],
            rationale=str(payload["rationale"]),
            target_input_bindings=target_input_bindings,
        )
        state = apply_event(
            state,
            "plan_revised",
            {"plan": revised.to_dict(), "activate": True},
            rationale="Freeze a registry-validated node-level replacement after scientific review.",
            superseded_action_ids=tuple(
                node.revision_contract.source_node_id
                for node in revised.nodes
                if node.revision_contract is not None
            ),
            replacement_action_ids=tuple(node.id for node in revised.nodes),
        )
    elif args.command == "map":
        state = _state(args.state)
        version = EvidenceMapVersion.from_dict(_read(args.version))
        bundle = ScientificDependencyBundle.create(
            state,
            admissions=state.analysis_admissions,
            reviews=state.artifact_reviews,
            decisions=state.scientific_decisions,
            map_kind=version.map_kind,
        )
        specs_payload = json.loads(args.specs.read_text(encoding="utf-8"))
        if not isinstance(specs_payload, list):
            raise ValueError("evidence map specs must contain one JSON array")
        evidence_map = build_scientific_evidence_map(
            state,
            bundle,
            tuple(EvidenceUnitSpec.from_dict(item) for item in specs_payload),
            workspace_root=args.workspace.resolve(strict=True),
            version=version,
            authorized_delivery_node_ids=tuple(args.authorize_delivery_node),
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
        publish_evidence_map_transaction(
            evidence_map,
            publication,
            state,
            state_path=args.state,
            output_root=args.publish_root,
            workspace_root=args.workspace.resolve(strict=True),
        )
        print(json.dumps(_summary(state), indent=2, sort_keys=True, ensure_ascii=False))
        return 0
    elif args.command == "map-recovery":
        if args.complete and args.abort_prepared:
            raise ValueError("map recovery accepts only one modifying action at a time")
        if args.complete:
            result = complete_evidence_map_publication_recovery(
                args.publish_root,
                state_path=args.state,
            )
        elif args.abort_prepared:
            result = abort_prepared_evidence_map_publication(
                args.publish_root,
                state_path=args.state,
            )
        else:
            result = inspect_evidence_map_publication_recovery(args.publish_root, state_path=args.state)
        print(json.dumps(
            result,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        ))
        return 0
    elif args.command == "ingest-execution":
        state = _state(args.state)
        root = args.project_root.resolve(strict=True)
        state = ingest_execution_bundle(
            state,
            _read(args.input),
            registry=ModuleRegistry.discover(BUILTIN_ROOT),
            artifact_store=ProjectArtifactStore(root / ".biomed-workbench" / "artifacts"),
        )
        for receipt in state.observed_executions:
            if receipt.execution_environment is not None:
                persist_analysis_environment_record(root, receipt.execution_environment)
    else:
        state = _state(args.state)
        if state.active_plan_id is None:
            raise ValueError("project state has no active plan to resume")
        root = args.project_root.resolve(strict=True)
        controller = ResearchController(
            ModuleRegistry.discover(BUILTIN_ROOT),
            environment_provider=lambda manifest: detect_environment(
                manifest, project_root=str(root)
            ),
            artifact_store=ProjectArtifactStore(root / ".biomed-workbench" / "artifacts"),
            allow_mutation=args.allow_mutation,
            evidence_map_root=args.evidence_map_root,
        )
        cycle = controller.resume(state.to_dict())
        state = cycle.state
        for receipt in state.observed_executions:
            if receipt.execution_environment is not None:
                persist_analysis_environment_record(root, receipt.execution_environment)
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
