import json
import unittest

from biomed_workbench.models import EvidenceItem, ExecutionResult
from biomed_workbench.research import ResearchAction, ResearchRecord, StageRecord


class ResearchRecordTests(unittest.TestCase):
    def test_record_serialization_redacts_secret_inputs(self):
        record = ResearchRecord(
            objective="Assess TP53 evidence",
            inputs={"NCBI_API_KEY": "private", "gene": "TP53"},
            plan=(ResearchAction("ncbi-search", {"database": "gene", "term": "TP53"}, "Find gene records"),),
            stages=(StageRecord("frame", "completed", "Objective is explicit"),),
            executions=(ExecutionResult("ncbi-search", "completed", {"count": 1}),),
            evidence=(EvidenceItem("7157", "NCBI Gene", "TP53 record"),),
            conclusions=("One gene record was identified.",),
            limitations=(),
            next_decisions=(),
            summary="Evidence retrieval completed.",
        )
        serialized = json.dumps(record.to_dict())

        self.assertNotIn("private", serialized)
        self.assertIn("[REDACTED]", serialized)

    def test_all_research_lifecycle_states_are_validated(self):
        names = ("frame", "plan", "investigate", "design", "interpret", "deliver", "audit")
        for name in names:
            self.assertEqual(StageRecord(name, "completed", "done").name, name)
        with self.assertRaises(ValueError):
            StageRecord("invent", "completed", "bad")


if __name__ == "__main__":
    unittest.main()
