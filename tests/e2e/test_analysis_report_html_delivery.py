import tempfile
import unittest
from pathlib import Path

from biomed_workbench.reporting.analysis_html import assert_primary_html_delivery
from biomed_workbench.router import route
from biomed_workbench.runner import run


class AnalysisReportHTMLDeliveryTests(unittest.TestCase):
    def _report(self, source: Path) -> dict[str, object]:
        return {
            "project": "controlled-project",
            "biological_question": "Does the measured state differ between conditions?",
            "scientific_results": [{
                "label": "Cell-state abundance",
                "progress": "SCIENTIFICALLY_REVIEWED",
                "observation_en": "The measured cell-state fraction was lower in the perturbed group.",
                "interpretation_en": "The observation is consistent with a change in state abundance but does not establish tissue loss.",
                "experimental_unit": "embryo",
                "evidence_boundary_en": ["The controlled fixture does not establish a biological mechanism."],
                "next_decision": "retain-with-limit",
            }],
            "evidence_links": [{"label": "Source data", "path": source.as_posix()}],
        }

    def test_registered_delivery_uses_reopened_html_as_primary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.tsv"
            source.write_text("group\tfraction\ncontrol\t0.4\nmutant\t0.3\n", encoding="utf-8")
            execution = run(
                "scientific-analysis-report-delivery",
                {"report": self._report(source), "output_directory": (root / "report").as_posix()},
                allow_mutation=True,
            ).to_dict()
            output = execution["output"]
            files = output["report_files"]
            self.assertEqual(output["primary_delivery_format"], "html")
            self.assertTrue(output["markdown_is_companion_only"])
            self.assertEqual(files["primary"], files["html"])
            self.assertTrue(files["delivery_verified"])
            html = Path(files["html"]).read_text(encoding="utf-8")
            self.assertIn('<nav>', html)
            self.assertIn('id="result-1"', html)
            self.assertIn('id="sources"', html)
            self.assertIn("source.tsv", html)

    def test_markdown_only_delivery_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            markdown = Path(temporary) / "analysis-report.md"
            markdown.write_text("# Analysis report\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "requires HTML as the primary"):
                assert_primary_html_delivery({
                    "primary": markdown.as_posix(), "primary_format": "markdown", "html": None,
                    "delivery_verified": True,
                })

    def test_unreviewed_result_cannot_be_delivered(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.tsv"
            source.write_text("x\ty\n1\t2\n", encoding="utf-8")
            report = self._report(source)
            report["scientific_results"][0]["progress"] = "RELOADED"
            with self.assertRaisesRegex(Exception, "failed with ValueError"):
                run(
                    "scientific-analysis-report-delivery",
                    {"report": report, "output_directory": (root / "report").as_posix()},
                    allow_mutation=True,
                )

    def test_common_analysis_report_requests_route_to_html_delivery(self):
        queries = (
            "对当前项目的分析结果进行科学解读并生成分析报告",
            "读取这些单细胞分析结果，生成完整项目报告",
            "完成数据分析并交付报告",
            "把已有分析结果整理成可阅读的报告",
        )
        for query in queries:
            with self.subTest(query=query):
                self.assertIn("scientific-analysis-report-delivery", route(query, per_workflow=6)["selected_module_ids"])

    def test_tool_native_qc_report_does_not_route_to_project_report_delivery(self):
        selected = route("生成FastQC质控报告", per_workflow=6)["selected_module_ids"]
        self.assertIn("read-quality-fastqc", selected)
        self.assertNotIn("scientific-analysis-report-delivery", selected)


if __name__ == "__main__":
    unittest.main()
