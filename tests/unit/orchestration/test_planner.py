import tempfile
import unittest
from pathlib import Path

from biomed_workbench.kernel.artifacts import ScientificArtifact
from biomed_workbench.kernel.state import ProjectState, apply_event
from biomed_workbench.modules.registry import ModuleRegistry
from biomed_workbench.orchestration.graph import build_capability_graph
from biomed_workbench.orchestration.planner import PlanningError, PlanningRequest, plan_research
from tests.unit.kernel.test_context import project_context
from tests.unit.kernel.test_hypotheses import hypothesis
from tests.unit.test_module_contract import valid_manifest_payload
from tests.unit.test_module_registry import write_manifest


def inline_artifact(artifact_id, artifact_type, quality_status="passed", format_name="inline-json", format_version="1"):
    return ScientificArtifact.create(
        id=artifact_id,
        artifact_type=artifact_type,
        schema_version="1.0",
        format_name=format_name,
        format_version=format_version,
        compression="none",
        orientation="request-object",
        indexes=(),
        producing_module_id=None,
        producing_module_version=None,
        source_artifact_ids=(),
        scientific_scope={"species": "human", "sample_id": "s1"},
        experimental_unit="independent-organoid-line",
        denominator="four-independent-lines",
        processing_level="declared",
        quality_status=quality_status,
        coordinate_system=None,
        genome_build=None,
        annotation_release=None,
        identifier_namespace=None,
        producer_tool_versions={},
        content={"sample_id": "s1"},
    )


def state_with(*artifacts):
    state = ProjectState.create(project_context())
    state = apply_event(state, "hypothesis_added", {"hypothesis": hypothesis().to_dict()}, rationale="Register the planning hypothesis.")
    for value in artifacts:
        state = apply_event(state, "artifact_registered", {"artifact": value.to_dict()}, rationale="Register a planning input artifact.")
    return state


def module_payload(module_id, input_type, output_type, *, alternatives=(), maturity="validated", credentials=()):
    payload = valid_manifest_payload()
    payload.update(
        {
            "id": module_id,
            "title": module_id.replace("-", " ").title(),
            "description": f"Execute {module_id} with explicit typed artifact and scientific quality contracts.",
            "intents": [module_id.replace("-", " ")],
            "questions": [f"What validated result does {module_id} produce?"],
            "maturity": maturity,
            "alternatives": list(alternatives),
            "credentials": list(credentials),
        }
    )
    payload["input_artifacts"][0]["artifact_type"] = input_type
    payload["output_artifacts"][0]["artifact_type"] = output_type
    payload["input_artifacts"][0]["formats"][0]["orientations"] = ["request-object"]
    payload["output_artifacts"][0]["formats"][0]["orientations"] = ["request-object"]
    return payload


def workflow_registry(payloads):
    temporary = tempfile.TemporaryDirectory()
    root = Path(temporary.name)
    for payload in payloads:
        write_manifest(root, payload)
    return temporary, ModuleRegistry.discover(root)


