import re
import subprocess
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
POLICY_BASELINE = "922c6e9571cdb56d4433d0f9c051b31d87020f2c"
NOTE_PATTERN = re.compile(r"^docs/releases/(\d{4}-\d{2}-\d{2})(\.zh-CN)?\.md$")


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=check,
        capture_output=True,
        text=True,
    )


class ReleaseNoteHistoryTests(unittest.TestCase):
    def test_release_index_states_the_editorial_correction_policy(self):
        english = (ROOT / "docs/releases/README.md").read_text(encoding="utf-8")
        chinese = (ROOT / "docs/releases/README.zh-CN.md").read_text(encoding="utf-8")

        self.assertIn("Scientific behavior and evidence are not silently rewritten", english)
        self.assertIn("editorial corrections to public wording are dated", english)
        self.assertIn("科学行为和证据不会被静默改写", chinese)
        self.assertIn("公开措辞的编辑性修订", chinese)

    def test_historical_notes_changed_after_policy_disclose_the_latest_correction(self):
        baseline = _git("cat-file", "-e", f"{POLICY_BASELINE}^{{commit}}", check=False)
        self.assertEqual(
            baseline.returncode,
            0,
            "the policy baseline is unavailable; CI must check out complete Git history",
        )

        changed = set(
            filter(
                None,
                _git("diff", "--name-only", f"{POLICY_BASELINE}..HEAD", "--", "docs/releases").stdout.splitlines(),
            )
        )
        working_tree_changes = set(
            filter(None, _git("diff", "--name-only", "--", "docs/releases").stdout.splitlines())
        )
        changed.update(working_tree_changes)

        for relative_path in sorted(changed):
            match = NOTE_PATTERN.match(relative_path)
            if match is None:
                continue
            snapshot_date = date.fromisoformat(match.group(1))
            if relative_path in working_tree_changes:
                correction_date = date.today()
            else:
                correction_date = date.fromisoformat(
                    _git("log", "-1", "--format=%cs", "--", relative_path).stdout.strip()
                )
            if correction_date <= snapshot_date:
                continue

            text = (ROOT / relative_path).read_text(encoding="utf-8")
            if match.group(2):
                self.assertIn("## 编辑性修订", text, relative_path)
                self.assertIn(f"- {correction_date.isoformat()}：", text, relative_path)
            else:
                self.assertIn("## Editorial correction", text, relative_path)
                self.assertIn(f"- {correction_date.isoformat()}:", text, relative_path)


if __name__ == "__main__":
    unittest.main()
