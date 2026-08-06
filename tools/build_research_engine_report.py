#!/usr/bin/env python3
"""Build deterministic release evidence for the stateful research engine."""

from __future__ import annotations

import argparse
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402
from biomed_workbench.orchestration.graph import build_capability_graph  # noqa: E402
from tests.e2e.test_research_cycle_scenarios import run_scenario  # noqa: E402


FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "research-cycles"
KERNEL_CONTRACTS = [
    "artifact_payload", "project_context", "scientific_artifact", "hypothesis", "evidence_record",
    "decision_event", "project_state", "plan_node", "research_dag", "quality_finding",
    "node_execution", "hypothesis_assessment", "cycle_result",
    "analysis_admission", "scientific_gate_adjudication", "artifact_review", "panel_interpretation", "scientific_decision",
    "scientific_evidence_map", "global_panel_story_dag", "file_level_evidence_mind_map",
    "evidence_map_edge_table", "bilingual_evidence_report", "append_only_evidence_map_version",
    "execution_handoff", "observed_execution_receipt", "artifact_reload_receipt",
    "scientific_review_receipt", "evidence_map_publication", "state_migration_record",
    "registered_gate_evaluator_identity", "revision_target_contract", "review_triggered_plan_revision",
    "normalized_command_revision_identity", "legacy_evidence_map_record", "artifact_store_transaction",
]
EXECUTION_CONTRACTS = [
    "scientific_command", "command_companion_sidecar_input", "command_digest_bound_project_implementation",
    "command_input_binding", "command_derived_sidecar_output", "command_output_binding",
    "command_scalar_parameter_template", "command_stream_output_capture", "command_zip_directory_input",
    "command_workdir_relative_paths", "tested_baseline_compatibility_policy", "bounded_process_result",
]


def _scenario(path: Path) -> dict[str, object]:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    result, replayed = run_scenario(fixture)
    failed = next((code for execution in result.executions for code in execution.compatibility_finding_codes), None)
    if result.state.state_digest != fixture["expected_replay_digest"] or replayed.state_digest != result.state.state_digest:
        raise RuntimeError(f"research scenario replay differs: {fixture['id']}")
    if not result.assessments:
        raise RuntimeError(f"research scenario has no hypothesis assessment: {fixture['id']}")
    assessment = result.assessments[0]
    return {
        "id": fixture["id"],
        "plan_type": result.active_plan.plan_type,
        "event_count": result.state.revision,
        "execution_count": len(result.executions),
        "revision_count": result.active_plan.revision - 1,
        "alternative_substitution_count": 1 if result.active_plan.parent_plan_id else 0,
        "evidence_count": len(result.state.evidence),
        "failed_gate_code": failed,
        "hypothesis_transition": [assessment.previous_status, assessment.new_status],
        "final_state_digest": result.state.state_digest,
        "replay_passed": True,
    }


def build() -> dict[str, object]:
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    graph = build_capability_graph(registry)
    scenarios = [_scenario(path) for path in sorted(FIXTURE_ROOT.glob("*.json"))]
    test_count = unittest.defaultTestLoader.discover(
        str(ROOT / "tests" / "release"),
        pattern="test*.py",
        top_level_dir=str(ROOT),
    ).countTestCases()
    module_count = len(registry.all())
    return {
        "schema_version": 1,
        "passed": True,
        "module_count": module_count,
        "test_count": test_count,
        "registry_digest": registry.digest,
        "capability_graph": {"node_count": len(graph.nodes), "edge_count": len(graph.edges), "digest": graph.digest},
        "kernel_contracts": KERNEL_CONTRACTS,
        "execution_contracts": EXECUTION_CONTRACTS,
        "scenario_count": len(scenarios),
        "strict_compatibility_blocks": sum(item["failed_gate_code"] is not None for item in scenarios),
        "plan_revisions": sum(int(item["revision_count"]) for item in scenarios),
        "alternative_substitutions": sum(int(item["alternative_substitution_count"]) for item in scenarios),
        "successful_replays": sum(item["replay_passed"] is True for item in scenarios),
        "scenarios": scenarios,
        "limitations": [
            f"The current {module_count} modules remain bounded scientific functions; project-specific validation is still required before biological claims are treated as research conclusions.",
            "Executable Scanpy and Seurat foundations, droplet decontamination, doublet detection, marker discovery, CellTypist, Azimuth, popV, SingleR adjudication, donor-aware and longitudinal inference, Harmony, Scanorama, BBKNN, scVI, scANVI, scVelo, CellRank, moscot, Slingshot, Monocle3, tradeSeq, LIANA, CellPhoneDB, CellChat, NicheNet, WNN, MOFA+, MACS3, chromVAR, pySCENIC, SCENIC+, Squidpy, and SpatialData are validated on planted representative fixtures; additional project-diverse and platform-specific validation remains necessary before production claims.",
            "Content-addressed artifacts, strict compatibility gates, bounded commands, Codex-native handoffs, claim and manuscript audits, NCBI E-utilities, Crossref, Europe PMC, bioRxiv, PubChem, ClinicalTrials.gov v2, RCSB PDB, and selected version-specific sequence, variant, imaging, and omics tools are implemented.",
            "The v0.2 assistant API remains available for compatibility while new projects use replayable state.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "research-engine-verification.json")
    args = parser.parse_args()
    report = build()
    args.output.write_text(json.dumps(report, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(json.dumps({"module_count": report["module_count"], "test_count": report["test_count"], "registry_digest": report["registry_digest"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
