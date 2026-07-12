import unittest

from biomed_workbench.assistant import ResearchAssistant
from biomed_workbench.models import ExecutionResult
from biomed_workbench.research import ResearchAction


class AssistantTests(unittest.TestCase):
    def test_assistant_finishes_with_scientific_output_not_tool_ids(self):
        def executor(capability_id, inputs, allow_mutation=False):
            self.assertEqual(capability_id, "ncbi-search-summary")
            return ExecutionResult(
                capability_id=capability_id,
                status="completed",
                output={
                    "search": {"database": "gene", "count": 1, "ids": ["7157"]},
                    "summary": {"database": "gene", "records": [{"uid": "7157", "name": "TP53", "description": "tumor protein p53"}]},
                },
            )

        assistant = ResearchAssistant(executor=executor)
        result = assistant.run(
            "Assess TP53 evidence and propose validation",
            actions=(
                ResearchAction(
                    "ncbi-search-summary",
                    {"database": "gene", "term": "TP53[Gene Name] AND human[Organism]", "retmax": 1},
                    "Ground the target identity",
                ),
            ),
            require_design=True,
        )

        self.assertTrue(result.summary)
        self.assertTrue(result.evidence)
        self.assertNotIn("tool_ids", result.user_output)
        self.assertIn("TP53", result.user_output)
        self.assertEqual(tuple(stage.name for stage in result.record.stages), ("frame", "plan", "investigate", "design", "interpret", "deliver", "audit"))

    def test_assistant_records_why_optional_design_is_skipped(self):
        result = ResearchAssistant(executor=lambda *_args, **_kwargs: None).run("Summarize an existing record")
        design = next(stage for stage in result.record.stages if stage.name == "design")

        self.assertEqual(design.status, "skipped")
        self.assertTrue(design.rationale)


if __name__ == "__main__":
    unittest.main()
