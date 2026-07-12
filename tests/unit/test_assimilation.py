import json
import os
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.assimilation import (
    IncompleteAssimilationError,
    assimilate_source,
    load_private_manifest,
    public_summary,
    read_record,
    verify_complete,
    verify_manifest,
    write_private_manifest,
)


class AssimilationTests(unittest.TestCase):
    def test_manifest_requires_exact_inventory_equality(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
            (root / "b.md").write_text("# B\n", encoding="utf-8")

            records = [read_record(root / "a.py", root, "fixture")]

            with self.assertRaises(IncompleteAssimilationError):
                verify_complete(root, records, "fixture")

    def test_sensitive_text_is_redacted_but_counted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secret = root / ".env"
            secret.write_text("API_KEY=secret-value\n", encoding="utf-8")

            record = read_record(secret, root, "fixture")
            serialized = json.dumps(record.to_dict())

            self.assertEqual(record.disposition, "sensitive")
            self.assertEqual(record.size, len(b"API_KEY=secret-value\n"))
            self.assertNotIn("secret-value", serialized)

    def test_environment_variable_usage_is_understood_not_hidden(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module = root / "client.py"
            module.write_text(
                "import os\nAPI_KEY = os.environ.get('SERVICE_API_KEY')\n",
                encoding="utf-8",
            )

            record = read_record(module, root, "fixture")

            self.assertEqual(record.disposition, "merge")
            self.assertEqual(record.semantic["imports"], ["os"])

    def test_token_named_source_file_is_not_treated_as_a_credential(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module = root / "token.py"
            module.write_text("def tokenize(text):\n    return text.split()\n", encoding="utf-8")

            record = read_record(module, root, "fixture")

            self.assertEqual(record.disposition, "merge")
            self.assertEqual(record.semantic["public_symbols"], ["tokenize"])

    def test_every_record_has_capability_and_understanding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "literature_search.py").write_text(
                "def search_pubmed(query):\n    return query\n",
                encoding="utf-8",
            )

            record = read_record(root / "literature_search.py", root, "fixture")

            self.assertEqual(record.capability_cluster, "evidence_discovery")
            self.assertEqual(record.understanding["role"], "executable_logic")
            self.assertEqual(record.understanding["public_symbol_count"], 1)

    def test_generated_runtime_keeps_per_file_package_group(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "conda" / "pkgs" / "numpy-2.0" / "metadata.json"
            package.parent.mkdir(parents=True)
            package.write_text('{"name": "numpy"}\n', encoding="utf-8")

            record = read_record(package, root, "fixture")

            self.assertEqual(record.disposition, "generated_runtime")
            self.assertEqual(record.capability_cluster, "generated_runtime")
            self.assertEqual(record.understanding["runtime_group"], "pkgs:numpy-2.0")

    def test_model_provider_code_is_marked_for_codex_native_rewrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = root / "src" / "provider" / "anthropic.ts"
            provider.parent.mkdir(parents=True)
            provider.write_text("export function complete() { return null }\n", encoding="utf-8")

            record = read_record(provider, root, "fixture")

            self.assertEqual(record.disposition, "rewrite")
            self.assertEqual(record.capability_cluster, "codex_native_orchestration")

    def test_known_live_token_shape_is_redacted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "settings.txt"
            token = "nv" + "api-" + "abcdefghijklmnopqrstuvwxyz123456"
            config.write_text(f"TOKEN={token}\n", encoding="utf-8")

            record = read_record(config, root, "fixture")

            self.assertEqual(record.disposition, "sensitive")
            self.assertNotIn("nvapi-", json.dumps(record.to_dict()))

    def test_python_record_extracts_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module = root / "analysis.py"
            module.write_text(
                '"""Analyze a cohort."""\n'
                "import csv\n\n"
                "def summarize(values):\n"
                "    return sum(values)\n",
                encoding="utf-8",
            )

            record = read_record(module, root, "fixture")

            self.assertEqual(record.format, "python")
            self.assertEqual(record.semantic["module_doc"], "Analyze a cohort.")
            self.assertEqual(record.semantic["public_symbols"], ["summarize"])
            self.assertEqual(record.semantic["imports"], ["csv"])

    def test_assimilation_is_deterministic_and_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.md").write_text("# Aim\nTest a hypothesis.\n", encoding="utf-8")
            (root / "data.json").write_text('{"species": "human"}\n', encoding="utf-8")
            os.symlink("notes.md", root / "latest")

            first = assimilate_source(root, "fixture")
            second = assimilate_source(root, "fixture")

            self.assertEqual(first.summary.root_digest, second.summary.root_digest)
            self.assertEqual(first.summary.file_count, 3)
            self.assertEqual(first.summary.unreadable_count, 0)
            verify_complete(root, first.records, "fixture")

    def test_private_manifest_round_trip_and_public_summary_privacy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "private-source-name"
            root.mkdir()
            (root / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
            result = assimilate_source(root, "primary-a")
            manifest = Path(directory) / "manifest.jsonl"

            write_private_manifest(manifest, {"primary-a": root}, [result])
            roots, records = load_private_manifest(manifest)
            summaries = verify_manifest(manifest)
            tracked = json.dumps(public_summary([result]))

            self.assertEqual(roots["primary-a"], root.resolve())
            self.assertEqual(records, result.records)
            self.assertEqual(summaries[0].root_digest, result.summary.root_digest)
            self.assertNotIn(str(root), tracked)
            self.assertNotIn("module.py", tracked)


if __name__ == "__main__":
    unittest.main()
