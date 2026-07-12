import unittest

from biomed_workbench.assimilation import FileRecord
from biomed_workbench.design_ledger import build_design_record, summarize_design, verify_design_complete


def record(path, *, role, cluster, disposition="merge", purpose="A concrete scientific purpose."):
    return FileRecord(
        source="fixture",
        path=path,
        kind="file",
        size=10,
        sha256="a" * 64,
        format="python",
        media_type="text/x-python",
        disposition=disposition,
        capability_cluster=cluster,
        understanding={"role": role, "purpose": purpose, "public_symbol_count": 1, "dependency_count": 2},
        semantic={},
    )


class DesignLedgerTests(unittest.TestCase):
    def test_scientific_code_is_redesigned_not_copied(self):
        design = build_design_record(record("tool/genomics.py", role="executable_logic", cluster="omics"))

        self.assertEqual(design.action, "rewrite_capability")
        self.assertEqual(design.target, "biomed_workbench/capabilities/omics.py")
        self.assertEqual(design.reuse_mode, "concept_only")
        self.assertNotIn("copy", design.rationale.lower())

    def test_skills_are_rewritten_behind_one_codex_entrypoint(self):
        design = build_design_record(record("skills/reviewer/SKILL.md", role="assistant_workflow", cluster="publication"))

        self.assertEqual(design.action, "rewrite_workflow")
        self.assertEqual(design.target, "skills/biomed-workbench/SKILL.md")
        self.assertEqual(design.reuse_mode, "concept_only")

    def test_generated_and_sensitive_files_are_understood_but_not_reimplemented(self):
        generated = build_design_record(
            record("conda/pkgs/library.so", role="generated_runtime_artifact", cluster="generated_runtime", disposition="generated_runtime")
        )
        sensitive = build_design_record(
            record("credentials.json", role="redacted_configuration", cluster="sensitive_configuration", disposition="sensitive")
        )

        self.assertEqual(generated.action, "exclude_generated")
        self.assertEqual(sensitive.action, "exclude_sensitive")
        self.assertEqual(generated.reuse_mode, "none")
        self.assertEqual(sensitive.reuse_mode, "none")

    def test_ledger_requires_exact_one_to_one_file_coverage(self):
        records = [
            record("a.py", role="executable_logic", cluster="omics"),
            record("b.md", role="assistant_workflow", cluster="publication"),
        ]
        designs = [build_design_record(records[0])]

        with self.assertRaises(ValueError):
            verify_design_complete(records, designs)

        designs.append(build_design_record(records[1]))
        verify_design_complete(records, designs)
        summary = summarize_design(designs)
        self.assertEqual(summary["learned_file_count"], 2)
        self.assertEqual(sum(summary["action_counts"].values()), 2)


if __name__ == "__main__":
    unittest.main()
