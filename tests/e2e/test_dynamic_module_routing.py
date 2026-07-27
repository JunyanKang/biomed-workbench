import tempfile
import unittest
from pathlib import Path

from biomed_workbench.modules.registry import ModuleRegistry
from biomed_workbench.router import route
from tests.unit.test_module_contract import valid_manifest_payload
from tests.unit.test_module_registry import write_manifest


class DynamicModuleRoutingTests(unittest.TestCase):
    def test_compound_wetlab_request_does_not_expand_from_generic_simulation_or_measurement_words(self):
        plan = route(
            "Quantify bacterial CFU from serial dilution plates, summarize crystal-violet biofilm measurements, "
            "and distinguish observed results from a bacterial population scenario."
        )

        self.assertEqual(plan["matched_workflows"], ["wetlab"])
        self.assertEqual(
            plan["selected_module_ids"],
            ["cfu-enumeration", "biofilm-crystal-violet", "bacterial-population-scenario"],
        )
        self.assertNotIn("msprime-demographic-simulation", plan["selected_module_ids"])
        self.assertNotIn("network-analysis", plan["selected_module_ids"])
        self.assertNotIn("single-cell-marker-discovery", plan["selected_module_ids"])

    def test_composite_scientific_queries_ignore_generic_context_words_across_domains(self):
        communication = route("analyze donor-aware single-cell differential expression and validate cell-cell communication")
        annotation = route("identify cell types in scRNA-seq and retain unknown populations")
        spatial = route("analyze spatial transcriptomics and validate spatial gene patterns")
        disorder = route("compare protein disorder profile with AlphaFold confidence for P04637")

        self.assertEqual(communication["matched_workflows"], ["omics"])
        self.assertIn("single-cell-communication", communication["selected_module_ids"])
        self.assertNotIn("image-chroma-key-remove", communication["selected_module_ids"])
        self.assertEqual(annotation["matched_workflows"], ["omics"])
        self.assertNotIn("point-tracking", annotation["selected_module_ids"])
        self.assertEqual(spatial["matched_workflows"], ["omics"])
        self.assertEqual(spatial["selected_module_ids"], ["single-cell-spatial-analysis"])
        self.assertEqual(disorder["matched_workflows"], ["evidence"])
        self.assertEqual(disorder["selected_module_ids"], ["protein-disorder-evidence", "alphafold-structure-evidence"])

    def test_exact_protein_disorder_lookup_is_not_expanded_by_generic_profile_terms(self):
        payload = route("retrieve protein disorder profile for UniProt P04637")

        self.assertEqual(payload["matched_workflows"], ["evidence"])
        self.assertEqual(payload["selected_module_ids"], ["protein-disorder-evidence"])

    def test_cfse_proliferation_intent_does_not_leak_to_alignment_indexing(self):
        plan = route("analyze CFSE proliferation and division index")

        self.assertEqual(plan["selected_module_ids"], ["dye-dilution-proliferation"])

    def test_fcs_import_expands_into_declared_flow_cytometry_gating(self):
        plan = route("导入 FCS 流式细胞术文件并做门控")

        self.assertEqual(plan["selected_module_ids"], ["fcs-event-import", "flow-cytometry-summary"])
        self.assertEqual(plan["plan_type"], "serial")

    def test_immunophenotype_expands_into_event_import_and_gate_lineage(self):
        plan = route("quantify flow cytometry immunophenotype")

        self.assertEqual(
            plan["selected_module_ids"],
            ["fcs-event-import", "flow-cytometry-summary", "flow-immunophenotype-summary"],
        )
        self.assertEqual(plan["plan_type"], "serial")

    def test_cell_migration_metrics_expands_the_declared_tracking_upstream(self):
        plan = route("追踪细胞并量化迁移轨迹")

        self.assertEqual(plan["selected_module_ids"], ["point-tracking", "cell-migration-metrics"])
        self.assertEqual(plan["plan_type"], "serial")

    def test_primer_pair_reference_panel_discovers_the_specificity_module(self):
        plan = route("Screen this PCR primer pair against my plasmid and paralog reference panel")

        self.assertIn("primer-pair-specificity-screen", plan["selected_module_ids"])

    def test_connective_words_do_not_create_cross_domain_routes(self):
        plan = route("single-cell RNA-seq QC and differential expression")
        self.assertEqual(plan["matched_workflows"], ["omics"])
        routed = {item["id"] for step in plan["steps"] for item in step["candidates"]}
        self.assertIn("single-cell-foundation-workflow", routed)
        self.assertIn("differential-expression", routed)
        self.assertNotIn("qpcr-relative-expression", routed)
        self.assertNotIn("claim-evidence-integrity-audit", routed)

    def test_compound_single_cell_request_selects_all_explicit_concepts_without_domain_leakage(self):
        plan = route(
            "分析单细胞RNA+ATAC数据，做doublet、ambient RNA、marker和atlas注释，"
            "再做组成差异、轨迹、细胞通讯、SCENIC调控网络和空间转录组验证"
        )
        selected = set(plan["selected_module_ids"])
        visible = {item["id"] for step in plan["steps"] for item in step["candidates"]}

        self.assertEqual(plan["matched_workflows"], ["omics"])
        self.assertTrue(
            {
                "single-cell-atlas-annotation",
                "single-cell-communication",
                "single-cell-complex-inference",
                "single-cell-doublet-detection",
                "single-cell-droplet-decontamination",
                "single-cell-marker-discovery",
                "single-cell-multimodal-integration",
                "single-cell-regulatory-network",
                "single-cell-spatial-analysis",
                "single-cell-trajectory-topology",
            }
            <= selected
        )
        self.assertTrue(selected <= visible)
        self.assertNotIn("docking-pose-review", visible)

    def test_donor_aware_single_cell_inference_routes_from_manifest(self):
        plan = route("Run donor-aware single-cell pseudobulk differential expression with edgeR")
        routed = {item["id"] for step in plan["steps"] for item in step["candidates"]}

        self.assertIn("single-cell-donor-inference", routed)
        self.assertIn("omics", plan["matched_workflows"])

    def test_single_cell_integration_benchmark_routes_from_manifest(self):
        plan = route("Benchmark Harmony Scanorama and BBKNN integration without biological overcorrection")
        routed = {item["id"] for step in plan["steps"] for item in step["candidates"]}

        self.assertIn("single-cell-batch-integration", routed)

    def test_single_cell_generative_model_routes_from_manifest(self):
        plan = route("Train scVI and validate scANVI on held-out reviewed labels")
        routed = {item["id"] for step in plan["steps"] for item in step["candidates"]}

        self.assertIn("single-cell-generative-modeling", routed)

    def test_single_cell_reference_annotation_routes_from_manifest(self):
        plan = route("Annotate single cells with SingleR markers Cell Ontology constraints and unknown retention")
        routed = {item["id"] for step in plan["steps"] for item in step["candidates"]}

        self.assertIn("single-cell-reference-annotation", routed)

    def test_reference_map_query_prefers_reference_annotation(self):
        plan = route("Reference map single-cell annotation")
        selected = set(plan["selected_module_ids"])
        routed = {item["id"] for step in plan["steps"] for item in step["candidates"]}

        self.assertIn("single-cell-reference-annotation", routed)
        self.assertIn("single-cell-reference-annotation", selected)

    def test_single_cell_trajectory_velocity_routes_from_manifest(self):
        plan = route("Run scVelo RNA velocity latent time and direction-validated pseudotime")
        routed = {item["id"] for step in plan["steps"] for item in step["candidates"]}

        self.assertIn("single-cell-trajectory-velocity", routed)

    def test_regvelo_routes_and_composes_from_manifest(self):
        plan = route(
            "Use RegVelo with an independently defined GRN to compare regulatory velocity, "
            "CellRank fate probabilities, and transcription factor perturbation hypotheses"
        )
        selected = set(plan["selected_module_ids"])

        self.assertIn("single-cell-regulatory-velocity", selected)
        self.assertIn("single-cell-fate-mapping", selected)
        self.assertIn("omics", plan["matched_workflows"])

    def test_velocity_regvelo_query_excludes_generative_modeling(self):
        plan = route(
            "Run RNA velocity and RegVelo with CellRank fate and annotation"
        )
        selected = set(plan["selected_module_ids"])

        self.assertIn("single-cell-regulatory-velocity", selected)
        self.assertIn("single-cell-fate-mapping", selected)
        self.assertNotIn("single-cell-generative-modeling", selected)

    def test_multi_method_annotation_consensus_routes_to_atlas_annotation(self):
        plan = route(
            "Reconcile CellTypist Azimuth popV SingleR and scANVI annotations with "
            "Cell Ontology labels and keep conflicts as Unknown"
        )

        self.assertIn("single-cell-atlas-annotation", plan["selected_module_ids"])

    def test_scRNA_seq_empty_droplet_request_routes_to_single_cell_droplet_module(self):
        plan = route("做scRNA-seq空滴去除")

        self.assertEqual(plan["matched_workflows"], ["omics"])
        self.assertEqual(plan["selected_module_ids"], ["single-cell-droplet-decontamination"])

    def test_single_cell_complex_inference_query_routes_from_manifest(self):
        plan = route(
            "Run single-cell complex differential inference with longitudinal mixed models and variance decomposition"
        )

        self.assertIn("single-cell-complex-inference", {item["id"] for step in plan["steps"] for item in step["candidates"]})
        self.assertIn("single-cell-complex-inference", plan["selected_module_ids"])

    def test_single_cell_trajectory_velocity_does_not_leak_to_imaging_tracking(self):
        plan = route("做单细胞轨迹分析和RNA velocity")

        self.assertEqual(plan["matched_workflows"], ["omics"])
        self.assertNotIn("imaging", plan["matched_workflows"])
        routed = {item["id"] for step in plan["steps"] for item in step["candidates"]}
        self.assertIn("single-cell-fate-mapping", routed)
        self.assertIn("single-cell-trajectory-topology", routed)
        self.assertNotIn("point-tracking", routed)
        self.assertNotIn("cell-migration-metrics", routed)

    def test_medical_imaging_query_routes_to_medical_imaging_modules(self):
        plan = route("检查 DICOM / NIfTI 医疗影像序列并做体积摘要与元数据隐私审计")
        routed = {item["id"] for step in plan["steps"] for item in step["candidates"]}

        self.assertEqual(plan["matched_workflows"], ["imaging"])
        self.assertIn("medical-imaging-volume-summary", plan["selected_module_ids"])
        self.assertIn("medical-imaging-metadata-audit", plan["selected_module_ids"])
        self.assertIn("medical-imaging-volume-summary", routed)
        self.assertIn("medical-imaging-metadata-audit", routed)

    def test_router_contains_no_module_specific_intent_table(self):
        source = (Path(__file__).resolve().parents[2] / "biomed_workbench" / "router.py").read_text(encoding="utf-8")

        self.assertNotIn("INTENT_BOOSTS", source)
        self.assertNotIn("WORKFLOW_KEYWORDS", source)
        self.assertNotIn('"crispr-design"', source)
        self.assertNotIn('"manuscript-audit"', source)
        self.assertNotIn('"temporal-integrity-audit"', source)
        self.assertNotIn('"assertion-citation-coverage-audit"', source)
        self.assertNotIn('"manuscript-revision-lineage"', source)
        self.assertNotIn('"manuscript-revision-base"', source)
        self.assertIn("_select_ranked_modules", source)

    def test_new_fixture_module_routes_from_manifest_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = valid_manifest_payload()
            payload["id"] = "neoenzyme-flux"
            payload["title"] = "Quantify neoenzyme flux"
            payload["intents"] = ["quantify neoenzyme flux", "量化新酶通量"]
            payload["questions"] = ["Does the new enzyme alter pathway flux?"]
            write_manifest(root, payload)
            registry = ModuleRegistry.discover(root)

            plan = route("请量化新酶通量", registry=registry)

        candidate = plan["steps"][0]["candidates"][0]
        self.assertEqual(candidate["id"], "neoenzyme-flux")
        self.assertTrue(candidate["selection_reasons"])

    def test_unknown_domain_is_discovered_without_router_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = valid_manifest_payload()
            payload["id"] = "ecology-flux"
            payload["domains"] = ["ecology"]
            payload["title"] = "Analyze ecosystem flux"
            payload["intents"] = ["ecosystem flux", "生态系统通量"]
            payload["questions"] = ["How does ecosystem flux change?"]
            write_manifest(root, payload)

            plan = route("分析生态系统通量", registry=ModuleRegistry.discover(root))

        self.assertEqual(plan["matched_workflows"], ["ecology"])
        self.assertEqual(plan["steps"][0]["candidates"][0]["id"], "ecology-flux")

    def test_domain_concept_remains_routable_as_modules_expand(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, suffix in enumerate(("quality control", "batch integration", "donor inference")):
                payload = valid_manifest_payload()
                payload["id"] = f"single-cell-{index}"
                payload["domains"] = ["omics"]
                payload["title"] = f"Single-cell {suffix}"
                payload["intents"] = [f"single-cell {suffix}", f"单细胞{index}流程"]
                write_manifest(root, payload)
            for identifier, domain, intent in (
                ("image-segment", "imaging", "图像分割"),
                ("paper-write", "publication", "写论文"),
            ):
                payload = valid_manifest_payload()
                payload["id"] = identifier
                payload["domains"] = [domain]
                payload["title"] = intent
                payload["intents"] = [intent]
                write_manifest(root, payload)

            plan = route(
                "并行做单细胞和图像分割，最后写论文",
                registry=ModuleRegistry.discover(root),
            )

        self.assertEqual(plan["matched_workflows"], ["omics", "imaging", "publication"])

    def test_exact_manifest_intent_suppresses_incidental_fuzzy_workflows(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            exact = valid_manifest_payload()
            exact["id"] = "contract-audit"
            exact["domains"] = ["evidence"]
            exact["title"] = "Audit research contracts"
            exact["intents"] = ["检查科研项目多份产物的一致性"]
            write_manifest(root, exact)
            fuzzy = valid_manifest_payload()
            fuzzy["id"] = "generic-data-check"
            fuzzy["domains"] = ["omics"]
            fuzzy["title"] = "Check scientific data"
            fuzzy["intents"] = ["检查科研数据"]
            write_manifest(root, fuzzy)

            plan = route("请检查科研项目多份产物的一致性", registry=ModuleRegistry.discover(root))

        self.assertEqual(plan["matched_workflows"], ["evidence"])
        self.assertEqual(plan["steps"][0]["candidates"][0]["id"], "contract-audit")

    def test_multi_domain_module_is_scheduled_once_without_a_central_special_case(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shared = valid_manifest_payload()
            shared["id"] = "shared-visual"
            shared["domains"] = ["imaging", "publication"]
            shared["title"] = "Create shared visual"
            shared["intents"] = ["create shared visual"]
            shared["questions"] = ["What shared visual should be created?"]
            write_manifest(root, shared)
            for identifier, domain in (("image-check", "imaging"), ("publication-check", "publication")):
                payload = valid_manifest_payload()
                payload["id"] = identifier
                payload["domains"] = [domain]
                payload["title"] = identifier.replace("-", " ")
                payload["intents"] = [identifier.replace("-", " ")]
                write_manifest(root, payload)

            plan = route("create shared visual for publication", registry=ModuleRegistry.discover(root))

        routed = [item["id"] for step in plan["steps"] for item in step["candidates"]]
        self.assertEqual(routed.count("shared-visual"), 1)
        self.assertIn("publication-check", routed)

    def test_artifact_contract_turns_independent_selection_into_serial_plan(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            producer = valid_manifest_payload()
            producer["id"] = "neo-assay-preparation"
            producer["domains"] = ["evidence"]
            producer["title"] = "Prepare neo assay"
            producer["intents"] = ["prepare neo assay"]
            producer["output_artifacts"][0]["artifact_type"] = "neo_assay_result"
            write_manifest(root, producer)

            consumer = valid_manifest_payload()
            consumer["id"] = "neo-conclusion-review"
            consumer["domains"] = ["evidence"]
            consumer["title"] = "Review neo conclusion"
            consumer["intents"] = ["review neo conclusion"]
            consumer["input_artifacts"][0]["artifact_type"] = "neo_assay_result"
            write_manifest(root, consumer)

            plan = route(
                "prepare neo assay and review neo conclusion",
                registry=ModuleRegistry.discover(root),
            )

        self.assertEqual(plan["selected_module_ids"], ["neo-assay-preparation", "neo-conclusion-review"])
        self.assertEqual(plan["plan_type"], "serial")
        self.assertEqual(plan["steps"][0]["mode"], "serial")


if __name__ == "__main__":
    unittest.main()
