import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("route_task", ROOT / "tools" / "route_task.py")
ROUTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ROUTER)
ENTRIES = ROUTER.load_catalog()["entries"]


def route(query, limit=12):
    workflows = ROUTER.infer_workflows(query, [])
    candidates = ROUTER.score_entries(ENTRIES, query, workflows, limit)
    plan_type = ROUTER.plan_type_for(query, workflows, candidates)
    return workflows, candidates, ROUTER.build_steps(query, workflows, candidates, plan_type), plan_type


def ids_for(candidates, workflow):
    return [item["id"] for item in candidates if item["workflow"] == workflow]


class RoutingTests(unittest.TestCase):
    def test_review_and_citation_intents_rank_the_matching_workflows(self):
        workflows, candidates, _, _ = route("review this manuscript and verify every citation")

        self.assertEqual(workflows, ["publication"])
        self.assertEqual(ids_for(candidates, "publication")[:2], [
            "publication_reviewer",
            "publication_ref_verifier",
        ])
        self.assertNotIn("publication_paper_to_patent", ids_for(candidates, "publication")[:4])

    def test_crispr_pipeline_keeps_evidence_design_and_writing_relevant(self):
        query = "分析TP53在肺癌中的证据并设计CRISPR验证，最后写成Nature风格结果"
        workflows, candidates, steps, plan_type = route(query)

        self.assertEqual(plan_type, "serial")
        self.assertEqual([step["workflow"] for step in steps], [
            "evidence",
            "molecular_design",
            "publication",
        ])
        self.assertEqual(ids_for(candidates, "evidence")[0], "search_pubmed")
        self.assertEqual(ids_for(candidates, "molecular_design")[0], "design_crispr")
        self.assertIn("publication_writing", ids_for(candidates, "publication")[:3])

    def test_mixed_runtime_parallel_analysis_and_publication_plan(self):
        query = "检查环境然后并行分析RNA-seq和显微图像，最后整合成论文图表"
        _, candidates, steps, plan_type = route(query)

        self.assertEqual(plan_type, "mixed")
        self.assertEqual([(step["workflow"], step["mode"]) for step in steps], [
            ("runtime", "serial"),
            ("omics", "parallel"),
            ("imaging", "parallel"),
            ("publication", "serial"),
        ])
        self.assertEqual(ids_for(candidates, "omics")[0], "run_deseq2_analysis")
        self.assertNotIn("analyze_western_blot", ids_for(candidates, "omics")[:3])
        self.assertNotIn("analyze_immunohistochemistry_image", ids_for(candidates, "omics")[:3])
        self.assertNotIn("count_colonies", [candidate["id"] for candidate in candidates])

    def test_elisa_protocol_prefers_protocol_discovery_over_data_analysis(self):
        _, candidates, _, _ = route("帮我做一份ELISA实验方案")

        wetlab_ids = ids_for(candidates, "wetlab")
        self.assertEqual(wetlab_ids[0], "search_protocols")
        self.assertEqual(wetlab_ids[1], "get_protocol_details")
        self.assertNotIn("process_elisa", wetlab_ids[:3])

    def test_candidate_descriptions_are_human_readable(self):
        _, candidates, _, _ = route("分析显微图像中的细胞形态")

        for candidate in candidates:
            self.assertNotRegex(candidate["description"], r"\b(import argparse|def [a-z_]+\()")


if __name__ == "__main__":
    unittest.main()
