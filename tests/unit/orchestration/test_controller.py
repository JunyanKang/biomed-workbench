import threading
import time
import unittest
import json
import tempfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from biomed_workbench.kernel.artifacts import ScientificArtifact
from biomed_workbench.kernel.evidence import EvidenceRecord
from biomed_workbench.kernel.execution_receipts import ExecutionHandoff
from biomed_workbench.kernel.execution_chain import (
    delivery_slice_digest,
    validate_revision_target_contract,
    validate_delivery_prerequisites,
    validated_delivery_publication_is_current,
)
from biomed_workbench.kernel.identity import digest_value
from biomed_workbench.kernel.hypotheses import revise_hypothesis
from biomed_workbench.kernel.plans import PlanNode, ResearchDAG, RevisionTargetContract
from biomed_workbench.kernel.scientific_dependency import (
    AnalysisAdmission,
    ArtifactReview,
    ScientificDecision,
    ScientificDependencyBundle,
)
from biomed_workbench.kernel.scientific_evidence_map import (
    EvidenceFile,
    EvidenceMapPublication,
    EvidenceMapVersion,
    EvidenceUnitSpec,
    NarrativeSource,
    build_scientific_evidence_map,
)
from biomed_workbench.kernel.state import ProjectState, apply_event
from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.contract import (
    manifest_to_dict,
    module_manifest_digest,
    revision_alternative_to_dict,
)
from biomed_workbench.modules.registry import ModuleRegistry
from biomed_workbench.orchestration.controller import ControllerPolicy, ResearchController
from biomed_workbench.orchestration.execution import NodeExecution, execute_node
from biomed_workbench.orchestration.graph import build_capability_graph
from biomed_workbench.orchestration.planner import PlanningRequest, plan_research
from biomed_workbench.orchestration.revision import prepare_plan_revision
from biomed_workbench.reporting import (
    publish_evidence_map_transaction,
    verify_evidence_map_version_index,
)
from tests.unit.kernel.test_hypotheses import hypothesis
from tests.unit.orchestration.test_planner import inline_artifact, module_payload, state_with, workflow_registry


_StrictResearchController = ResearchController


def ResearchController(*args, **kwargs):
    """Keep pre-state-machine unit cases focused; dedicated tests exercise strict defaults."""
    policy = kwargs.pop("policy", ControllerPolicy())
    kwargs["policy"] = replace(
        policy,
        require_approved_admission=False,
        require_scientific_review=False,
        require_evidence_map_for_publication=False,
    )
    return _StrictResearchController(*args, **kwargs)


def execution_artifact(state, node, registry):
    manifest = registry.get(node.module_id)
    port = manifest.output_artifacts[0]
    artifact_id = node.planned_output_artifact_ids[port.name]
    source_ids = tuple(node.input_bindings.values())
    denominators = {artifact.denominator for artifact in state.artifacts if artifact.id in source_ids}
    return ScientificArtifact.create(
        id=artifact_id,
        artifact_type=port.artifact_type,
        schema_version="1.0",
        format_name="inline-json",
        format_version="1",
        compression="none",
        orientation="request-object",
        indexes=(),
        producing_module_id=manifest.id,
        producing_module_version=manifest.version,
        source_artifact_ids=source_ids,
        scientific_scope={"species": "human", "sample_id": "s1"},
        experimental_unit=state.context.experimental_unit,
        denominator=next(iter(denominators)),
        processing_level="derived",
        quality_status="passed",
        coordinate_system=None,
        genome_build=None,
        annotation_release=None,
        identifier_namespace=None,
        producer_tool_versions={},
        content={"module": manifest.id, "sample_id": "s1"},
    )


def completed_execution(state, node, registry):
    artifact = execution_artifact(state, node, registry)
    return NodeExecution(
        node_id=node.id,
        module_id=node.module_id,
        module_version=registry.get(node.module_id).version,
        status="completed",
        compatibility_row_id=registry.get(node.module_id).compatibility_matrix[0].id,
        input_artifact_ids=tuple(node.input_bindings.values()),
        output_artifact_ids=(artifact.id,),
        artifacts=(artifact,),
        quality_findings=(),
        compatibility_finding_codes=(),
        provenance={"module_id": node.module_id, "module_version": "1.0.0", "compatibility_row_id": registry.get(node.module_id).compatibility_matrix[0].id},
        safe_error_class=None,
    )


def serial_fixture():
    temporary, registry = workflow_registry(
        (
            module_payload("normalize-matrix", "count_matrix", "normalized_matrix"),
            module_payload("test-contrast", "normalized_matrix", "contrast_result"),
        )
    )
    counts_payload = inline_artifact("artifact-counts", "count_matrix").to_dict()
    counts_payload.pop("content_digest")
    counts_payload["content"] = {"rows": [{"sample_id": "s1"}]}
    state = state_with(ScientificArtifact.create(**counts_payload))
    request = PlanningRequest("request-contrast", "contrast_result", (hypothesis().id,), ("cell-state-association",))
    plan = plan_research(state, registry, build_capability_graph(registry), (request,))
    return temporary, registry, state, plan


def revision_fixture(action):
    source_module = "primary-normalizer"
    alternative_module = "alternative-normalizer"
    temporary, registry = workflow_registry(
        (
            module_payload(
                source_module,
                "count_matrix",
                "normalized_matrix",
                alternatives=(alternative_module,),
                revision_alternatives=({
                    "target_module_id": alternative_module,
                    "input_binding_map": {"records": "records"},
                    "output_binding_map": {"profile": "profile"},
                    "required_additional_artifact_types": [],
                    "parameter_mapping": {"rows": "rows"},
                    "scientific_contract_equivalence": "equivalent",
                },),
            ),
            module_payload(alternative_module, "count_matrix", "normalized_matrix"),
        )
    )
    state = state_with(inline_artifact("artifact-counts", "count_matrix"))
    row_id = registry.get(source_module).compatibility_matrix[0].id
    source = PlanNode(
        id="node-primary-normalizer",
        module_id=source_module,
        input_bindings={"records": "artifact-counts"},
        dependencies=(),
        branch_id="branch-normalization",
        target_hypothesis_ids=(hypothesis().id,),
        expected_evidence_types=("cell-state-association",),
        expected_output_artifact_types=("normalized_matrix",),
        planned_output_artifact_ids={"profile": "artifact-primary-normalized"},
        compatibility_row_candidates=(row_id,),
        status="pending",
        attempt=0,
    )
    observed_request_digest = digest_value({
        "module_id": source_module,
        "module_version": "1.0.0",
        "compatibility_row_id": row_id,
    })
    target_module = alternative_module if action == "switch-method" else source_module
    target_row_id = registry.get(target_module).compatibility_matrix[0].id
    planned_request_digest = (
        digest_value({"source": observed_request_digest, "adjustment": "registered-change"})
        if action == "rerun-adjusted-parameters"
        else observed_request_digest
    )
    target_id = "node-revision-normalizer"
    target_manifest_payload = manifest_to_dict(registry.get(target_module))
    contract = RevisionTargetContract.create(
        id=f"revision-contract-{action}",
        source_node_id=source.id,
        target_node_id=target_id,
        action=action,
        source_module_id=source_module,
        target_module_id=target_module,
        source_manifest_digest=module_manifest_digest(registry.get(source_module)),
        target_manifest_digest=module_manifest_digest(registry.get(target_module)),
        alternative_relation_digest=digest_value(
            revision_alternative_to_dict(registry.get(source_module).revision_alternatives[0])
            if action == "switch-method"
            else {"kind": "same-method", "source_module_id": source_module}
        ),
        input_contract_digest=digest_value({
            "target_ports": target_manifest_payload["input_artifacts"],
            "bindings": {"records": "artifact-counts"},
        }),
        output_contract_digest=digest_value({
            "source_types": list(source.expected_output_artifact_types),
            "target_ports": target_manifest_payload["output_artifacts"],
            "output_binding_map": {"profile": "profile"},
        }),
        source_request_digest=observed_request_digest,
        target_request_digest=planned_request_digest,
        rationale="Freeze the controlled replacement identity for revision state-machine tests.",
    )
    replacement = PlanNode(
        id=target_id,
        module_id=target_module,
        input_bindings={"records": "artifact-counts"},
        dependencies=(),
        branch_id=source.branch_id,
        target_hypothesis_ids=source.target_hypothesis_ids,
        expected_evidence_types=source.expected_evidence_types,
        expected_output_artifact_types=source.expected_output_artifact_types,
        planned_output_artifact_ids={"profile": "artifact-revision-normalized"},
        compatibility_row_candidates=(target_row_id,),
        status="pending",
        attempt=0,
        planned_request_digest=planned_request_digest,
        revision_of_node_id=source.id,
        parameter_overrides={"adjustment": "registered-change"} if action == "rerun-adjusted-parameters" else {},
        revision_contract=contract,
    )
    plan = ResearchDAG.create(
        id=f"plan-{action}",
        objective="Evaluate one registered normalization result and activate only its contracted revision when required.",
        nodes=(source, replacement),
        required_output_artifact_types=("normalized_matrix",),
        plan_type="parallel",
        revision=1,
        parent_plan_id=None,
        rationale=("Keep the replacement dormant until a bound scientific review selects its exact revision action.",),
    )
    return temporary, registry, state, plan


