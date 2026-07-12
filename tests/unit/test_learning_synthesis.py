import unittest

from biomed_workbench.assimilation import FileRecord
from biomed_workbench.learning_synthesis import synthesize_learning


def record(path, cluster, role, semantic):
    return FileRecord(
        source="fixture",
        path=path,
        kind="file",
        size=10,
        sha256="a" * 64,
        format="python",
        media_type="text/x-python",
        disposition="merge",
        capability_cluster=cluster,
        understanding={"role": role, "purpose": "Purpose", "public_symbol_count": len(semantic.get("public_symbols", ()))},
        semantic=semantic,
    )


class LearningSynthesisTests(unittest.TestCase):
    def test_synthesis_combines_every_record_into_domain_signals(self):
        records = [
            record("a.py", "omics", "executable_logic", {"imports": ["pandas", "numpy"], "public_symbols": ["normalize_counts"]}),
            record("b.py", "omics", "verification", {"imports": ["pandas"], "public_symbols": ["test_normalization"]}),
            record("c.md", "publication", "assistant_workflow", {"headings": [{"level": 2, "text": "Citation verification"}]}),
        ]

        summary = synthesize_learning(records)

        self.assertEqual(summary["learned_file_count"], 3)
        self.assertEqual(summary["clusters"]["omics"]["file_count"], 2)
        self.assertEqual(summary["clusters"]["omics"]["top_dependencies"][0], ["pandas", 2])
        self.assertIn(["normalize counts", 1], summary["clusters"]["omics"]["operation_signals"])
        self.assertEqual(sum(cluster["file_count"] for cluster in summary["clusters"].values()), 3)


if __name__ == "__main__":
    unittest.main()
