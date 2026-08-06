import hashlib
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from biomed_workbench.kernel.artifact_store import ProjectArtifactStore
from biomed_workbench.kernel.execution_receipts import ExecutionHandoff, ObservedExecutionReceipt
from biomed_workbench.kernel.execution_chain import gate_adjudication_bundle_digest
from biomed_workbench.kernel.identity import digest_value
from biomed_workbench.kernel.plans import PlanNode, ResearchDAG
from biomed_workbench.kernel.state import ProjectState, apply_event
from biomed_workbench.kernel.scientific_dependency import ScientificGateAdjudication
from biomed_workbench.orchestration.controller import ResearchController
from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry
from biomed_workbench.modules.contract import (
    compatibility_contract_digest,
    observed_output_contract_digest,
    observed_output_protocol_version,
)
from biomed_workbench.orchestration.execution_ingest import ingest_execution_bundle
from tests.unit.kernel.test_hypotheses import hypothesis
from tests.unit.kernel.test_scientific_dependency import decision, review
from tests.unit.orchestration.test_planner import inline_artifact, state_with


class ExecutionIngestTests(unittest.TestCase):
    def _adjudicate_pending_gates(self, state, *, forced_status=None):
        observed = state.observed_executions[-1]
        artifact_id = "artifact-enrichment-result"
        adjudications = []
        for gate_id, result in observed.postflight_results.items():
            if result["status"] not in {"requires_review", "not_evaluable"}:
                continue
            evaluation = result["evaluations"][0]
            adjudication = ScientificGateAdjudication(
                id=f"adjudication-{gate_id}",
                artifact_id=artifact_id,
                observed_execution_receipt_id=observed.id,
                gate_id=gate_id,
                port=evaluation["port"],
                evaluator_type=evaluation["evaluator_type"],
                gate_result_digest=observed.postflight_result_digests[gate_id],
                evidence_payload_sha256=evaluation["evidence_payload_sha256"],
                adjudication_mode="manual",
                observed_value=evaluation["observed_metric"],
                criterion=evaluation["threshold"],
                finding=evaluation["reason"],
                status=forced_status or ("accepted-with-caveat" if result["status"] == "not_evaluable" else "accepted"),
                reviewer_identity="independent-scientific-reviewer",
                rationale_zh="审议者逐项核对该门禁对应的富集主表、参数、统计语义与适用范围后作出独立判断。",
                rationale_en="The reviewer independently checked the gate against the enrichment table, parameters, statistical semantics, and scope.",
                limitations_zh=("该审议只覆盖当前登记输入、输出与方法版本，不能外推到其他数据集。",),
                limitations_en=("This adjudication covers only the registered inputs, outputs, and method version and does not generalize to other data.",),
                source_urls=("https://bioconductor.org/packages/clusterProfiler/",),
            )
            state = apply_event(
                state,
                "scientific_gate_adjudicated",
                {"adjudication": adjudication.to_dict()},
                rationale="Record one independently reviewed scientific gate result.",
                affected_artifact_ids=(artifact_id,),
            )
            adjudications.append(adjudication)
        return state, tuple(adjudications)

    def _prepared_case(self, *, contract_digest=None):
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        manifest = registry.get("functional-enrichment")
        state = state_with(
            inline_artifact("artifact-genes", "gene_list_or_ranking"),
            inline_artifact("artifact-universe", "measured_gene_universe"),
        )
        node = PlanNode(
            id="node-functional-enrichment",
            module_id=manifest.id,
            input_bindings={"gene_evidence": "artifact-genes", "tested_universe": "artifact-universe"},
            dependencies=(), branch_id="branch-enrichment", target_hypothesis_ids=(hypothesis().id,),
            expected_evidence_types=("functional-enrichment",),
            expected_output_artifact_types=("functional_enrichment_evidence",),
            planned_output_artifact_ids={"functional_enrichment_evidence": "artifact-enrichment-result"},
            compatibility_row_candidates=(manifest.compatibility_matrix[0].id,),
            status="awaiting_observed_execution", attempt=1,
        )
        plan = ResearchDAG.create(
            id="plan-functional-enrichment", objective="Test the registered gene set against its measured universe.",
            nodes=(node,), required_output_artifact_types=("functional_enrichment_evidence",),
            plan_type="single", revision=1, parent_plan_id=None,
            rationale=("Exercise adversarial observed-result admission.",),
        )
        state = apply_event(state, "plan_created", {"plan": plan.to_dict(), "activate": True}, rationale="Register the test plan.")
        handoff = ExecutionHandoff.create(
            plan_node_id=node.id, module_id=manifest.id, module_version=manifest.version,
            request_digest=digest_value({"genes": ["TP53"], "universe": ["TP53", "BRCA1"]}),
            compatibility_row_id=manifest.compatibility_matrix[0].id,
            observed_output_contract_digest=contract_digest or observed_output_contract_digest(manifest),
            planned_output_artifact_ids=node.planned_output_artifact_ids,
            protocol={
                "result_kind": "execution_handoff",
                "execution_state": "prepared-not-run",
                "observed_output_protocol_version": observed_output_protocol_version(manifest),
                "required_postflight_gate_ids": sorted(gate.id for gate in manifest.quality_gates),
                "required_postflight_gate_set_digest": digest_value(
                    sorted(gate.id for gate in manifest.quality_gates)
                ),
                "compatibility_contract_digest": compatibility_contract_digest(
                    manifest, manifest.compatibility_matrix[0].id
                ),
            },
        )
        state = apply_event(state, "execution_handoff_recorded", {"handoff": handoff.to_dict()}, rationale="Record the exact handoff.")
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        table = root / "enrichment.tsv"
        table.write_text(
            "term_id\tterm_name\tp_value\tadjusted_p_value\tgene_ratio\tbackground_ratio\tgene_set_size\toverlap_genes\n"
            "GO:0006281\tDNA repair\t0.01\t0.02\t1/1\t25/100\t25\tTP53\n",
            encoding="utf-8",
        )
        payload_digest = hashlib.sha256(table.read_bytes()).hexdigest()
        semantic = root / "enrichment.semantic.json"
        semantic.write_text(json.dumps({
            "schema_version": 1,
            "module_id": manifest.id,
            "module_version": manifest.version,
            "port": "functional_enrichment_evidence",
            "result_schema_id": (
                f"{manifest.id}:functional_enrichment_evidence:"
                f"{manifest.observed_output_contracts[0].semantic_profile}"
            ),
            "primary_payload_sha256": payload_digest,
            "analysis_mode": "ora",
            "input_accounting": {"tested_entities": 1, "background_entities": 100},
            "result_accounting": {"reported_records": 1},
            "limitations": [],
            "empty_result_reason": None,
            "handoff_request_digest": handoff.request_digest,
            "compatibility_contract_digest": compatibility_contract_digest(
                manifest, handoff.compatibility_row_id
            ),
            "input_artifacts": {
                artifact.id: artifact.content_digest
                for artifact in state.artifacts
                if artifact.id in node.input_bindings.values()
            },
        }, sort_keys=True), encoding="utf-8")
        bundle = {
            "handoff_id": handoff.id, "process_exit_code": 0,
            "runtime_versions": {
                "workflow": {"identity": "clusterProfiler", "version": "4.10.1"},
                "tools": {"clusterProfiler": "4.10.1", "fgsea": "1.28.0"},
                "dependencies": {
                    "AnnotationDbi": "1.64.1",
                    "digest": "0.6.39",
                    "enrichplot": "1.22.0",
                    "ggplot2": "3.5.2",
                    "jsonlite": "2.0.0",
                    "r": "4.3.2",
                },
                "version_policy": "tested",
                "compatibility_contract_digest": compatibility_contract_digest(
                    manifest, manifest.compatibility_matrix[0].id
                ),
            },
            "postflight_results": [{"gate_id": gate.id} for gate in manifest.quality_gates],
            "outputs": [{
                "port": "functional_enrichment_evidence",
                "content": {
                    "artifact_type": "functional_enrichment_evidence", "format": "tab-separated-values",
                    "processing_level": "tested", "result_summary": "A reloadable enrichment result was produced.",
                    "record_count": 1,
                    "provenance": {"workflow": "clusterProfiler", "workflow_version": "4.10.1",
                                   "parameters_digest": handoff.request_digest,
                                   "compatibility_row_id": handoff.compatibility_row_id},
                },
                "payload_files": [
                    {"role": "primary", "path": str(table), "media_type": "text/tab-separated-values"},
                    {"role": "semantic-metadata", "path": str(semantic), "media_type": "application/json"},
                ],
            }],
        }
        return registry, state, root, bundle

    def test_handoff_observation_reloads_outputs_and_enters_scientific_review(self):
        registry, state, root, bundle = self._prepared_case()
        state = ingest_execution_bundle(
            state,
            bundle,
            registry=registry,
            artifact_store=ProjectArtifactStore(root / "objects"),
        )

        self.assertEqual(state.plans[-1].nodes[0].status, "awaiting_review")
        self.assertEqual(len(state.observed_executions), 1)
        self.assertEqual(len(state.artifact_reloads), 1)
        self.assertEqual(len(state.execution_reviews), 1)
        self.assertEqual(state.artifact_reloads[0].artifact_id, "artifact-enrichment-result")
        gate_results = state.observed_executions[0].postflight_results
        self.assertEqual(set(gate_results), {item.id for item in registry.get("functional-enrichment").quality_gates})
        self.assertIn("requires_review", {item["status"] for item in gate_results.values()})
        self.assertNotEqual({item["status"] for item in gate_results.values()}, {"passed"})

    def test_compatible_nonbaseline_runtime_is_admitted_but_not_labeled_tested(self):
        registry, state, root, bundle = self._prepared_case()
        bundle["runtime_versions"]["version_policy"] = "compatible"
        bundle["runtime_versions"]["tools"]["clusterProfiler"] = "4.10.2"
        bundle["runtime_versions"]["workflow"]["version"] = "4.10.2"
        bundle["outputs"][0]["content"]["provenance"]["workflow_version"] = "4.10.2"
        state = ingest_execution_bundle(
            state,
            bundle,
            registry=registry,
            artifact_store=ProjectArtifactStore(root / "objects"),
        )
        receipt = state.observed_executions[-1]
        self.assertEqual(receipt.runtime_versions["workflow:clusterProfiler"], "4.10.2")
        self.assertEqual(receipt.runtime_versions["tool:fgsea"], "1.28.0")

    def test_observed_result_contract_rejects_adversarial_bundles(self):
        mutations = {
            "arbitrary content": lambda value: value["outputs"][0].update(content={"arbitrary_unvalidated_field": True}),
            "missing required field": lambda value: value["outputs"][0]["content"].pop("record_count"),
            "wrong payload role": lambda value: value["outputs"][0]["payload_files"][0].update(role="table"),
            "wrong payload media": lambda value: value["outputs"][0]["payload_files"][0].update(media_type="text/plain"),
            "missing postflight gate": lambda value: value["postflight_results"].pop(),
            "caller supplied gate verdict": lambda value: value["postflight_results"][0].update(status="passed"),
            "unobserved workflow version": lambda value: value["outputs"][0]["content"]["provenance"].update(workflow_version="99.0.0"),
            "missing required tool": lambda value: value["runtime_versions"]["tools"].pop("fgsea"),
            "missing required dependency": lambda value: value["runtime_versions"]["dependencies"].pop("AnnotationDbi"),
            "tool version outside row": lambda value: value["runtime_versions"]["tools"].update(fgsea="99.0.0"),
            "dependency version outside row": lambda value: value["runtime_versions"]["dependencies"].update(
                AnnotationDbi="99.0.0"
            ),
            "boolean disguised as zero exit": lambda value: value.update(process_exit_code=False),
            "unknown substitute workflow": lambda value: value["runtime_versions"].update(
                workflow={"identity": "invented-workflow", "version": "1.0.0"}
            ),
            "forged compatibility contract": lambda value: value["runtime_versions"].update(
                compatibility_contract_digest="f" * 64
            ),
            "tested policy with merely compatible version": lambda value: value["runtime_versions"]["tools"].update(
                clusterProfiler="4.10.2"
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                registry, state, root, bundle = self._prepared_case()
                invalid = copy.deepcopy(bundle)
                mutate(invalid)
                with self.assertRaises((ValueError, TypeError)):
                    ingest_execution_bundle(
                        state, invalid, registry=registry,
                        artifact_store=ProjectArtifactStore(root / "objects"),
                    )

    def test_reload_validator_rejects_plain_text_disguised_as_a_result_table(self):
        registry, state, root, bundle = self._prepared_case()
        Path(bundle["outputs"][0]["payload_files"][0]["path"]).write_text(
            "ordinary text without a scientific table contract\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "too few columns"):
            ingest_execution_bundle(
                state,
                bundle,
                registry=registry,
                artifact_store=ProjectArtifactStore(root / "objects"),
            )

    def test_semantic_validator_rejects_readable_but_scientifically_wrong_enrichment(self):
        cases = {
            "placeholder columns": (
                "foo\tbar\nx\ty\n",
                "placeholder or empty column names",
            ),
            "invalid probability": (
                "term_id\tterm_name\tp_value\tadjusted_p_value\tgene_ratio\tbackground_ratio\tgene_set_size\toverlap_genes\n"
                "GO:0006281\tDNA repair\t1.2\t0.02\t1/1\t2/100\t25\tTP53\n",
                "must lie in",
            ),
        }
        for label, (table_text, message) in cases.items():
            with self.subTest(label=label):
                registry, state, root, bundle = self._prepared_case()
                table = Path(bundle["outputs"][0]["payload_files"][0]["path"])
                table.write_text(table_text, encoding="utf-8")
                semantic = Path(bundle["outputs"][0]["payload_files"][1]["path"])
                metadata = json.loads(semantic.read_text(encoding="utf-8"))
                metadata["primary_payload_sha256"] = hashlib.sha256(table.read_bytes()).hexdigest()
                semantic.write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, message):
                    ingest_execution_bundle(
                        state, bundle, registry=registry,
                        artifact_store=ProjectArtifactStore(root / "objects"),
                    )

    def test_semantic_validator_recomputes_enrichment_accounting_relationships(self):
        registry, state, root, bundle = self._prepared_case()
        semantic = Path(bundle["outputs"][0]["payload_files"][1]["path"])
        metadata = json.loads(semantic.read_text(encoding="utf-8"))
        metadata["input_accounting"] = {
            "tested_entities": 999999,
            "background_entities": 1,
        }
        semantic.write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "overlap is inconsistent"):
            ingest_execution_bundle(
                state,
                bundle,
                registry=registry,
                artifact_store=ProjectArtifactStore(root / "objects"),
            )

    def test_semantic_metadata_must_bind_exact_input_artifact_digests(self):
        registry, state, root, bundle = self._prepared_case()
        semantic = Path(bundle["outputs"][0]["payload_files"][1]["path"])
        metadata = json.loads(semantic.read_text(encoding="utf-8"))
        metadata["input_artifacts"]["artifact-genes"] = "f" * 64
        semantic.write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "exact handoff inputs"):
            ingest_execution_bundle(
                state,
                bundle,
                registry=registry,
                artifact_store=ProjectArtifactStore(root / "objects"),
            )

    def test_plugin_rejects_caller_supplied_gate_verdicts_inside_semantic_metadata(self):
        registry, state, root, bundle = self._prepared_case()
        semantic = Path(bundle["outputs"][0]["payload_files"][1]["path"])
        metadata = json.loads(semantic.read_text(encoding="utf-8"))
        metadata["quality_metrics"] = {
            gate.id: True for gate in registry.get("functional-enrichment").quality_gates
        }
        semantic.write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "fields are incomplete or unsupported"):
            ingest_execution_bundle(
                state, bundle, registry=registry,
                artifact_store=ProjectArtifactStore(root / "objects"),
            )

    def test_handoff_rejects_observed_contract_digest_drift(self):
        registry, state, root, bundle = self._prepared_case(contract_digest="f" * 64)
        with self.assertRaisesRegex(ValueError, "contract changed"):
            ingest_execution_bundle(state, bundle, registry=registry, artifact_store=ProjectArtifactStore(root / "objects"))

    def test_ingest_rejects_a_gate_evaluator_digest_from_the_wrong_payload(self):
        registry, state, root, bundle = self._prepared_case()
        forged = {
            "status": "requires_review",
            "observed_metric": json.dumps("pending-independent-scientific-review"),
            "threshold": json.dumps(
                {"operator": "equals", "value": "accepted"},
                sort_keys=True,
                separators=(",", ":"),
            ),
            "evidence_payload_sha256": "f" * 64,
            "reason": "forged evidence binding",
            "evaluator_type": "provenance-design",
        }
        with patch(
            "biomed_workbench.modules.semantic_output_validation.evaluate_structured_gate",
            return_value=forged,
        ), self.assertRaisesRegex(ValueError, "differs from its declared payload role"):
            ingest_execution_bundle(
                state,
                bundle,
                registry=registry,
                artifact_store=ProjectArtifactStore(root / "objects"),
            )

    def test_ingest_review_retain_and_resume_completes_handoff_node(self):
        registry, state, root, bundle = self._prepared_case()
        state = ingest_execution_bundle(
            state, bundle, registry=registry, artifact_store=ProjectArtifactStore(root / "objects")
        )
        state = ProjectState.from_dict(state.to_dict())
        artifact_id = "artifact-enrichment-result"
        with self.assertRaisesRegex(ValueError, "unresolved scientific gates"):
            apply_event(
                state,
                "artifact_review_recorded",
                {"review": review(id="review-generic", artifact_id=artifact_id).to_dict()},
                rationale="A generic review must not bypass unresolved manifest gates.",
            )
        state, adjudications = self._adjudicate_pending_gates(state)
        artifact_review = review(
            id="review-artifact-enrichment-result",
            artifact_id=artifact_id,
            results_zh="富集结果及其主表已经按登记契约重新读取，身份、格式和门控证据完整。",
            results_en="The enrichment result and primary table were reloaded under the registered contract with complete identity, format, and gate evidence.",
            gate_adjudication_ids=tuple(item.id for item in adjudications),
        )
        state = apply_event(
            state, "artifact_review_recorded", {"review": artifact_review.to_dict()},
            rationale="Record the bilingual scientific review of the reloaded workflow output.",
        )
        retained = decision(
            id="decision-artifact-enrichment-result",
            review_id=artifact_review.id,
            artifact_id=artifact_id,
            next_plan_node_ids=(),
            gate_adjudication_digest=gate_adjudication_bundle_digest(state, artifact_id),
        )
        state = apply_event(
            state, "scientific_decision_recorded", {"decision": retained.to_dict()},
            rationale="Retain the reviewed workflow output as active evidence.",
        )
        result = ResearchController(
            registry,
            environment_provider=lambda _manifest: None,
            artifact_store=ProjectArtifactStore(root / "objects"),
        ).resume(state.to_dict())
        self.assertEqual(result.stop_reason, "plan_completed")
        self.assertEqual(result.active_plan.nodes[0].status, "completed")

    def test_gate_adjudication_must_bind_exact_receipt_result_and_evidence(self):
        registry, state, root, bundle = self._prepared_case()
        state = ingest_execution_bundle(
            state, bundle, registry=registry, artifact_store=ProjectArtifactStore(root / "objects")
        )
        observed = state.observed_executions[-1]
        gate_id = next(iter(observed.postflight_results))
        evaluation = observed.postflight_results[gate_id]["evaluations"][0]
        valid = ScientificGateAdjudication(
            id=f"adjudication-{gate_id}", artifact_id="artifact-enrichment-result",
            observed_execution_receipt_id=observed.id, gate_id=gate_id, port=evaluation["port"],
            evaluator_type=evaluation["evaluator_type"], gate_result_digest=observed.postflight_result_digests[gate_id],
            evidence_payload_sha256=evaluation["evidence_payload_sha256"],
            adjudication_mode="manual", observed_value=evaluation["observed_metric"],
            criterion=evaluation["threshold"], finding=evaluation["reason"], status="accepted",
            reviewer_identity="independent-scientific-reviewer",
            rationale_zh="审议者逐项核对门禁结果并记录与当前执行回执的精确对应关系。",
            rationale_en="The reviewer checked the gate result and recorded its exact relationship to the execution receipt.",
            limitations_zh=("该结论仅适用于本次登记执行与对应证据文件。",),
            limitations_en=("The conclusion applies only to this registered execution and its evidence files.",),
            source_urls=("https://bioconductor.org/packages/clusterProfiler/",),
        )
        mutations = {
            "receipt": {"observed_execution_receipt_id": "observed-wrong-receipt"},
            "gate": {"gate_id": "wrong-gate-id"},
            "port": {"port": "wrong-output-port"},
            "result digest": {"gate_result_digest": "f" * 64},
            "evidence digest": {"evidence_payload_sha256": "f" * 64},
            "observed value": {"observed_value": "forged-observation"},
            "criterion": {"criterion": "forged-criterion"},
            "finding": {"finding": "forged-finding"},
        }
        for label, mutation in mutations.items():
            with self.subTest(label=label):
                payload = {**valid.to_dict(), **mutation}
                with self.assertRaisesRegex(ValueError, "no pending gate|exact receipt result or evidence"):
                    apply_event(
                        state, "scientific_gate_adjudicated", {"adjudication": payload},
                        rationale="Reject a forged gate adjudication binding.",
                    )

    def test_handoff_receipt_rejects_digest_only_or_tampered_gate_results(self):
        registry, state, root, bundle = self._prepared_case()
        state = ingest_execution_bundle(
            state, bundle, registry=registry, artifact_store=ProjectArtifactStore(root / "objects")
        )
        payload = state.observed_executions[-1].to_dict()
        payload["postflight_results"] = {}
        with self.assertRaisesRegex(ValueError, "same gates"):
            ObservedExecutionReceipt.from_dict(payload)
        payload = state.observed_executions[-1].to_dict()
        gate_id = next(iter(payload["postflight_results"]))
        payload["postflight_results"][gate_id]["status"] = "passed"
        with self.assertRaisesRegex(ValueError, "digest differs"):
            ObservedExecutionReceipt.from_dict(payload)

    def test_state_rejects_a_structured_receipt_missing_one_frozen_handoff_gate(self):
        registry, prepared_state, root, bundle = self._prepared_case()
        completed_state = ingest_execution_bundle(
            prepared_state, bundle, registry=registry, artifact_store=ProjectArtifactStore(root / "objects")
        )
        payload = completed_state.observed_executions[-1].to_dict()
        gate_id = next(iter(payload["postflight_results"]))
        payload["postflight_results"].pop(gate_id)
        payload["postflight_result_digests"].pop(gate_id)
        shortened = ObservedExecutionReceipt.from_dict(payload)
        with self.assertRaisesRegex(ValueError, "frozen handoff gate set"):
            apply_event(
                prepared_state,
                "execution_observed",
                {"receipt": shortened.to_dict()},
                rationale="Reject a receipt that omits a frozen manifest gate.",
            )

    def test_unknown_duplicate_and_digest_drift_protocols_fail_at_handoff_boundary(self):
        _registry, state, _root, _bundle = self._prepared_case()
        base = state.execution_handoffs[-1].to_dict()
        mutations = {
            "unknown": lambda value: value["protocol"].update(observed_output_protocol_version="9.9.0"),
            "legacy": lambda value: value["protocol"].update(observed_output_protocol_version="2.0"),
            "duplicate": lambda value: value["protocol"]["required_postflight_gate_ids"].append(
                value["protocol"]["required_postflight_gate_ids"][0]
            ),
            "wrong digest": lambda value: value["protocol"].update(required_postflight_gate_set_digest="f" * 64),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                payload = copy.deepcopy(base)
                mutate(payload)
                with self.assertRaisesRegex(ValueError, "protocol|gate"):
                    ExecutionHandoff.from_dict(payload)

    def test_rejected_gate_can_be_reviewed_and_excluded_but_never_retained(self):
        registry, state, root, bundle = self._prepared_case()
        state = ingest_execution_bundle(
            state, bundle, registry=registry, artifact_store=ProjectArtifactStore(root / "objects")
        )
        state, adjudications = self._adjudicate_pending_gates(state, forced_status="rejected")
        artifact_id = "artifact-enrichment-result"
        artifact_review = review(
            id="review-rejected-enrichment",
            artifact_id=artifact_id,
            technical_status="fatal",
            statistical_status="major",
            biological_status="major",
            robustness_status="fatal",
            recommended_action="exclude-invalid",
            conclusion_zh="该产物未通过关键科学门禁，应保留失败记录并从有效证据中排除。",
            conclusion_en="The artifact failed a critical scientific gate and must remain in the audit record while being excluded from active evidence.",
            gate_adjudication_ids=tuple(item.id for item in adjudications),
        )
        state = apply_event(
            state,
            "artifact_review_recorded",
            {"review": artifact_review.to_dict()},
            rationale="Record the fatal review without erasing the rejected gate evidence.",
        )
        retain = decision(
            id="decision-invalid-retain",
            review_id=artifact_review.id,
            artifact_id=artifact_id,
            action="retain-as-evidence",
            active_evidence=True,
            next_plan_node_ids=(),
            gate_adjudication_digest=gate_adjudication_bundle_digest(state, artifact_id),
        )
        with self.assertRaisesRegex(ValueError, "blocking|retention"):
            apply_event(
                state,
                "scientific_decision_recorded",
                {"decision": retain.to_dict()},
                rationale="A rejected gate must not be retained.",
            )
        excluded = decision(
            id="decision-exclude-invalid",
            review_id=artifact_review.id,
            artifact_id=artifact_id,
            action="exclude-invalid",
            active_evidence=False,
            next_plan_node_ids=(),
            gate_adjudication_digest=gate_adjudication_bundle_digest(state, artifact_id),
        )
        state = apply_event(
            state,
            "scientific_decision_recorded",
            {"decision": excluded.to_dict()},
            rationale="Exclude the rejected output while retaining its complete audit chain.",
        )
        result = ResearchController(
            registry,
            environment_provider=lambda _manifest: None,
            artifact_store=ProjectArtifactStore(root / "objects"),
        ).resume(state.to_dict())
        self.assertEqual(result.stop_reason, "scientific_evidence_excluded")
        self.assertEqual(result.active_plan.nodes[0].status, "skipped")
        self.assertNotIn(artifact_id, {item.artifact_id for item in result.state.evidence})

    def test_unresolved_gate_can_request_more_data_and_enters_blocked_state(self):
        registry, state, root, bundle = self._prepared_case()
        state = ingest_execution_bundle(
            state, bundle, registry=registry, artifact_store=ProjectArtifactStore(root / "objects")
        )
        state, adjudications = self._adjudicate_pending_gates(state, forced_status="unresolved")
        artifact_id = "artifact-enrichment-result"
        artifact_review = review(
            id="review-unresolved-enrichment",
            artifact_id=artifact_id,
            technical_status="major",
            statistical_status="major",
            biological_status="major",
            robustness_status="major",
            recommended_action="acquire-more-data",
            gate_adjudication_ids=tuple(item.id for item in adjudications),
        )
        state = apply_event(state, "artifact_review_recorded", {"review": artifact_review.to_dict()}, rationale="Record an unresolved review.")
        blocked = decision(
            id="decision-acquire-more-data",
            review_id=artifact_review.id,
            artifact_id=artifact_id,
            action="acquire-more-data",
            active_evidence=False,
            next_plan_node_ids=(),
            gate_adjudication_digest=gate_adjudication_bundle_digest(state, artifact_id),
        )
        state = apply_event(state, "scientific_decision_recorded", {"decision": blocked.to_dict()}, rationale="Block until additional data resolve the gate.")
        result = ResearchController(
            registry,
            environment_provider=lambda _manifest: None,
            artifact_store=ProjectArtifactStore(root / "objects"),
        ).resume(state.to_dict())
        self.assertEqual(result.stop_reason, "awaiting_additional_data")
        self.assertEqual(result.active_plan.nodes[0].status, "blocked")


if __name__ == "__main__":
    unittest.main()