class ResearchControllerTests(unittest.TestCase):
    def test_multi_output_source_rejects_split_brain_revision_actions_and_targets(self):
        temporary, registry, state, plan = revision_fixture("rerun-same-method")
        self.addCleanup(temporary.cleanup)
        source, target = plan.nodes
        source = replace(
            source,
            expected_output_artifact_types=("normalized_matrix", "normalization_figure"),
            planned_output_artifact_ids={
                "profile": "artifact-primary-normalized",
                "figure": "artifact-primary-figure",
            },
        )
        target = replace(
            target,
            expected_output_artifact_types=source.expected_output_artifact_types,
            planned_output_artifact_ids={
                "profile": "artifact-revision-normalized",
                "figure": "artifact-revision-figure",
            },
        )
        state_view = SimpleNamespace(
            plans=(SimpleNamespace(id=plan.id, nodes=(source, target)),),
            active_plan_id=plan.id,
            artifact_reloads=(SimpleNamespace(
                artifact_id="artifact-primary-normalized",
                observed_execution_receipt_id="observed-source",
            ),),
            observed_executions=(SimpleNamespace(
                id="observed-source",
                parameters_digest=target.revision_contract.source_request_digest,
            ),),
            artifacts=state.artifacts,
            scientific_decisions=(SimpleNamespace(
                artifact_id="artifact-primary-figure",
                action="rerun-adjusted-parameters",
                revision_contract_id="revision-contract-conflicting",
                next_plan_node_ids=("node-conflicting-target",),
            ),),
        )
        decision = SimpleNamespace(
            action="rerun-same-method",
            next_plan_node_ids=(target.id,),
            artifact_id="artifact-primary-normalized",
            revision_contract_id=target.revision_contract.id,
        )
        with self.assertRaisesRegex(ValueError, "split outputs across conflicting revision decisions"):
            validate_revision_target_contract(state_view, decision)

    def test_default_planner_review_then_prepare_revision_rewrites_downstream_and_resumes(self):
        temporary, registry, state, plan = serial_fixture()
        self.addCleanup(temporary.cleanup)

        def executor(current_state, _plan, node, active_registry, **_kwargs):
            execution = completed_execution(current_state, node, active_registry)
            return replace(
                execution,
                provenance={
                    **execution.provenance,
                    "parameters_digest": (
                        node.planned_request_digest
                        or digest_value({"rows": [{"sample_id": "s1"}]})
                    ),
                },
            )

        controller = _StrictResearchController(
            registry,
            environment_provider=lambda _manifest: None,
            node_executor=executor,
            policy=ControllerPolicy(require_approved_admission=False),
        )
        waiting = controller.advance(state, plan)
        source = next(node for node in waiting.active_plan.nodes if node.status == "awaiting_review")
        source_artifact_id = next(iter(source.planned_output_artifact_ids.values()))
        artifact_review = ArtifactReview(
            id="review-default-planner-revision",
            artifact_id=source_artifact_id,
            artifact_kind="data",
            rationale_zh="默认计划产物经复核后需要以相同方法按冻结请求重新执行。",
            rationale_en="The default-plan output requires a same-method rerun with a frozen request after review.",
            methods_zh="复核执行身份、输入绑定、输出完整性和后续依赖。",
            methods_en="Review execution identity, input bindings, output integrity, and downstream dependencies.",
            results_zh="轻量结果足以触发计划修订，但不用于推断生物效应。",
            results_en="The lightweight result is sufficient to trigger plan revision but not biological inference.",
            conclusion_zh="创建登记的替代节点并重接尚未执行的下游节点。",
            conclusion_en="Create a registered replacement and rewire downstream nodes that have not executed.",
            panels=(),
            technical_status="major",
            statistical_status="major",
            biological_status="major",
            robustness_status="major",
            limitations_zh=("该夹具仅验证公开修订路径。",),
            limitations_en=("This fixture validates only the public revision path.",),
            recommended_action="rerun-same-method",
            source_urls=("https://www.w3.org/TR/prov-o/",),
        )
        reviewed_state = apply_event(
            waiting.state,
            "artifact_review_recorded",
            {"review": artifact_review.to_dict()},
            rationale="Review the default planner output before revision preparation.",
        )
        revised = prepare_plan_revision(
            reviewed_state,
            registry,
            source_artifact_id=source_artifact_id,
            action="rerun-same-method",
            target_module_id=source.module_id,
            parameter_overrides={},
            rationale="Repeat the reviewed method with the exact observed request and rewire untouched downstream work.",
        )
        self.assertEqual(revised.parent_plan_id, plan.id)
        replacement = next(node for node in revised.nodes if node.revision_of_node_id == source.id)
        rebuilt_downstream = next(node for node in revised.nodes if node.module_id == "test-contrast")
        self.assertIn(replacement.id, rebuilt_downstream.dependencies)
        self.assertNotIn(source.id, rebuilt_downstream.dependencies)
        state = apply_event(
            reviewed_state,
            "plan_revised",
            {"plan": revised.to_dict(), "activate": True},
            rationale="Activate the registry-validated child plan.",
        )
        scientific_decision = ScientificDecision(
            id="decision-default-planner-revision",
            review_id=artifact_review.id,
            artifact_id=source_artifact_id,
            hypothesis_ids=(hypothesis().id,),
            action="rerun-same-method",
            rationale_zh="评审要求按冻结请求重新运行相同方法。",
            rationale_en="The review requires the same method to rerun with the frozen request.",
            active_evidence=False,
            next_plan_node_ids=(replacement.id,),
            revision_contract_id=replacement.revision_contract.id,
        )
        validate_revision_target_contract(state, scientific_decision, registry=registry, require_pending=True)
        state = apply_event(
            state,
            "scientific_decision_recorded",
            {"decision": scientific_decision.to_dict()},
            rationale="Bind the reviewed source to its prepared node-level revision contract.",
        )
        resumed = controller.resume(state.to_dict())
        self.assertEqual(resumed.stop_reason, "awaiting_artifact_review")
        self.assertEqual(
            next(node for node in resumed.active_plan.nodes if node.id == replacement.id).status,
            "awaiting_review",
        )

    def test_revision_target_contract_rejects_wrong_method_parameter_and_scope_semantics(self):
        def contract_state(plan, state, source):
            return SimpleNamespace(
                plans=(plan,),
                active_plan_id=plan.id,
                artifact_reloads=(SimpleNamespace(
                    artifact_id=next(iter(source.planned_output_artifact_ids.values())),
                    observed_execution_receipt_id="observed-source",
                ),),
                observed_executions=(SimpleNamespace(
                    id="observed-source",
                    parameters_digest=digest_value({
                        "module_id": source.module_id,
                        "module_version": "1.0.0",
                        "compatibility_row_id": source.compatibility_row_candidates[0],
                    }),
                ),),
                artifacts=state.artifacts,
                scientific_decisions=(),
            )

        def rebuilt(plan, source, target):
            return ResearchDAG.create(
                id=plan.id,
                objective=plan.objective,
                nodes=(source, target),
                required_output_artifact_types=plan.required_output_artifact_types,
                plan_type=plan.plan_type,
                revision=plan.revision,
                parent_plan_id=plan.parent_plan_id,
                rationale=plan.rationale,
            )

        cases = []
        for action in ("rerun-same-method", "rerun-adjusted-parameters", "switch-method"):
            temporary, registry, state, plan = revision_fixture(action)
            self.addCleanup(temporary.cleanup)
            source, target = plan.nodes
            observed_digest = contract_state(plan, state, source).observed_executions[0].parameters_digest
            if action == "rerun-same-method":
                with self.assertRaisesRegex(ValueError, "frozen revision contract"):
                    replace(target, module_id="alternative-normalizer")
            elif action == "rerun-adjusted-parameters":
                with self.assertRaisesRegex(ValueError, "frozen revision contract"):
                    replace(target, planned_request_digest=observed_digest)
            else:
                with self.assertRaisesRegex(ValueError, "frozen revision contract"):
                    replace(
                        target,
                        module_id=source.module_id,
                        compatibility_row_candidates=source.compatibility_row_candidates,
                    )

        temporary, registry, state, plan = revision_fixture("rerun-same-method")
        self.addCleanup(temporary.cleanup)
        source, target = plan.nodes
        invalid = replace(target, branch_id="branch-unrelated")
        invalid_plan = rebuilt(plan, source, invalid)
        cases.append((
            "rerun-same-method",
            registry,
            contract_state(invalid_plan, state, source),
            invalid.id,
            "branch, inputs, outputs",
        ))

        with self.assertRaisesRegex(ValueError, "frozen revision contract"):
            replace(target, revision_of_node_id=None)

        temporary, registry, state, plan = revision_fixture("switch-method")
        self.addCleanup(temporary.cleanup)
        source, target = plan.nodes
        base_registry = registry
        undeclared_registry = SimpleNamespace(
            get=lambda module_id, base=base_registry: (
                replace(base.get(module_id), alternatives=(), revision_alternatives=())
                if module_id == source.module_id
                else base.get(module_id)
            )
        )
        cases.append((
            "switch-method",
            undeclared_registry,
            contract_state(plan, state, source),
            target.id,
            "revision-compatible alternative",
        ))

        for action, registry, state, target_id, message in cases:
            with self.subTest(action=action, message=message):
                decision = SimpleNamespace(
                    action=action,
                    next_plan_node_ids=(target_id,),
                    artifact_id=state.artifact_reloads[0].artifact_id,
                    revision_contract_id=next(
                        node.revision_contract.id for node in state.plans[0].nodes
                        if node.id == target_id
                    ),
                )
                with self.assertRaisesRegex(ValueError, message):
                    validate_revision_target_contract(
                        state,
                        decision,
                        registry=registry,
                        require_pending=True,
                    )

    def test_state_only_delivery_authorization_cannot_replace_the_immutable_store(self):
        payload = module_payload("publication-delivery", "analysis_result", "publication_package")
        payload["module_type"] = "delivery"
        payload["domains"] = ["publication"]
        temporary, registry = workflow_registry((payload,))
        self.addCleanup(temporary.cleanup)
        state = state_with(inline_artifact("artifact-reviewed-result", "analysis_result"))
        node = PlanNode(
            id="node-publication-delivery",
            module_id="publication-delivery",
            input_bindings={"input_data": "artifact-reviewed-result"},
            dependencies=(), branch_id="branch-publication",
            target_hypothesis_ids=(hypothesis().id,),
            expected_evidence_types=("publication-delivery",),
            expected_output_artifact_types=("publication_package",),
            planned_output_artifact_ids={"profile": "artifact-publication-package"},
            compatibility_row_candidates=(registry.get("publication-delivery").compatibility_matrix[0].id,),
            status="pending", attempt=0,
        )
        plan = ResearchDAG.create(
            id="plan-publication-delivery", objective="Release a publication package from retained evidence.",
            nodes=(node,), required_output_artifact_types=("publication_package",), plan_type="single",
            revision=1, parent_plan_id=None,
            rationale=("Authorize the delivery node from its exact retained input slice.",),
        )
        state = apply_event(state, "plan_created", {"plan": plan.to_dict(), "activate": True}, rationale="Register delivery plan.")
        admission = AnalysisAdmission(
            id="admission-publication-delivery", plan_node_id=node.id, hypothesis_ids=node.target_hypothesis_ids,
            rationale_zh="基于已保留证据生成可审查的发表交付包。",
            rationale_en="Generate a reviewable publication package from retained evidence.",
            method="Execute the registered publication renderer against exact retained artifact identities.",
            official_sources=("https://example.org/publication",), alternatives_considered=("Retain the evidence without rendering if authorization fails.",),
            assumptions=("The retained input identity is current.",), parameter_justifications={"profile": "Use the registered profile."},
            acceptance_criteria=("Reload the complete publication package.",), falsification_criteria=("A stale input identity blocks delivery.",),
            expected_artifact_types=node.expected_output_artifact_types, approved=True,
        )
        state = apply_event(state, "analysis_admission_recorded", {"admission": admission.to_dict()}, rationale="Approve delivery.")
        input_review = ArtifactReview(
            id="review-artifact-reviewed-result", artifact_id="artifact-reviewed-result", artifact_kind="data",
            rationale_zh="对登记输入进行技术和科学复核。", rationale_en="Review the registered input technically and scientifically.",
            methods_zh="核对输入身份、范围和来源。", methods_en="Verify input identity, scope, and provenance.",
            results_zh="输入完整且适合进入发表交付。", results_en="The input is complete and eligible for publication delivery.",
            conclusion_zh="保留该输入作为当前证据。", conclusion_en="Retain this input as current evidence.", panels=(),
            technical_status="passed", statistical_status="passed", biological_status="passed", robustness_status="passed",
            limitations_zh=("该测试验证交付授权状态机。",), limitations_en=("This test validates the delivery authorization state machine.",),
            recommended_action="retain-as-evidence", source_urls=("https://example.org/publication",),
        )
        state = apply_event(state, "artifact_review_recorded", {"review": input_review.to_dict()}, rationale="Review input.")
        retained = ScientificDecision(
            id="decision-artifact-reviewed-result", review_id=input_review.id, artifact_id="artifact-reviewed-result",
            hypothesis_ids=(hypothesis().id,), action="retain-as-evidence",
            rationale_zh="输入通过评审并保留用于交付。", rationale_en="The reviewed input is retained for delivery.",
            active_evidence=True, next_plan_node_ids=(node.id,),
        )
        state = apply_event(state, "scientific_decision_recorded", {"decision": retained.to_dict()}, rationale="Retain input.")

        controller = _StrictResearchController(
            registry, environment_provider=lambda _manifest: None,
            node_executor=lambda current, _plan, current_node, active_registry, **_kwargs: completed_execution(current, current_node, active_registry),
        )
        blocked = controller.advance(state, plan)
        self.assertEqual(blocked.stop_reason, "awaiting_evidence_map")
        scope = validate_delivery_prerequisites(blocked.state, node.id)
        publication = EvidenceMapPublication(
            id="evidence-map-authorization", version=EvidenceMapVersion(
                version="1.0.0", revision=1, parent_map_digest=None, change_type="initial",
                change_summary_zh="发布精确上游证据切片以授权发表交付。",
                change_summary_en="Publish the exact upstream evidence slice to authorize delivery.",
                map_kind="delivery-authorization",
            ),
            map_digest="1" * 64, edge_table_digest="2" * 64,
            source_state_digest=blocked.state.state_digest, dependency_bundle_digest="3" * 64,
            map_kind="delivery-authorization", delivery_slice_digest=delivery_slice_digest(blocked.state),
            active_artifact_ids=("artifact-reviewed-result",), covered_plan_id=scope.plan_id,
            covered_node_ids=scope.covered_node_ids, covered_artifact_ids=scope.covered_artifact_ids,
            authorized_delivery_node_ids=(node.id,), delivery_scope_digest=scope.digest,
        )
        authorized = apply_event(
            blocked.state, "evidence_map_published", {"publication": publication.to_dict()},
            rationale="Authorize this exact delivery node from its retained upstream slice.",
        )
        released = controller.resume(authorized.to_dict())
        self.assertEqual(released.stop_reason, "awaiting_evidence_map")
        self.assertFalse(released.executions)

    def test_registered_delivery_modules_each_have_a_reachable_authorized_execution(self):
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        delivery_module_ids = (
            "patent-flowchart-svg",
            "presentation-delivery-plan",
            "trajectory-spatial-figure-package",
        )
        for module_id in delivery_module_ids:
            with self.subTest(module_id=module_id):
                manifest = registry.get(module_id)
                self.assertEqual(manifest.module_type, "delivery")
                input_port = manifest.input_artifacts[0]
                output_port = manifest.output_artifacts[0]
                input_id = f"artifact-input-{module_id}"
                node_id = f"node-{module_id}"
                state = state_with(inline_artifact(input_id, input_port.artifact_type))
                node = PlanNode(
                    id=node_id,
                    module_id=module_id,
                    input_bindings={input_port.name: input_id},
                    dependencies=(),
                    branch_id=f"branch-{module_id}",
                    target_hypothesis_ids=(hypothesis().id,),
                    expected_evidence_types=("publication-delivery",),
                    expected_output_artifact_types=(output_port.artifact_type,),
                    planned_output_artifact_ids={output_port.name: f"artifact-output-{module_id}"},
                    compatibility_row_candidates=(manifest.compatibility_matrix[0].id,),
                    status="pending",
                    attempt=0,
                )
                plan = ResearchDAG.create(
                    id=f"plan-{module_id}",
                    objective=f"Authorize the registered {module_id} delivery.",
                    nodes=(node,),
                    required_output_artifact_types=(output_port.artifact_type,),
                    plan_type="single",
                    revision=1,
                    parent_plan_id=None,
                    rationale=("Bind authorization to the exact retained input and delivery node.",),
                )
                state = apply_event(
                    state,
                    "plan_created",
                    {"plan": plan.to_dict(), "activate": True},
                    rationale="Register the delivery plan.",
                )
                admission = AnalysisAdmission(
                    id=f"admission-{module_id}",
                    plan_node_id=node_id,
                    hypothesis_ids=node.target_hypothesis_ids,
                    rationale_zh="依据当前保留证据生成指定的研究交付物。",
                    rationale_en="Generate the specified research deliverable from current retained evidence.",
                    method=f"Execute registered delivery module {module_id} with its exact input binding.",
                    official_sources=("https://github.com/JunyanKang/biomed-workbench",),
                    alternatives_considered=("Keep the retained evidence without delivery if authorization fails.",),
                    assumptions=("The registered input identity is current.",),
                    parameter_justifications={"contract": "Use the registered compatibility row."},
                    acceptance_criteria=("Reload every declared delivery artifact.",),
                    falsification_criteria=("Any input-identity drift blocks delivery.",),
                    expected_artifact_types=node.expected_output_artifact_types,
                    approved=True,
                )
                state = apply_event(
                    state,
                    "analysis_admission_recorded",
                    {"admission": admission.to_dict()},
                    rationale="Approve the exact delivery method.",
                )
                review = ArtifactReview(
                    id=f"review-{module_id}", artifact_id=input_id, artifact_kind="data",
                    rationale_zh="复核交付输入的身份、范围和来源。",
                    rationale_en="Review the delivery input identity, scope, and provenance.",
                    methods_zh="逐项核对登记内容、科学范围、来源记录和身份校验值。",
                    methods_en="Verify the registered content, scientific scope, provenance record, and identity digest.",
                    results_zh="登记输入的身份、科学范围、来源记录和内容校验均保持一致。",
                    results_en="The registered input identity, scientific scope, provenance, and content digest are consistent.",
                    conclusion_zh="该输入通过技术与科学复核，可保留为当前交付节点的有效证据。",
                    conclusion_en="The input passes technical and scientific review and may be retained as current evidence for delivery.", panels=(),
                    technical_status="passed", statistical_status="passed", biological_status="passed", robustness_status="passed",
                    limitations_zh=("该受控样例验证授权闭环，不代表外部渲染后端已经执行。",),
                    limitations_en=("This controlled fixture validates authorization closure, not execution of an external renderer.",),
                    recommended_action="retain-as-evidence",
                    source_urls=("https://github.com/JunyanKang/biomed-workbench",),
                )
                state = apply_event(
                    state, "artifact_review_recorded", {"review": review.to_dict()}, rationale="Review delivery input."
                )
                decision = ScientificDecision(
                    id=f"decision-{module_id}", review_id=review.id, artifact_id=input_id,
                    hypothesis_ids=(hypothesis().id,), action="retain-as-evidence",
                    rationale_zh="该输入的身份、范围和来源通过复核，因此保留为交付节点的有效证据。",
                    rationale_en="The input identity, scope, and provenance passed review, so it is retained as active evidence for delivery.",
                    active_evidence=True, next_plan_node_ids=(node_id,),
                )
                state = apply_event(
                    state, "scientific_decision_recorded", {"decision": decision.to_dict()}, rationale="Retain delivery input."
                )
                controller = _StrictResearchController(
                    registry,
                    environment_provider=lambda _manifest: None,
                    node_executor=lambda current, _plan, current_node, active_registry, **_kwargs: completed_execution(
                        current, current_node, active_registry
                    ),
                )
                blocked = controller.advance(state, plan)
                self.assertEqual(blocked.stop_reason, "awaiting_evidence_map")
                bundle = ScientificDependencyBundle.create(
                    blocked.state,
                    admissions=blocked.state.analysis_admissions,
                    reviews=blocked.state.artifact_reviews,
                    decisions=blocked.state.scientific_decisions,
                    map_kind="delivery-authorization",
                )
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    workspace = root / "workspace"
                    files = {
                        "data/input.json": '{"sample":"controlled"}\n',
                        "scripts/render.py": "print('controlled renderer')\n",
                        "results/qualified.json": '{"eligible":true}\n',
                        "captions/input.md": "Reviewed delivery input and provenance.\n",
                    }
                    for relative, content in files.items():
                        path = workspace / relative
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text(content, encoding="utf-8")
                    spec = EvidenceUnitSpec(
                        id=f"unit-{module_id}", group_id=f"group-{module_id}",
                        artifact_id=input_id, panel_id=None,
                        analysis_admission_ids=(admission.id,), predecessor_unit_ids=(),
                        prerequisite_conclusion_zh="该输入已完成身份、范围和来源复核，可用于精确交付授权。",
                        prerequisite_conclusion_en="The input identity, scope, and provenance were reviewed for exact delivery authorization.",
                        files=(
                            EvidenceFile.from_workspace(id=f"file-{module_id}-input", role="registered-data", path="data/input.json", media_type="application/json", workspace_root=workspace),
                            EvidenceFile.from_workspace(id=f"file-{module_id}-script", role="analysis-script", path="scripts/render.py", media_type="text/x-python", workspace_root=workspace),
                            EvidenceFile.from_workspace(id=f"file-{module_id}-result", role="final-data", path="results/qualified.json", media_type="application/json", workspace_root=workspace),
                            EvidenceFile.from_workspace(id=f"file-{module_id}-caption", role="caption", path="captions/input.md", media_type="text/markdown", workspace_root=workspace),
                        ),
                        narrative_sources=(NarrativeSource(
                            id=f"source-{module_id}", role="original-study",
                            title="The FAIR Guiding Principles for scientific data management and stewardship",
                            doi="10.1038/sdata.2016.18",
                            url="https://doi.org/10.1038/sdata.2016.18",
                        ),),
                    )
                    mapped = build_scientific_evidence_map(
                        blocked.state, bundle, (spec,), workspace_root=workspace,
                        version=EvidenceMapVersion(
                            version="1.0.0", revision=1, parent_map_digest=None,
                            change_type="initial",
                            change_summary_zh="以真实文件事务发布精确证据切片并授权交付。",
                            change_summary_en="Publish the exact evidence slice through a real file transaction to authorize delivery.",
                            map_kind="delivery-authorization",
                        ),
                        authorized_delivery_node_ids=(node_id,),
                    )
                    publication = EvidenceMapPublication.from_map(mapped)
                    authorized = apply_event(
                        blocked.state, "evidence_map_published", {"publication": publication.to_dict()},
                        rationale="Authorize only this delivery node through the published retained slice.",
                    )
                    state_path = root / "project-state.json"
                    state_path.write_text(
                        json.dumps(blocked.state.to_dict(), indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    publish_root = root / "published"
                    publish_evidence_map_transaction(
                        mapped, publication, authorized,
                        state_path=state_path, output_root=publish_root, workspace_root=workspace,
                    )
                    verify_evidence_map_version_index(publish_root)
                    reloaded = ProjectState.from_dict(json.loads(state_path.read_text(encoding="utf-8")))
                    self.assertTrue(validated_delivery_publication_is_current(reloaded, node_id))
                    self.assertFalse(validated_delivery_publication_is_current(reloaded, f"other-{node_id}"))
                    authorized_controller = _StrictResearchController(
                        registry,
                        environment_provider=lambda _manifest: None,
                        node_executor=lambda current, _plan, current_node, active_registry, **_kwargs: completed_execution(
                            current, current_node, active_registry
                        ),
                        evidence_map_root=publish_root,
                    )
                    released = authorized_controller.resume(reloaded.to_dict())
                    self.assertEqual(released.stop_reason, "awaiting_artifact_review")
                    self.assertEqual(tuple(item.module_id for item in released.executions), (module_id,))

                    index_path = publish_root / "evidence-map-version-index.json"
                    original_index = index_path.read_text(encoding="utf-8")
                    tampered = json.loads(original_index)
                    tampered["entries"][0]["map_digest"] = "f" * 64
                    index_path.write_text(json.dumps(tampered, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                    with self.assertRaises(ValueError):
                        verify_evidence_map_version_index(publish_root)
                    blocked_tamper = authorized_controller.resume(reloaded.to_dict())
                    self.assertEqual(blocked_tamper.stop_reason, "awaiting_evidence_map")
                    self.assertFalse(blocked_tamper.executions)
                    index_path.write_text(original_index, encoding="utf-8")
                    (publish_root / "versions/v1.0.0/scientific-evidence-map.json").unlink()
                    with self.assertRaises(ValueError):
                        verify_evidence_map_version_index(publish_root)
                    blocked_missing = authorized_controller.resume(reloaded.to_dict())
                    self.assertEqual(blocked_missing.stop_reason, "awaiting_evidence_map")
                    self.assertFalse(blocked_missing.executions)

    def test_upstream_required_port_rejects_an_unreviewed_project_input_at_runtime(self):
        payload = module_payload("reviewed-upstream-consumer", "normalized_matrix", "contrast_result")
        payload["input_artifacts"][0]["source_policy"] = "upstream_required"
        payload["orchestration"]["requires_reviewed_upstream_types"] = ["normalized_matrix"]
        temporary, registry = workflow_registry((payload,))
        self.addCleanup(temporary.cleanup)
        state = state_with(inline_artifact("artifact-project-matrix", "normalized_matrix"))
        node = PlanNode(
            id="node-reviewed-upstream-consumer",
            module_id="reviewed-upstream-consumer",
            input_bindings={"input_data": "artifact-project-matrix"},
            dependencies=(),
            branch_id="branch-upstream-contract",
            target_hypothesis_ids=(hypothesis().id,),
            expected_evidence_types=("contrast",),
            expected_output_artifact_types=("contrast_result",),
            planned_output_artifact_ids={"result": "artifact-reviewed-contrast"},
            compatibility_row_candidates=(registry.get("reviewed-upstream-consumer").compatibility_matrix[0].id,),
            status="ready",
            attempt=0,
        )
        plan = ResearchDAG.create(
            id="plan-reviewed-upstream-consumer",
            objective="Reject a project input that attempts to bypass the reviewed upstream contract.",
            nodes=(node,),
            required_output_artifact_types=("contrast_result",),
            plan_type="single",
            revision=1,
            parent_plan_id=None,
            rationale=("The runtime source policy is independently enforced after planning.",),
        )
        result = execute_node(
            state,
            plan,
            node,
            registry,
            environment_provider=lambda _manifest: None,
        )
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.safe_error_class, "UpstreamReviewRequiredError")

    def test_strict_default_requires_admission_review_and_retain_decision_before_release(self):
        temporary, registry, state, plan = serial_fixture()
        self.addCleanup(temporary.cleanup)
        executions = []

        def executor(current_state, _plan, node, active_registry, **_kwargs):
            executions.append(node.id)
            return completed_execution(current_state, node, active_registry)

        controller = _StrictResearchController(
            registry,
            environment_provider=lambda _manifest: None,
            node_executor=executor,
        )
        waiting = controller.advance(state, plan)
        self.assertEqual(waiting.stop_reason, "awaiting_analysis_admission")
        self.assertEqual(executions, [])
        state = waiting.state
        active = waiting.active_plan
        for node in active.nodes:
            admission = AnalysisAdmission(
                id=f"admission-{node.id}",
                plan_node_id=node.id,
                hypothesis_ids=node.target_hypothesis_ids or (hypothesis().id,),
                rationale_zh="该分析用于检验预先登记的科学假设并产生指定类型的结果。",
                rationale_en="This analysis tests the preregistered hypothesis and produces the declared result type.",
                method=f"Execute the exact registered module {node.module_id} under its selected compatibility contract.",
                official_sources=("https://example.org/official-method",),
                alternatives_considered=("Use the declared alternative only if this exact compatibility row is blocked.",),
                assumptions=("The registered input artifact identities and experimental units are correct.",),
                parameter_justifications={"default": "The fixture uses the manifest-declared bounded parameters for deterministic validation."},
                acceptance_criteria=("All declared outputs are reloaded and pass their registered artifact contracts.",),
                falsification_criteria=("A missing output or blocking quality finding invalidates the result for release.",),
                expected_artifact_types=node.expected_output_artifact_types,
                approved=True,
            )
            state = apply_event(
                state,
                "analysis_admission_recorded",
                {"admission": admission.to_dict()},
                rationale="Approve a complete analysis admission before execution.",
                affected_hypothesis_ids=admission.hypothesis_ids,
                replacement_action_ids=(node.id,),
            )

        first_cycle = controller.advance(state, active)
        self.assertEqual(first_cycle.stop_reason, "awaiting_artifact_review")
        self.assertEqual(len(executions), 1)

        def review_and_retain(current_state, artifact_id):
            review = ArtifactReview(
                id=f"review-{artifact_id}",
                artifact_id=artifact_id,
                artifact_kind="data",
                rationale_zh="该产物依据预先登记的验收标准进行独立技术与科学评审。",
                rationale_en="The artifact is independently reviewed against the preregistered technical and scientific criteria.",
                methods_zh="重新读取登记内容并核对来源、实验单位、输出类型和质量状态。",
                methods_en="Reload the registered content and verify provenance, unit, output type, and quality status.",
                results_zh="产物结构完整，来源可追溯，未发现阻断解释或后续分析的问题。",
                results_en="The artifact is complete and traceable, with no issue blocking interpretation or downstream analysis.",
                conclusion_zh="该产物满足保留为当前项目有效科学证据的标准。",
                conclusion_en="The artifact satisfies the criteria for retention as active project evidence.",
                panels=(),
                technical_status="passed",
                statistical_status="passed",
                biological_status="passed",
                robustness_status="warning",
                limitations_zh=("该轻量夹具仅验证状态转换，不代表真实生物数据的效应量。",),
                limitations_en=("This lightweight fixture validates state transitions, not a biological effect size.",),
                recommended_action="retain-with-caveat",
                source_urls=("https://example.org/official-method",),
            )
            current_state = apply_event(
                current_state,
                "artifact_review_recorded",
                {"review": review.to_dict()},
                rationale="Record the mandatory bilingual artifact review.",
                affected_artifact_ids=(artifact_id,),
            )
            decision = ScientificDecision(
                id=f"decision-{artifact_id}",
                review_id=review.id,
                artifact_id=artifact_id,
                hypothesis_ids=(hypothesis().id,),
                action="retain-with-caveat",
                rationale_zh="评审通过且局限已明确，因此保留该产物并释放其依赖分析。",
                rationale_en="The review passed with explicit limitations, so the artifact is retained and dependencies may proceed.",
                active_evidence=True,
                next_plan_node_ids=(),
            )
            return apply_event(
                current_state,
                "scientific_decision_recorded",
                {"decision": decision.to_dict()},
                rationale="Retain reviewed output as active evidence before releasing dependencies.",
                affected_artifact_ids=(artifact_id,),
                affected_hypothesis_ids=decision.hypothesis_ids,
            )

        first_output = first_cycle.executions[0].output_artifact_ids[0]
        state = review_and_retain(first_cycle.state, first_output)
        second_cycle = controller.resume(state.to_dict())
        self.assertEqual(second_cycle.stop_reason, "awaiting_artifact_review")
        self.assertEqual(len(executions), 2)
        second_output = second_cycle.executions[0].output_artifact_ids[0]
        state = review_and_retain(second_cycle.state, second_output)
        completed = controller.resume(state.to_dict())
        self.assertEqual(completed.stop_reason, "plan_completed")
        self.assertEqual({node.status for node in completed.active_plan.nodes}, {"completed"})

    def test_execution_handoff_stops_before_artifact_evidence_and_downstream_release(self):
        temporary, registry, state, plan = serial_fixture()
        self.addCleanup(temporary.cleanup)
        first = plan.nodes[0]

        def executor(_state, _plan, node, active_registry, **_kwargs):
            manifest = active_registry.get(node.module_id)
            gate_ids = sorted(gate.id for gate in manifest.quality_gates)
            handoff = ExecutionHandoff.create(
                plan_node_id=node.id,
                module_id=manifest.id,
                module_version=manifest.version,
                request_digest="1" * 64,
                compatibility_row_id=manifest.compatibility_matrix[0].id,
                observed_output_contract_digest="2" * 64,
                planned_output_artifact_ids=node.planned_output_artifact_ids,
                protocol={
                    "result_kind": "execution_handoff",
                    "execution_state": "prepared-not-run",
                    "observed_output_protocol_version": "2.1.0",
                    "required_postflight_gate_ids": gate_ids,
                    "required_postflight_gate_set_digest": digest_value(gate_ids),
                },
            )
            return NodeExecution(
                node_id=node.id,
                module_id=node.module_id,
                module_version=manifest.version,
                status="awaiting_observed_execution",
                compatibility_row_id=manifest.compatibility_matrix[0].id,
                input_artifact_ids=tuple(node.input_bindings.values()),
                output_artifact_ids=(),
                artifacts=(),
                quality_findings=(),
                compatibility_finding_codes=(),
                provenance={"compatibility_row_id": manifest.compatibility_matrix[0].id},
                safe_error_class=None,
                execution_handoff=handoff,
            )

        result = ResearchController(
            registry,
            environment_provider=lambda _manifest: None,
            node_executor=executor,
        ).advance(state, plan)

        self.assertEqual(result.stop_reason, "awaiting_observed_execution")
        self.assertEqual(result.active_plan.nodes[0].status, "awaiting_observed_execution")
        self.assertEqual(result.active_plan.nodes[1].status, "pending")
        self.assertNotIn(next(iter(first.planned_output_artifact_ids.values())), {item.id for item in result.state.artifacts})
        self.assertEqual(result.state.evidence, ())
        self.assertEqual(result.assessments, ())

    def test_review_decision_families_have_distinct_controller_transitions(self):
        cases = {
            "retain-with-caveat": ("completed", "awaiting_artifact_review", True),
            "exclude-invalid": ("skipped", "scientific_evidence_excluded", False),
            "stop-branch": ("skipped", "scientific_branch_stopped", False),
            "rerun-same-method": ("superseded", "awaiting_artifact_review", True),
            "rerun-adjusted-parameters": ("superseded", "awaiting_artifact_review", True),
            "switch-method": ("superseded", "awaiting_artifact_review", True),
            "acquire-more-data": ("blocked", "awaiting_additional_data", False),
            "revise-hypothesis": ("blocked", "awaiting_plan_revision", False),
            "revise-project-scope": ("blocked", "awaiting_plan_revision", False),
        }
        for action, (expected_status, expected_stop, executes_revision) in cases.items():
            with self.subTest(action=action):
                if action in {"rerun-same-method", "rerun-adjusted-parameters", "switch-method"}:
                    temporary, registry, state, plan = revision_fixture(action)
                else:
                    temporary, registry, state, plan = serial_fixture()
                self.addCleanup(temporary.cleanup)
                executions = []

                def executor(current_state, _plan, node, active_registry, **_kwargs):
                    executions.append(node.id)
                    execution = completed_execution(current_state, node, active_registry)
                    if node.planned_request_digest is not None:
                        execution = replace(
                            execution,
                            provenance={
                                **execution.provenance,
                                "parameters_digest": node.planned_request_digest,
                            },
                        )
                    return execution

                controller = _StrictResearchController(
                    registry,
                    environment_provider=lambda _manifest: None,
                    node_executor=executor,
                    policy=ControllerPolicy(require_approved_admission=False),
                )
                waiting = controller.advance(state, plan)
                self.assertEqual(waiting.stop_reason, "awaiting_artifact_review")
                first_node, revision_node = waiting.active_plan.nodes
                artifact_id = waiting.executions[0].output_artifact_ids[0]
                retained = action == "retain-with-caveat"
                artifact_review = ArtifactReview(
                    id=f"review-{artifact_id}",
                    artifact_id=artifact_id,
                    artifact_kind="data",
                    rationale_zh="该产物依据预先登记的科学标准进行独立评审，并据此选择明确的后续动作。",
                    rationale_en="The artifact is independently reviewed against preregistered scientific criteria to select an explicit next action.",
                    methods_zh="重新读取产物，核对技术完整性、统计适用性、生物学边界与稳健性。",
                    methods_en="The artifact was reloaded and checked for technical integrity, statistical fitness, biological scope, and robustness.",
                    results_zh="轻量夹具记录了足以验证状态转换的评审结果，不代表真实生物效应。",
                    results_en="The lightweight fixture records a review result sufficient for state-transition testing, not a biological effect.",
                    conclusion_zh="该评审结论必须通过指定动作改变后续计划，且旧产物身份保持不可变。",
                    conclusion_en="The review must change the downstream plan through its declared action while preserving the old artifact identity.",
                    panels=(),
                    technical_status="warning" if retained else "major",
                    statistical_status="warning" if retained else "major",
                    biological_status="warning" if retained else "major",
                    robustness_status="warning" if retained else "major",
                    limitations_zh=("该夹具仅验证控制器动作语义和恢复一致性。",),
                    limitations_en=("This fixture validates only controller action semantics and resume consistency.",),
                    recommended_action=action,
                    source_urls=("https://www.w3.org/TR/prov-o/",),
                )
                state = apply_event(
                    waiting.state,
                    "artifact_review_recorded",
                    {"review": artifact_review.to_dict()},
                    rationale="Record a review before dispatching its action family.",
                )
                next_ids = (revision_node.id,) if action in {
                    "rerun-same-method", "rerun-adjusted-parameters", "switch-method"
                } else ()
                next_hypothesis_ids = ()
                if action == "revise-hypothesis":
                    original = next(item for item in state.hypotheses if item.id == hypothesis().id)
                    revised = revise_hypothesis(
                        original,
                        new_id=f"{original.id}-review-revision",
                        statement="A revised, explicitly registered hypothesis follows the reviewed conflicting result.",
                    )
                    state = apply_event(
                        state,
                        "hypothesis_revised",
                        {"hypothesis": revised.to_dict()},
                        rationale="Register a distinct child hypothesis before binding the revision decision.",
                    )
                    next_hypothesis_ids = (revised.id,)
                scientific_decision = ScientificDecision(
                    id=f"decision-{artifact_id}",
                    review_id=artifact_review.id,
                    artifact_id=artifact_id,
                    hypothesis_ids=(hypothesis().id,),
                    action=action,
                    rationale_zh="该动作依据评审结果执行，并保留原始产物、评审和决策的不可变历史。",
                    rationale_en="The action follows the review while preserving immutable history for the original artifact, review, and decision.",
                    active_evidence=retained,
                    next_plan_node_ids=next_ids,
                    next_hypothesis_ids=next_hypothesis_ids,
                    revision_contract_id=(
                        revision_node.revision_contract.id
                        if action in {"rerun-same-method", "rerun-adjusted-parameters", "switch-method"}
                        else None
                    ),
                )
                state = apply_event(
                    state,
                    "scientific_decision_recorded",
                    {"decision": scientific_decision.to_dict()},
                    rationale="Dispatch the explicit scientific decision family.",
                )
                result = controller.resume(state.to_dict())
                by_id = {node.id: node for node in result.active_plan.nodes}
                self.assertEqual(by_id[first_node.id].status, expected_status)
                self.assertEqual(result.stop_reason, expected_stop)
                self.assertEqual(revision_node.id in executions, executes_revision)

    def test_retained_revision_target_resolves_superseded_source_plan(self):
        temporary, registry, state, plan = revision_fixture("rerun-same-method")
        self.addCleanup(temporary.cleanup)

        def executor(current_state, _plan, node, active_registry, **_kwargs):
            execution = completed_execution(current_state, node, active_registry)
            if node.planned_request_digest is not None:
                execution = replace(
                    execution,
                    provenance={
                        **execution.provenance,
                        "parameters_digest": node.planned_request_digest,
                    },
                )
            return execution

        controller = _StrictResearchController(
            registry,
            environment_provider=lambda _manifest: None,
            node_executor=executor,
            policy=ControllerPolicy(require_approved_admission=False),
        )
        first = controller.advance(state, plan)
        source, replacement = first.active_plan.nodes
        source_artifact_id = next(iter(source.planned_output_artifact_ids.values()))

        def reviewed(current, artifact_id, review_id, action, *, active_evidence):
            artifact_review = ArtifactReview(
                id=review_id,
                artifact_id=artifact_id,
                artifact_kind="data",
                rationale_zh="依据登记标准复核该替代流程产物及其适用范围。",
                rationale_en="Review the replacement workflow artifact and its scope against registered criteria.",
                methods_zh="核对执行身份、输入输出、统计边界和结果重读。",
                methods_en="Check execution identity, inputs, outputs, statistical scope, and output reload.",
                results_zh="轻量夹具提供状态转换所需的完整身份与评审记录。",
                results_en="The lightweight fixture provides complete identities and review records for the transition.",
                conclusion_zh="按登记动作处理该产物并保留不可变历史。",
                conclusion_en="Apply the registered action while preserving immutable history.",
                panels=(),
                technical_status="passed" if active_evidence else "major",
                statistical_status="passed" if active_evidence else "major",
                biological_status="passed" if active_evidence else "major",
                robustness_status="passed" if active_evidence else "major",
                limitations_zh=("该夹具只验证修订节点的生命周期。",),
                limitations_en=("This fixture validates only the revision-node lifecycle.",),
                recommended_action=action,
                source_urls=("https://www.w3.org/TR/prov-o/",),
            )
            current = apply_event(
                current,
                "artifact_review_recorded",
                {"review": artifact_review.to_dict()},
                rationale="Record the revision lifecycle review.",
            )
            scientific_decision = ScientificDecision(
                id=f"decision-{artifact_id}",
                review_id=review_id,
                artifact_id=artifact_id,
                hypothesis_ids=(hypothesis().id,),
                action=action,
                rationale_zh="根据科学评审执行登记动作。",
                rationale_en="Apply the registered action from the scientific review.",
                active_evidence=active_evidence,
                next_plan_node_ids=(replacement.id,) if action == "rerun-same-method" else (),
                next_hypothesis_ids=(),
                revision_contract_id=(
                    replacement.revision_contract.id if action == "rerun-same-method" else None
                ),
            )
            return apply_event(
                current,
                "scientific_decision_recorded",
                {"decision": scientific_decision.to_dict()},
                rationale="Bind the exact revision lifecycle decision.",
            )

        state = reviewed(
            first.state,
            source_artifact_id,
            "review-revision-source",
            "rerun-same-method",
            active_evidence=False,
        )
        second = controller.resume(state.to_dict())
        self.assertEqual(second.stop_reason, "awaiting_artifact_review")
        replacement_artifact_id = next(iter(replacement.planned_output_artifact_ids.values()))
        state = reviewed(
            second.state,
            replacement_artifact_id,
            "review-revision-result",
            "retain-as-evidence",
            active_evidence=True,
        )
        final = controller.resume(state.to_dict())
        self.assertEqual(final.stop_reason, "plan_completed")
        self.assertEqual(
            {node.id: node.status for node in final.active_plan.nodes},
            {source.id: "superseded", replacement.id: "completed"},
        )

    def test_serial_nodes_materialize_artifacts_in_dependency_order_and_update_state(self):
        temporary, registry, state, plan = serial_fixture()
        self.addCleanup(temporary.cleanup)
        order = []

        def executor(current_state, _plan, node, active_registry, **_kwargs):
            order.append(node.module_id)
            return completed_execution(current_state, node, active_registry)

        result = ResearchController(registry, environment_provider=lambda _manifest: None, node_executor=executor).advance(state, plan)

        self.assertEqual(order, ["normalize-matrix", "test-contrast"])
        self.assertEqual(result.stop_reason, "plan_completed")
        self.assertEqual(len(result.executions), 2)
        self.assertTrue({execution.output_artifact_ids[0] for execution in result.executions} <= {artifact.id for artifact in result.state.artifacts})
        self.assertEqual({node.status for node in result.active_plan.nodes}, {"completed"})
        self.assertGreater(result.state.revision, state.revision)

    def test_independent_ready_nodes_execute_in_parallel_but_merge_deterministically(self):
        temporary, registry = workflow_registry(
            (
                module_payload("normalize-matrix", "count_matrix", "normalized_matrix"),
                module_payload("measure-image", "image_collection", "image_measurements"),
            )
        )
        self.addCleanup(temporary.cleanup)
        state = state_with(inline_artifact("artifact-counts", "count_matrix"), inline_artifact("artifact-images", "image_collection"))
        plan = plan_research(
            state,
            registry,
            build_capability_graph(registry),
            (
                PlanningRequest("request-normalized", "normalized_matrix", (hypothesis().id,), ("cell-state-association",)),
                PlanningRequest("request-image", "image_measurements", (hypothesis().id,), ("regulatory-association",)),
            ),
        )
        threads = set()

        def executor(current_state, _plan, node, active_registry, **_kwargs):
            threads.add(threading.current_thread().name)
            time.sleep(0.05)
            return completed_execution(current_state, node, active_registry)

        result = ResearchController(
            registry,
            environment_provider=lambda _manifest: None,
            node_executor=executor,
            policy=ControllerPolicy(max_plan_revisions=2, max_node_attempts=1, parallel_workers=2, stop_on_fatal=True),
        ).advance(state, plan)

        self.assertGreaterEqual(len(threads), 2)
        self.assertEqual(tuple(execution.node_id for execution in result.executions), tuple(sorted(execution.node_id for execution in result.executions)))
        self.assertEqual(result.stop_reason, "plan_completed")

    def test_blocked_downstream_preserves_completed_upstream_and_stops_branch(self):
        temporary, registry, state, plan = serial_fixture()
        self.addCleanup(temporary.cleanup)

        def executor(current_state, _plan, node, active_registry, **_kwargs):
            if node.module_id == "test-contrast":
                return NodeExecution(
                    node.id,
                    node.module_id,
                    "1.0.0",
                    "blocked",
                    None,
                    tuple(node.input_bindings.values()),
                    (),
                    (),
                    (),
                    ("UNVALIDATED_DEPENDENCY_VERSION",),
                    {},
                    "CompatibilityError",
                )
            return completed_execution(current_state, node, active_registry)

        result = ResearchController(registry, environment_provider=lambda _manifest: None, node_executor=executor).advance(state, plan)

        self.assertEqual(result.stop_reason, "blocked")
        self.assertIn("normalized_matrix", {artifact.artifact_type for artifact in result.state.artifacts})
        self.assertEqual({node.module_id: node.status for node in result.active_plan.nodes}["test-contrast"], "blocked")

    def test_evidence_mapper_changes_hypothesis_status_and_state_replays(self):
        temporary, registry, state, plan = serial_fixture()
        self.addCleanup(temporary.cleanup)

        def mapper(execution, node, current_state):
            if node.module_id != "test-contrast":
                return ()
            return (
                EvidenceRecord(
                    id="evidence-controller-contrast",
                    hypothesis_id=hypothesis().id,
                    artifact_id=execution.output_artifact_ids[0],
                    relation="supports",
                    evidence_type="cell-state-association",
                    independent_group="controller-cohort",
                    study_design="paired-perturbation",
                    experimental_unit=current_state.context.experimental_unit,
                    effect={"estimate": -0.5},
                    uncertainty={"interval": [-0.8, -0.2]},
                    quality_status="passed",
                    limitations=(),
                    rationale="The completed contrast matches one prespecified expected observation.",
                ),
            )

        controller = ResearchController(
            registry,
            environment_provider=lambda _manifest: None,
            node_executor=lambda current_state, _plan, node, active_registry, **_kwargs: completed_execution(current_state, node, active_registry),
            evidence_mapper=mapper,
        )
        result = controller.advance(state, plan)
        resumed = controller.resume(result.state.to_dict())

        self.assertEqual(result.assessments[0].new_status, "inconclusive")
        self.assertEqual(result.state.hypotheses[0].status, "inconclusive")
        self.assertEqual(resumed.state.state_digest, result.state.state_digest)
        self.assertEqual(resumed.stop_reason, "already_complete")

    def test_transient_failure_retries_within_bound_and_then_completes(self):
        temporary, registry = workflow_registry((module_payload("normalize-matrix", "count_matrix", "normalized_matrix"),))
        self.addCleanup(temporary.cleanup)
        state = state_with(inline_artifact("artifact-counts", "count_matrix"))
        plan = plan_research(
            state,
            registry,
            build_capability_graph(registry),
            (PlanningRequest("request-normalized", "normalized_matrix", (hypothesis().id,), ("cell-state-association",)),),
        )
        attempts = []

        def executor(current_state, _plan, node, active_registry, **_kwargs):
            attempts.append(node.attempt)
            if len(attempts) == 1:
                return NodeExecution(node.id, node.module_id, "1.0.0", "failed", None, tuple(node.input_bindings.values()), (), (), (), (), {}, "TransientError")
            return completed_execution(current_state, node, active_registry)

        result = ResearchController(
            registry,
            environment_provider=lambda _manifest: None,
            node_executor=executor,
            policy=ControllerPolicy(max_plan_revisions=1, max_node_attempts=2, parallel_workers=1, stop_on_fatal=True),
        ).advance(state, plan)

        self.assertEqual(attempts, [1, 2])
        self.assertEqual(result.stop_reason, "plan_completed")

    def test_blocked_primary_is_replaced_by_revision_with_declared_alternative(self):
        primary = module_payload("primary-normalizer", "count_matrix", "normalized_matrix", alternatives=("alternative-normalizer",))
        alternative = module_payload("alternative-normalizer", "count_matrix", "normalized_matrix")
        temporary, registry = workflow_registry((primary, alternative))
        self.addCleanup(temporary.cleanup)
        state = state_with(inline_artifact("artifact-counts", "count_matrix"))
        initial = plan_research(
            state,
            registry,
            build_capability_graph(registry),
            (PlanningRequest("request-normalized", "normalized_matrix", (hypothesis().id,), ("cell-state-association",)),),
            compatible_module_ids=("primary-normalizer",),
        )

        def executor(current_state, _plan, node, active_registry, **_kwargs):
            if node.module_id == "primary-normalizer":
                return NodeExecution(
                    node_id=node.id,
                    module_id=node.module_id,
                    module_version="1.0.0",
                    status="blocked",
                    compatibility_row_id=None,
                    input_artifact_ids=tuple(node.input_bindings.values()),
                    output_artifact_ids=(),
                    artifacts=(),
                    quality_findings=(),
                    compatibility_finding_codes=("UNVALIDATED_DEPENDENCY_VERSION",),
                    provenance={},
                    safe_error_class="CompatibilityError",
                )
            return completed_execution(current_state, node, active_registry)

        def replanner(current_state, parent, _executions, _findings):
            old = parent.nodes[0]
            replacement = PlanNode(
                **{
                    **old.__dict__,
                    "id": "node-alternative-normalizer",
                    "module_id": "alternative-normalizer",
                    "planned_output_artifact_ids": {"profile": "artifact-planned-alternative"},
                    "compatibility_row_candidates": (registry.get("alternative-normalizer").compatibility_matrix[0].id,),
                    "status": "pending",
                    "attempt": 0,
                }
            )
            return ResearchDAG.create(
                id="plan-alternative-revision",
                objective=parent.objective,
                nodes=(replacement,),
                required_output_artifact_types=parent.required_output_artifact_types,
                plan_type="single",
                revision=parent.revision + 1,
                parent_plan_id=parent.id,
                rationale=("The primary module was blocked, so use its declared compatible alternative.",),
            )

        result = ResearchController(
            registry,
            environment_provider=lambda _manifest: None,
            node_executor=executor,
            replanner=replanner,
            policy=ControllerPolicy(max_plan_revisions=2, max_node_attempts=1, parallel_workers=1, stop_on_fatal=True),
        ).advance(state, initial)

        self.assertEqual(result.stop_reason, "plan_completed")
        self.assertEqual(result.active_plan.parent_plan_id, initial.id)
        self.assertEqual(result.active_plan.revision, 2)
        self.assertEqual(tuple(execution.module_id for execution in result.executions), ("primary-normalizer", "alternative-normalizer"))
        self.assertEqual(len(result.state.plans), 2)

    def test_default_controller_replaces_a_blocked_node_with_a_port_compatible_declared_alternative(self):
        primary = module_payload("primary-normalizer", "count_matrix", "normalized_matrix", alternatives=("alternative-normalizer",))
        alternative = module_payload("alternative-normalizer", "count_matrix", "normalized_matrix")
        temporary, registry = workflow_registry((primary, alternative))
        self.addCleanup(temporary.cleanup)
        state = state_with(inline_artifact("artifact-counts", "count_matrix"))
        initial = plan_research(
            state,
            registry,
            build_capability_graph(registry),
            (PlanningRequest("request-normalized", "normalized_matrix", (hypothesis().id,), ("cell-state-association",)),),
            compatible_module_ids=("primary-normalizer",),
        )

        def executor(current_state, _plan, node, active_registry, **_kwargs):
            if node.module_id == "primary-normalizer":
                return NodeExecution(
                    node.id,
                    node.module_id,
                    "1.0.0",
                    "blocked",
                    None,
                    tuple(node.input_bindings.values()),
                    (),
                    (),
                    (),
                    ("UNVALIDATED_DEPENDENCY_VERSION",),
                    {},
                    "CompatibilityError",
                )
            return completed_execution(current_state, node, active_registry)

        result = ResearchController(
            registry,
            environment_provider=lambda _manifest: None,
            node_executor=executor,
            policy=ControllerPolicy(max_plan_revisions=2, max_node_attempts=1, parallel_workers=1, stop_on_fatal=True),
        ).advance(state, initial)

        self.assertEqual(result.stop_reason, "plan_completed")
        self.assertEqual(result.active_plan.parent_plan_id, initial.id)
        self.assertEqual(tuple(execution.module_id for execution in result.executions), ("primary-normalizer", "alternative-normalizer"))

    def test_replan_inherits_verified_completed_upstream_and_replaces_only_blocked_downstream(self):
        normalizer = module_payload("normalize-matrix", "count_matrix", "normalized_matrix")
        primary = module_payload(
            "primary-contrast", "normalized_matrix", "contrast_result",
            alternatives=("alternative-contrast",),
        )
        alternative = module_payload("alternative-contrast", "normalized_matrix", "contrast_result")
        temporary, registry = workflow_registry((normalizer, primary, alternative))
        self.addCleanup(temporary.cleanup)
        state = state_with(inline_artifact("artifact-counts", "count_matrix"))
        initial = plan_research(
            state,
            registry,
            build_capability_graph(registry),
            (PlanningRequest("request-contrast", "contrast_result", (hypothesis().id,), ("cell-state-association",)),),
            compatible_module_ids=("normalize-matrix", "primary-contrast"),
        )

        def executor(current_state, _plan, node, active_registry, **_kwargs):
            if node.module_id == "primary-contrast":
                return NodeExecution(
                    node.id, node.module_id, "1.0.0", "blocked", None,
                    tuple(node.input_bindings.values()), (), (), (),
                    ("UNVALIDATED_DEPENDENCY_VERSION",), {}, "CompatibilityError",
                )
            return completed_execution(current_state, node, active_registry)

        result = ResearchController(
            registry,
            environment_provider=lambda _manifest: None,
            node_executor=executor,
            policy=ControllerPolicy(max_plan_revisions=2, max_node_attempts=1, parallel_workers=1),
        ).advance(state, initial)

        self.assertEqual(result.stop_reason, "plan_completed")
        self.assertEqual(
            tuple(execution.module_id for execution in result.executions),
            ("normalize-matrix", "primary-contrast", "alternative-contrast"),
        )
        parent_normalizer = next(node for node in result.state.plans[0].nodes if node.module_id == "normalize-matrix")
        child_normalizer = next(node for node in result.active_plan.nodes if node.module_id == "normalize-matrix")
        self.assertEqual(child_normalizer, parent_normalizer)
        self.assertEqual(child_normalizer.status, "completed")
        self.assertIn("alternative-contrast", {node.module_id for node in result.active_plan.nodes})

    def test_default_controller_does_not_cycle_between_reciprocal_alternatives(self):
        primary = module_payload("primary-normalizer", "count_matrix", "normalized_matrix", alternatives=("alternative-normalizer",))
        alternative = module_payload("alternative-normalizer", "count_matrix", "normalized_matrix", alternatives=("primary-normalizer",))
        temporary, registry = workflow_registry((primary, alternative))
        self.addCleanup(temporary.cleanup)
        state = state_with(inline_artifact("artifact-counts", "count_matrix"))
        initial = plan_research(
            state,
            registry,
            build_capability_graph(registry),
            (PlanningRequest("request-normalized", "normalized_matrix", (hypothesis().id,), ("cell-state-association",)),),
            compatible_module_ids=("primary-normalizer",),
        )

        def executor(_current_state, _plan, node, _active_registry, **_kwargs):
            return NodeExecution(
                node.id,
                node.module_id,
                "1.0.0",
                "blocked",
                None,
                tuple(node.input_bindings.values()),
                (),
                (),
                (),
                ("UNVALIDATED_DEPENDENCY_VERSION",),
                {},
                "CompatibilityError",
            )

        result = ResearchController(
            registry,
            environment_provider=lambda _manifest: None,
            node_executor=executor,
            policy=ControllerPolicy(max_plan_revisions=3, max_node_attempts=1, parallel_workers=1, stop_on_fatal=True),
        ).advance(state, initial)

        self.assertEqual(result.stop_reason, "blocked")
        self.assertEqual(tuple(execution.module_id for execution in result.executions), ("primary-normalizer", "alternative-normalizer"))
        self.assertEqual(len(result.state.plans), 2)


if __name__ == "__main__":
    unittest.main()
