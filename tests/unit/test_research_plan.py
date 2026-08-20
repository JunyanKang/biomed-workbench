import unittest

from biomed_workbench.research_plan import compile_research_plan


SINGLE_CELL_P1_MODULES = {
    "single-cell-atac-regulatory",
    "single-cell-atlas-annotation",
    "single-cell-batch-integration",
    "single-cell-communication",
    "single-cell-complex-inference",
    "single-cell-donor-inference",
    "single-cell-doublet-detection",
    "single-cell-droplet-decontamination",
    "single-cell-fate-mapping",
    "single-cell-marker-discovery",
    "single-cell-multimodal-integration",
    "single-cell-qc",
    "single-cell-reference-annotation",
    "single-cell-regulatory-network",
    "single-cell-regulatory-velocity",
    "single-cell-spatial-analysis",
    "single-cell-trajectory-topology",
    "single-cell-trajectory-velocity",
}


class ResearchPlanTests(unittest.TestCase):
    def test_plan_exposes_contracts_without_claiming_execution(self):
        plan = compile_research_plan("Import FCS flow cytometry data and apply a gating plan")

        self.assertEqual(plan["selected_module_ids"], ["fcs-event-import", "flow-cytometry-summary"])
        self.assertIn("not an execution record", plan["execution_boundary"])
        importer = next(item for item in plan["modules"] if item["id"] == "fcs-event-import")
        downstream = next(item for item in plan["modules"] if item["id"] == "flow-cytometry-summary")
        self.assertEqual(importer["project_inputs"][0]["artifact_type"], "flow_cytometry_acquisition")
        self.assertEqual(importer["execution"]["kind"], "python")
        self.assertIn("fcs_path", importer["input_schema"]["properties"])
        self.assertEqual(importer["execution_templates"][0]["path"], "templates/run_fcs_event_import.py")
        self.assertEqual(downstream["upstream_inputs"][0]["artifact_type"], "cytometry_event_table")
        self.assertEqual(downstream["depends_on"], ["fcs-event-import"])
        self.assertNotIn("NCBI_API_KEY", str(plan))

    def test_selected_producer_satisfies_a_project_or_upstream_interval_port(self):
        plan = compile_research_plan("将一组 hg19 BED 峰坐标转换到 hg38，保留无法映射的区域并检查后续 ATAC 区间重叠")

        overlap = next(item for item in plan["modules"] if item["id"] == "interval-overlap-bedtools")
        query = next(item for item in overlap["upstream_inputs"] if item["name"] == "query_intervals")
        self.assertEqual(query["selected_upstream_module_id"], "genome-coordinate-liftover")
        self.assertNotIn("query_intervals", {item["name"] for item in plan["unresolved_project_inputs"] if item["module_id"] == "interval-overlap-bedtools"})
        self.assertNotIn("query_intervals", {item["name"] for item in plan["unresolved_required_inputs"] if item["module_id"] == "interval-overlap-bedtools"})

    def test_immunophenotype_plan_binds_event_and_gate_producers(self):
        plan = compile_research_plan("quantify flow cytometry immunophenotype")

        module = next(item for item in plan["modules"] if item["id"] == "flow-immunophenotype-summary")
        bindings = {item["name"]: item["selected_upstream_module_id"] for item in module["upstream_inputs"]}
        self.assertEqual(bindings, {"events": "fcs-event-import", "gates": "flow-cytometry-summary"})

    def test_dense_single_cell_program_is_a_staged_evidence_bound_research_plan(self):
        plan = compile_research_plan(
            "读取 h5ad 10x HDF5 Matrix Market 和 Seurat 对象，完成空滴 ambient RNA doublet "
            "QC normalization HVG scaling PCA 邻居图 UMAP tSNE Leiden Louvain Scanpy Seurat "
            "pseudobulk donor-aware mixed model scVI scANVI Harmony Scanorama BBKNN CellTypist "
            "Azimuth popV Cell Ontology marker discovery 未知细胞类型保留 trajectory pseudotime "
            "RNA velocity fate mapping CellChat NicheNet LIANA CellPhoneDB SCENIC SCENIC+ RegVelo "
            "RNA+ATAC CITE-seq WNN MOFA peak calling motif peak-to-gene chromVAR spatial transcriptomics "
            "hypothesis revision manuscript delivery"
        )

        self.assertTrue(SINGLE_CELL_P1_MODULES <= set(plan["selected_module_ids"]))
        self.assertEqual(len(plan["execution_layers"]), 2)
        self.assertTrue(SINGLE_CELL_P1_MODULES <= set(plan["execution_layers"][0]["module_ids"]))
        self.assertTrue(
            {"trajectory-spatial-figure-package", "manuscript-revision-base"}
            <= set(plan["execution_layers"][1]["module_ids"])
        )
        self.assertNotIn("response-matrix", plan["selected_module_ids"])

        modules = {item["id"]: item for item in plan["modules"]}
        for module_id in SINGLE_CELL_P1_MODULES:
            module = modules[module_id]
            self.assertTrue(module["compatibility_row_ids"], module_id)
            self.assertTrue(module["quality_gate_ids"], module_id)
            self.assertTrue(module["execution_templates"], module_id)
            self.assertEqual(module["evidence_contract"]["module_version"], module["version"])
            self.assertEqual(module["evidence_contract"]["compatibility_row_ids"], module["compatibility_row_ids"])

    def test_publication_program_is_staged_from_figures_to_response_and_delivery(self):
        plan = compile_research_plan(
            "audit manuscript claims figures methods citations reviewer concerns response matrix "
            "patent readiness presentation delivery from analysis evidence"
        )

        modules = {item["id"]: item for item in plan["modules"]}
        self.assertEqual(plan["plan_type"], "parallel")
        self.assertEqual(len(plan["execution_layers"]), 1)
        self.assertTrue(
            {"figure-specification", "manuscript-audit", "citation-audit", "reviewer-assessment", "response-matrix", "patent-draft-readiness-audit", "presentation-delivery-plan"}
            <= set(plan["execution_layers"][0]["module_ids"])
        )
        for module_id in ("manuscript-audit", "citation-audit", "reviewer-assessment", "response-matrix"):
            self.assertTrue(modules[module_id]["compatibility_row_ids"], module_id)
            self.assertTrue(modules[module_id]["quality_gate_ids"], module_id)

    def test_database_evidence_program_separates_identity_records_and_audits(self):
        plan = compile_research_plan(
            "Resolve TP53 identifiers across UniProt Ensembl dbSNP gnomAD HPO GO Reactome "
            "cBioPortal Crossref Europe PMC and prepare evidence synthesis with freshness and citation checks",
            per_workflow=10,
        )

        modules = {item["id"]: item for item in plan["modules"]}
        self.assertEqual(plan["plan_type"], "mixed")
        self.assertIn("citation-record-resolution", plan["execution_layers"][0]["module_ids"])
        self.assertTrue(
            {"dbsnp-rsid-evidence", "gnomad-gene-constraint-evidence", "hpo-term-evidence", "quickgo-term-evidence", "reactome-pathway-evidence"}
            <= set(plan["execution_layers"][0]["module_ids"])
        )
        self.assertIn("source-freshness-audit", modules)
        self.assertIn("citation-record-resolution", modules["citation-audit"]["depends_on"])
        for module_id in ("citation-record-resolution", "dbsnp-rsid-evidence", "gnomad-gene-constraint-evidence", "source-freshness-audit"):
            self.assertTrue(modules[module_id]["compatibility_row_ids"], module_id)

    def test_molecular_design_program_orders_primer_selection_before_specificity_and_amplicons(self):
        plan = compile_research_plan(
            "design PCR primers then select the primer pair screen primer specificity and simulate PCR amplicons"
        )

        modules = {item["id"]: item for item in plan["modules"]}
        self.assertEqual(plan["plan_type"], "serial")
        self.assertEqual(plan["execution_layers"][0]["module_ids"], ["pcr-primer-pair-selection"])
        self.assertEqual(plan["execution_layers"][1]["module_ids"], ["primer-pair-specificity-screen"])
        self.assertEqual(plan["execution_layers"][2]["module_ids"], ["pcr-amplicon-simulation"])
        self.assertIn("pcr-primer-pair-selection", modules["primer-pair-specificity-screen"]["depends_on"])
        self.assertIn("pcr-primer-pair-selection", modules["pcr-amplicon-simulation"]["depends_on"])
        for module_id in ("pcr-primer-pair-selection", "primer-pair-specificity-screen", "pcr-amplicon-simulation"):
            self.assertTrue(modules[module_id]["execution_templates"], module_id)
            self.assertTrue(modules[module_id]["quality_gate_ids"], module_id)

    def test_omics_and_statistics_program_orders_qc_before_inference_and_secondary_synthesis(self):
        plan = compile_research_plan("run expression QC differential expression enrichment NMF and network analysis")

        modules = {item["id"]: item for item in plan["modules"]}
        self.assertEqual(plan["plan_type"], "parallel")
        self.assertTrue({"expression-qc", "differential-expression", "network-analysis"} <= set(plan["execution_layers"][0]["module_ids"]))
        self.assertEqual(modules["differential-expression"]["depends_on"], [])
        self.assertEqual(modules["network-analysis"]["depends_on"], [])
        for module_id in ("expression-qc", "differential-expression", "network-analysis"):
            self.assertTrue(modules[module_id]["execution_templates"], module_id)
            self.assertTrue(modules[module_id]["quality_gate_ids"], module_id)


if __name__ == "__main__":
    unittest.main()
