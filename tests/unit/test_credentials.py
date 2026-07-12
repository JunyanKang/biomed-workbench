import os
import unittest
from unittest.mock import patch

from biomed_workbench.services.credentials import (
    ALLOWED_CREDENTIALS,
    credential_status,
    optional_credential,
)


class CredentialPolicyTests(unittest.TestCase):
    def test_only_scientific_data_credentials_are_allowed(self):
        self.assertEqual(
            ALLOWED_CREDENTIALS,
            frozenset({"NCBI_API_KEY", "ELSEVIER_API_KEY", "SYNAPSE_AUTH_TOKEN"}),
        )
        with self.assertRaises(ValueError):
            optional_credential("NVIDIA_API_KEY")

    def test_status_never_returns_credential_values(self):
        with patch.dict(os.environ, {"NCBI_API_KEY": "private-value"}, clear=False):
            self.assertEqual(optional_credential("NCBI_API_KEY"), "private-value")
            status = credential_status()

        self.assertTrue(status["NCBI_API_KEY"])
        self.assertNotIn("private-value", repr(status))


if __name__ == "__main__":
    unittest.main()