class PlannerTests(unittest.TestCase):
    def test_builtin_primer_selection_pcr_chain_is_serial_and_unambiguous(self):
        from biomed_workbench.modules.index import BUILTIN_ROOT

        base = inline_artifact("artifact-template", "sequence_set").to_dict()
        base.pop("content_digest")
        base["content"] = {"template": "GCGTACGATCGATGCTAGCTAGGCTAACGTTAGCGATCGTACGATCGATGCTAGCATCGATGCGTACGATCG"}
        artifact = ScientificArtifact.create(**base)
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        request = PlanningRequest("request-pcr", "pcr_amplicon_evidence", (hypothesis().id,), ("pcr-product",))

        plan = plan_research(state_with(artifact), registry, build_capability_graph(registry), (request,))

        self.assertEqual(plan.plan_type, "serial")
        self.assertEqual([node.module_id for node in plan.nodes], ["primer-design", "pcr-primer-pair-selection", "pcr-amplicon-simulation"])
    def test_builtin_single_plan_uses_exact_available_artifact_contract(self):
        from biomed_workbench.modules.index import BUILTIN_ROOT

        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        state = state_with(inline_artifact("artifact-counts", "count_matrix"))
        request = PlanningRequest("request-quality", "quality_report", (hypothesis().id,), ("cell-state-association",))

        plan = plan_research(state, registry, build_capability_graph(registry), (request,))

        self.assertEqual(plan.plan_type, "single")
        self.assertEqual(len(plan.nodes), 1)
        self.assertEqual(plan.nodes[0].module_id, "single-cell-qc")
        self.assertEqual(plan.nodes[0].input_bindings["single_cell_counts"], "artifact-counts")

    def test_serial_parallel_and_mixed_dags_follow_artifact_dependencies(self):
        temporary, registry = workflow_registry(
            (
                module_payload("normalize-matrix", "count_matrix", "normalized_matrix"),
                module_payload("test-contrast", "normalized_matrix", "contrast_result"),
                module_payload("draft-claim", "contrast_result", "claim_set"),
                module_payload("measure-image", "image_collection", "image_measurements"),
            )
        )
        self.addCleanup(temporary.cleanup)
        state = state_with(inline_artifact("artifact-counts", "count_matrix"), inline_artifact("artifact-images", "image_collection"))
        graph = build_capability_graph(registry)
        claim = PlanningRequest("request-claim", "claim_set", (hypothesis().id,), ("cell-state-association",))
        image = PlanningRequest("request-image", "image_measurements", (hypothesis().id,), ("orthogonal-validation",))
        normalized = PlanningRequest("request-normalized", "normalized_matrix", (hypothesis().id,), ("cell-state-association",))

        serial = plan_research(state, registry, graph, (claim,))
        parallel = plan_research(state, registry, graph, (normalized, image))
        mixed = plan_research(state, registry, graph, (claim, image))

        self.assertEqual(serial.plan_type, "serial")
        self.assertEqual(parallel.plan_type, "parallel")
        self.assertEqual(mixed.plan_type, "mixed")
        self.assertEqual(len(serial.nodes), 3)
        downstream = next(node for node in serial.nodes if node.module_id == "test-contrast")
        upstream = next(node for node in serial.nodes if node.module_id == "normalize-matrix")
        self.assertEqual(downstream.dependencies, (upstream.id,))
        self.assertIn(downstream.input_bindings["records"], upstream.planned_output_artifact_ids.values())

    def test_unvalidated_format_major_quality_and_unknown_target_block_planning(self):
        from biomed_workbench.modules.index import BUILTIN_ROOT

        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        graph = build_capability_graph(registry)
        requests = (PlanningRequest("request-quality", "quality_report", (hypothesis().id,), ("cell-state-association",)),)
        invalid_states = (
            state_with(inline_artifact("artifact-counts", "count_matrix", format_name="h5ad", format_version="0.11")),
            state_with(inline_artifact("artifact-counts", "count_matrix", quality_status="major")),
        )
        for state in invalid_states:
            with self.subTest(state=state), self.assertRaises(PlanningError):
                plan_research(state, registry, graph, requests)
        with self.assertRaises(PlanningError):
            plan_research(invalid_states[0], registry, graph, (PlanningRequest("request-unknown", "unknown_artifact", (), ()),))

    def test_incompatible_primary_selects_only_its_declared_validated_alternative(self):
        primary = module_payload("primary-normalizer", "count_matrix", "normalized_matrix", alternatives=("alternative-normalizer",))
        alternative = module_payload("alternative-normalizer", "count_matrix", "normalized_matrix")
        temporary, registry = workflow_registry((primary, alternative))
        self.addCleanup(temporary.cleanup)
        state = state_with(inline_artifact("artifact-counts", "count_matrix"))

        plan = plan_research(
            state,
            registry,
            build_capability_graph(registry),
            (PlanningRequest("request-normalized", "normalized_matrix", (hypothesis().id,), ("cell-state-association",)),),
            compatible_module_ids=("alternative-normalizer",),
        )

        self.assertEqual(tuple(node.module_id for node in plan.nodes), ("alternative-normalizer",))

    def test_upstream_required_port_ignores_a_project_artifact_and_builds_its_declared_producer(self):
        resolver = module_payload("resolve-identifier", "count_matrix", "resolved_identifier")
        consumer = module_payload("retrieve-dependent-evidence", "resolved_identifier", "evidence_table")
        consumer["input_artifacts"][0]["source_policy"] = "upstream_required"
        temporary, registry = workflow_registry((resolver, consumer))
        self.addCleanup(temporary.cleanup)
        state = state_with(
            inline_artifact("artifact-counts", "count_matrix"),
            inline_artifact("artifact-untrusted-id", "resolved_identifier"),
        )

        plan = plan_research(
            state,
            registry,
            build_capability_graph(registry),
            (PlanningRequest("request-evidence", "evidence_table", (hypothesis().id,), ("identifier-evidence",)),),
        )

        self.assertEqual(plan.plan_type, "serial")
        resolver_node, consumer_node = plan.nodes
        self.assertEqual((resolver_node.module_id, consumer_node.module_id), ("resolve-identifier", "retrieve-dependent-evidence"))
        self.assertNotIn("artifact-untrusted-id", consumer_node.input_bindings.values())
        self.assertEqual(consumer_node.dependencies, (resolver_node.id,))

    def test_builtin_ortholog_plan_requires_identifier_resolution_before_retrieval(self):
        from biomed_workbench.modules.index import BUILTIN_ROOT

        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        state = state_with(inline_artifact("artifact-gene-query", "database_query"))

        plan = plan_research(
            state,
            registry,
            build_capability_graph(registry),
            (PlanningRequest("request-ortholog", "evidence_table", (hypothesis().id,), ("ortholog-record",)),),
            compatible_module_ids=("gene-identifier-resolution", "gene-ortholog-evidence"),
        )

        self.assertEqual(plan.plan_type, "serial")
        self.assertEqual(tuple(node.module_id for node in plan.nodes), ("gene-identifier-resolution", "gene-ortholog-evidence"))
        self.assertEqual(plan.nodes[1].dependencies, (plan.nodes[0].id,))


if __name__ == "__main__":
    unittest.main()
