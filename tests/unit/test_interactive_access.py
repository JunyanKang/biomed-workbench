import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from biomed_workbench.services.interactive_access import (
    ALPHAFOLD_SERVER,
    configure_interactive_access,
    interactive_access_status,
    interactive_access_store_path,
    mark_interactive_access,
    remove_interactive_access,
)


class InteractiveAccessPolicyTests(unittest.TestCase):
    def test_alphafold_server_status_is_private_and_secret_free(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(os.environ, {"BIOMED_WORKBENCH_CONFIG_HOME": temporary}):
                configure_interactive_access(
                    ALPHAFOLD_SERVER,
                    account="scientist@example.org",
                    terms_reviewed=True,
                )
                path = interactive_access_store_path()
                status = interactive_access_status()
                stored = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(status["state"], "ready")
                self.assertEqual(status["account_hint"], "s********@example.org")
                self.assertFalse(status["password_stored"])
                self.assertFalse(status["token_stored"])
                self.assertNotIn("password", json.dumps(stored).lower())
                self.assertNotIn("token", json.dumps(stored).lower())
                if os.name != "nt":
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_problem_state_and_removal_are_explicit(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(os.environ, {"BIOMED_WORKBENCH_CONFIG_HOME": temporary}):
                configure_interactive_access(
                    ALPHAFOLD_SERVER,
                    account="scientist@example.org",
                    terms_reviewed=True,
                )
                mark_interactive_access(ALPHAFOLD_SERVER, "authentication-error")
                self.assertEqual(interactive_access_status()["state"], "authentication-error")
                self.assertTrue(remove_interactive_access(ALPHAFOLD_SERVER))
                self.assertEqual(interactive_access_status()["state"], "not-configured")

    def test_ready_requires_terms_and_secret_fields_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(os.environ, {"BIOMED_WORKBENCH_CONFIG_HOME": temporary}):
                with self.assertRaisesRegex(ValueError, "terms"):
                    configure_interactive_access(
                        ALPHAFOLD_SERVER,
                        account="scientist@example.org",
                        terms_reviewed=False,
                    )
                path = Path(temporary) / "interactive-access.json"
                path.write_text(
                    json.dumps({ALPHAFOLD_SERVER: {"state": "ready", "password": "private"}}),
                    encoding="utf-8",
                )
                path.chmod(0o600)
                with self.assertRaisesRegex(ValueError, "secrets"):
                    interactive_access_status()

                path.write_text(
                    json.dumps({ALPHAFOLD_SERVER: {"state": "ready", "google_password": "private"}}),
                    encoding="utf-8",
                )
                path.chmod(0o600)
                with self.assertRaisesRegex(ValueError, "secrets"):
                    interactive_access_status()


if __name__ == "__main__":
    unittest.main()
