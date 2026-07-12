import unittest

from biomed_workbench.modules.compatibility import ArtifactSnapshot, EnvironmentSnapshot, evaluate_compatibility
from biomed_workbench.modules.contract import parse_manifest
from tests.unit.test_module_compatibility import artifact, environment, external_manifest_payload


class ToolVersionCompatibilityContractTests(unittest.TestCase):
    def test_compatibility_is_exact_not_monotonic(self):
        manifest = parse_manifest(external_manifest_payload())
        validated = evaluate_compatibility(manifest, environment("1.11.5"), (artifact(),))
        newer_unvalidated = evaluate_compatibility(manifest, environment("1.11.6"), (artifact(),))

        self.assertTrue(validated.allowed)
        self.assertFalse(newer_unvalidated.allowed)

    def test_missing_tool_and_artifact_block_independently(self):
        manifest = parse_manifest(external_manifest_payload())
        snapshot = EnvironmentSnapshot(
            tools={},
            dependencies={"python": "3.14.3", "anndata": "0.11.4"},
            platform="macos-arm64",
        )
        decision = evaluate_compatibility(manifest, snapshot, ())
        codes = {finding.code for finding in decision.findings}

        self.assertIn("MISSING_TOOL", codes)
        self.assertIn("MISSING_ARTIFACT", codes)


if __name__ == "__main__":
    unittest.main()
