import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from biomed_workbench.services.credentials import (
    ALLOWED_CREDENTIALS,
    configure_credential,
    credential_sources,
    credential_store_path,
    credential_status,
    optional_credential,
    remove_credential,
)


class CredentialPolicyTests(unittest.TestCase):
    def test_only_scientific_data_credentials_are_allowed(self):
        self.assertEqual(
            ALLOWED_CREDENTIALS,
            frozenset({"NCBI_API_KEY"}),
        )
        with self.assertRaises(ValueError):
            optional_credential("UNSUPPORTED_CREDENTIAL")

    def test_status_never_returns_credential_values(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch.dict(
                os.environ,
                {
                    "BIOMED_WORKBENCH_CONFIG_HOME": temporary_directory,
                    "NCBI_API_KEY": "private-value",
                },
                clear=False,
            ):
                self.assertEqual(optional_credential("NCBI_API_KEY"), "private-value")
                status = credential_status()

        self.assertTrue(status["NCBI_API_KEY"])
        self.assertNotIn("private-value", repr(status))

    def test_local_store_is_private_repository_external_and_removable(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch.dict(
                os.environ,
                {"BIOMED_WORKBENCH_CONFIG_HOME": temporary_directory},
                clear=False,
            ):
                os.environ.pop("NCBI_API_KEY", None)
                configure_credential("NCBI_API_KEY", "stored-private-value")
                path = credential_store_path()
                self.assertEqual(path.parent, Path(temporary_directory).resolve())
                self.assertEqual(optional_credential("NCBI_API_KEY"), "stored-private-value")
                self.assertEqual(
                    credential_sources()["NCBI_API_KEY"],
                    "local-user-store",
                )
                if os.name != "nt":
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                self.assertTrue(remove_credential("NCBI_API_KEY"))
                self.assertFalse(path.exists())
                self.assertIsNone(optional_credential("NCBI_API_KEY"))

    def test_environment_takes_precedence_over_local_store(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch.dict(
                os.environ,
                {"BIOMED_WORKBENCH_CONFIG_HOME": temporary_directory},
                clear=False,
            ):
                os.environ.pop("NCBI_API_KEY", None)
                configure_credential("NCBI_API_KEY", "stored-value")
                with patch.dict(os.environ, {"NCBI_API_KEY": "session-value"}, clear=False):
                    self.assertEqual(optional_credential("NCBI_API_KEY"), "session-value")
                    self.assertEqual(credential_sources()["NCBI_API_KEY"], "environment")


if __name__ == "__main__":
    unittest.main()
