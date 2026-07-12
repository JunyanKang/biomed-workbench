import copy
import unittest
from unittest.mock import patch

from biomed_workbench.modules.compatibility import ArtifactSnapshot, EnvironmentSnapshot, detect_environment, evaluate_compatibility, invoke_compatible
from biomed_workbench.modules.contract import parse_manifest
from biomed_workbench.services.eutils import EUtilitiesClient, EUtilitiesError, probe_eutils_contract
from tests.unit.test_module_contract import valid_manifest_payload


def eutils_manifest_payload():
    payload = copy.deepcopy(valid_manifest_payload())
    payload["execution"]["kind"] = "service"
    payload["access"] = "public_api"
    payload["credentials"] = ["NCBI_API_KEY"]
    payload["tool_requirements"] = [
        {
            "name": "ncbi-eutils",
            "ecosystem": "service",
            "identity": "eutils.ncbi.nlm.nih.gov/entrez/eutils",
            "required": True,
            "tested_versions": ["contract-2026-03-04"],
            "allowed_versions": ["==contract-2026-03-04"],
            "version_source": "https://www.ncbi.nlm.nih.gov/books/NBK25499/",
            "verified_at": "2026-07-12",
            "version_probe": ["biomed_workbench.services.eutils:probe_eutils_contract"],
            "version_probe_kind": "service_contract",
            "version_probe_timeout_seconds": 10,
            "version_pattern": "(contract-[0-9]{4}-[0-9]{2}-[0-9]{2})",
            "mismatch_policy": "block",
            "version_differences": [
                {
                    "id": "esummary-database-fields",
                    "affected_versions": ["==contract-2026-03-04"],
                    "category": "field",
                    "description": "ESummary 2.0 uses database-specific document-summary schemas.",
                    "compatibility_effect": "requires-parser",
                    "required_action": "Validate fields against the selected Entrez database response schema.",
                    "source": "https://www.ncbi.nlm.nih.gov/books/NBK25499/",
                }
            ],
            "platforms": ["any"],
        }
    ]
    payload["compatibility_matrix"][0]["tool_versions"] = {"ncbi-eutils": ["contract-2026-03-04"]}
    return payload


def input_artifact():
    return ArtifactSnapshot(
        port="records",
        format="inline-json",
        format_version="1",
        compression="none",
        indexes=(),
        coordinate_system=None,
        genome_build=None,
        annotation_release=None,
        orientation="records",
        metadata_fields=("sample_id",),
    )


class ServiceVersionProbeContractTests(unittest.TestCase):
    def test_probe_addition_preserves_all_eutils_client_operations(self):
        for operation in ("info", "search", "summary", "fetch", "link"):
            with self.subTest(operation=operation):
                self.assertTrue(callable(getattr(EUtilitiesClient, operation, None)))

    def test_service_probe_is_never_dispatched_as_a_shell_command(self):
        manifest = parse_manifest(eutils_manifest_payload())
        shell_calls = []
        service_calls = []

        snapshot = detect_environment(
            manifest,
            probe_runner=lambda command, timeout: shell_calls.append((command, timeout)) or "",
            service_probe_runner=lambda target, timeout: service_calls.append((target, timeout)) or "contract-2026-03-04",
            dependency_provider=lambda name, ecosystem: "3.14.3",
            platform_name="macos-arm64",
        )

        self.assertEqual(shell_calls, [])
        self.assertEqual(service_calls, [("biomed_workbench.services.eutils:probe_eutils_contract", 10)])
        self.assertEqual(snapshot.tools, {"ncbi-eutils": "contract-2026-03-04"})

    def test_unknown_service_contract_blocks_before_entrypoint(self):
        manifest = parse_manifest(eutils_manifest_payload())
        environment = EnvironmentSnapshot(
            tools={"ncbi-eutils": "contract-2027-01-01"},
            dependencies={"python": "3.14.3"},
            platform="macos-arm64",
        )
        calls = []

        decision = evaluate_compatibility(manifest, environment, (input_artifact(),))
        with self.assertRaises(Exception):
            invoke_compatible(
                manifest,
                inputs={"rows": [{"sample_id": "s1"}]},
                environment=environment,
                artifacts=(input_artifact(),),
                entrypoint=lambda **kwargs: calls.append(kwargs),
            )

        self.assertFalse(decision.allowed)
        self.assertIn("UNVALIDATED_TOOL_VERSION", {finding.code for finding in decision.findings})
        self.assertEqual(calls, [])

    def test_eutils_probe_returns_version_only_for_valid_einfo_contract(self):
        valid = {"einforesult": {"dblist": ["pubmed", "gene"]}}
        with patch("biomed_workbench.services.eutils.EUtilitiesClient.info", return_value=valid):
            self.assertEqual(probe_eutils_contract(timeout_seconds=7), "contract-2026-03-04")

        with patch("biomed_workbench.services.eutils.EUtilitiesClient.info", return_value={"einforesult": {"dblist": []}}):
            with self.assertRaises(EUtilitiesError):
                probe_eutils_contract(timeout_seconds=7)


if __name__ == "__main__":
    unittest.main()
