import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


def _builder_module():
    path = Path(__file__).parents[2] / "tools" / "build_journal_standards.py"
    spec = importlib.util.spec_from_file_location("journal_catalog_builder", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class JournalCatalogLifecycleTests(unittest.TestCase):
    def test_draft_can_change_but_released_and_historical_versions_are_immutable(self):
        builder = _builder_module()
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        snapshot = root / "v2026.08.03.json"
        index = root / "index.json"
        snapshot.write_text("old\n", encoding="utf-8")
        index.write_text(json.dumps({
            "active_catalog_version": "2026.08.03",
            "catalog_lifecycle": "draft",
        }), encoding="utf-8")
        builder._assert_snapshot_write_allowed(
            snapshot, index, "new\n", version="2026.08.03", lifecycle="draft"
        )

        index.write_text(json.dumps({
            "active_catalog_version": "2026.08.03",
            "catalog_lifecycle": "released",
        }), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "immutable"):
            builder._assert_snapshot_write_allowed(
                snapshot, index, "new\n", version="2026.08.03", lifecycle="released"
            )
        with self.assertRaisesRegex(RuntimeError, "cannot be downgraded"):
            builder._assert_snapshot_write_allowed(
                snapshot, index, "old\n", version="2026.08.03", lifecycle="draft"
            )

        index.write_text(json.dumps({
            "active_catalog_version": "2026.08.04",
            "catalog_lifecycle": "draft",
        }), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "historical"):
            builder._assert_snapshot_write_allowed(
                snapshot, index, "new\n", version="2026.08.03", lifecycle="draft"
            )


if __name__ == "__main__":
    unittest.main()
