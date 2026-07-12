import copy
import unittest
from dataclasses import replace

from biomed_workbench.modules.compatibility import (
    ArtifactSnapshot,
    CompatibilityError,
    EnvironmentSnapshot,
    detect_environment,
    evaluate_compatibility,
    invoke_compatible,
)
from biomed_workbench.modules.contract import parse_manifest
from tests.unit.test_module_contract import format_contract, valid_manifest_payload


def external_manifest_payload():
    payload = valid_manifest_payload()
    payload["input_artifacts"][0]["formats"] = [
        {
            **format_contract("h5ad", ["0.11"]),
            "representations": ["container", "sparse"],
            "compression": ["gzip", "none"],
            "coordinate_systems": ["zero-based-half-open"],
            "genome_build_policy": "required",
            "genome_builds": ["GRCh38"],
            "annotation_releases": ["GENCODE-47"],
            "orientations": ["cells-by-genes"],
        }
    ]
    payload["input_artifacts"][0]["required_metadata"] = ["sample_id", "batch"]
    payload["tool_requirements"] = [
        {
            "name": "scanpy",
            "ecosystem": "python",
            "identity": "scanpy",
            "required": True,
            "tested_versions": ["1.11.5"],
            "allowed_versions": ["==1.11.5"],
            "version_source": "https://scanpy.readthedocs.io/en/stable/release-notes/",
            "verified_at": "2026-07-12",
            "version_probe": ["python", "-c", "import scanpy; print(scanpy.__version__)"],
            "version_probe_kind": "command",
            "version_probe_timeout_seconds": 10,
            "version_pattern": "([0-9]+(?:\\.[0-9]+)+)",
            "mismatch_policy": "alternative",
            "version_differences": [
                {
                    "id": "scanpy-h5ad-011",
                    "affected_versions": ["==1.11.5"],
                    "category": "output-format",
                    "description": "The validated Scanpy release uses the declared h5ad 0.11 serialization behavior.",
                    "compatibility_effect": "requires-format",
                    "required_action": "Require h5ad 0.11 fixtures and reject unvalidated serialization versions.",
                    "source": "https://scanpy.readthedocs.io/en/stable/release-notes/",
                }
            ],
            "platforms": ["macos-arm64", "linux-x86_64"],
        }
    ]
    payload["dependencies"].append(
        {
            "name": "anndata",
            "ecosystem": "python",
            "identity": "anndata",
            "required": True,
            "tested_versions": ["0.11.4"],
            "allowed_versions": ["==0.11.4"],
            "version_source": "https://anndata.readthedocs.io/en/stable/release-notes/",
            "verified_at": "2026-07-12",
            "version_probe": ["python", "-c", "import anndata; print(anndata.__version__)"],
            "version_probe_kind": "command",
            "version_probe_timeout_seconds": 10,
            "version_pattern": "([0-9]+(?:\\.[0-9]+)+)",
            "purpose": "Read and validate annotated expression matrices.",
            "conflicts": [
                {
                    "dependency": "anndata",
                    "versions": ["<0.11"],
                    "reason": "Earlier releases are outside the validated h5ad serialization contract.",
                    "required_action": "Block execution and use the exact validated dependency version.",
                    "source": "https://anndata.readthedocs.io/en/stable/release-notes/",
                }
            ],
            "platforms": ["any"],
        }
    )
    payload["alternatives"] = []
    payload["compatibility_matrix"] = [
        {
            "id": "scanpy-1.11.5-h5ad-0.11",
            "module_version": "1.0.0",
            "tool_versions": {"scanpy": ["1.11.5"]},
            "dependency_versions": {"python": ["3.14.3"], "anndata": ["0.11.4"]},
            "input_formats": {"records": ["h5ad@0.11"]},
            "output_formats": {"profile": ["inline-json@1"]},
            "platforms": ["macos-arm64", "linux-x86_64"],
            "regression_evidence_ids": ["fixture-analysis-regression-v1"],
            "end_to_end_evidence_ids": ["fixture-analysis-e2e-v1"],
            "verified_at": "2026-07-12",
        }
    ]
    return payload


def environment(scanpy="1.11.5", anndata="0.11.4"):
    return EnvironmentSnapshot(
        tools={"scanpy": scanpy},
        dependencies={"python": "3.14.3", "anndata": anndata},
        platform="macos-arm64",
    )


def artifact(**overrides):
    values = {
        "port": "records",
        "format": "h5ad",
        "format_version": "0.11",
        "compression": "gzip",
        "indexes": (),
        "coordinate_system": "zero-based-half-open",
        "genome_build": "GRCh38",
        "annotation_release": "GENCODE-47",
        "orientation": "cells-by-genes",
        "metadata_fields": ("sample_id", "batch"),
    }
    values.update(overrides)
    return ArtifactSnapshot(**values)


class ModuleCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.manifest = parse_manifest(external_manifest_payload())

    def test_exact_validated_tool_dependency_and_format_row_allows_execution(self):
        decision = evaluate_compatibility(self.manifest, environment(), (artifact(),))

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.compatibility_row_id, "scanpy-1.11.5-h5ad-0.11")
        self.assertEqual(decision.findings, ())

    def test_unknown_tool_version_blocks_instead_of_guessing_newer_is_compatible(self):
        decision = evaluate_compatibility(self.manifest, environment(scanpy="1.12.0"), (artifact(),))

        self.assertFalse(decision.allowed)
        self.assertIn("UNVALIDATED_TOOL_VERSION", {finding.code for finding in decision.findings})

    def test_dependency_and_format_incompatibilities_are_distinct(self):
        cases = (
            (environment(anndata="0.12.0"), artifact(), "UNVALIDATED_DEPENDENCY_VERSION"),
            (environment(), artifact(format_version="0.10"), "UNSUPPORTED_FORMAT_VERSION"),
            (environment(), artifact(compression="zstd"), "UNSUPPORTED_COMPRESSION"),
            (environment(), artifact(coordinate_system="one-based-inclusive"), "COORDINATE_SYSTEM_MISMATCH"),
            (environment(), artifact(genome_build="GRCh37"), "GENOME_BUILD_MISMATCH"),
            (environment(), artifact(annotation_release="GENCODE-46"), "ANNOTATION_RELEASE_MISMATCH"),
            (environment(), artifact(orientation="genes-by-cells"), "ORIENTATION_MISMATCH"),
            (environment(), artifact(metadata_fields=("sample_id",)), "MISSING_METADATA"),
        )
        for snapshot, input_artifact, code in cases:
            with self.subTest(code=code):
                decision = evaluate_compatibility(self.manifest, snapshot, (input_artifact,))
                self.assertFalse(decision.allowed)
                self.assertIn(code, {finding.code for finding in decision.findings})

    def test_required_indexes_are_checked(self):
        payload = external_manifest_payload()
        payload["input_artifacts"][0]["formats"][0]["required_indexes"] = ["h5ad-index"]
        manifest = parse_manifest(payload)

        decision = evaluate_compatibility(manifest, environment(), (artifact(),))
        self.assertIn("MISSING_INDEX", {finding.code for finding in decision.findings})

    def test_registered_format_profile_adds_foundational_metadata_gate(self):
        payload = external_manifest_payload()
        payload["input_artifacts"][0]["formats"][0]["versions"] = ["0.1.0"]
        payload["input_artifacts"][0]["formats"][0]["orientations"] = ["observations-by-variables"]
        payload["compatibility_matrix"][0]["input_formats"] = {"records": ["h5ad@0.1.0"]}
        manifest = parse_manifest(payload)
        metadata_fields = ("sample_id", "batch", "encoding-type", "encoding-version", "obs-index", "var-index")
        snapshot = artifact(
            format_version="0.1.0",
            orientation="observations-by-variables",
            metadata_fields=metadata_fields,
            representation="container",
            sort_order="matrix-index-order",
            identifier_namespace="ensembl-gene",
            payload_roles=("matrix",),
            processing_level="filtered-counts",
        )

        rejected = evaluate_compatibility(manifest, environment(), (snapshot,))
        accepted = evaluate_compatibility(
            manifest,
            environment(),
            (replace(snapshot, sample_manifest_digest="b" * 64),),
        )

        self.assertIn("SAMPLE_MANIFEST_MISSING", {finding.code for finding in rejected.findings})
        self.assertTrue(accepted.allowed)

    def test_unvalidated_environment_never_invokes_entrypoint(self):
        calls = []

        with self.assertRaises(CompatibilityError):
            invoke_compatible(
                self.manifest,
                inputs={"rows": []},
                environment=environment(scanpy="1.12.0"),
                artifacts=(artifact(),),
                entrypoint=lambda **kwargs: calls.append(kwargs),
            )

        self.assertEqual(calls, [])

    def test_valid_invocation_records_versions_formats_and_parameters(self):
        result = invoke_compatible(
            self.manifest,
            inputs={"rows": [{"sample_id": "s1", "value": 1}]},
            environment=environment(),
            artifacts=(artifact(),),
            entrypoint=lambda **_kwargs: {"row_count": 1, "columns": {"value": {}}},
        )

        self.assertEqual(result.output["row_count"], 1)
        self.assertEqual(result.provenance["module_version"], "1.0.0")
        self.assertEqual(result.provenance["tools"], {"scanpy": "1.11.5"})
        self.assertEqual(result.provenance["dependencies"]["anndata"], "0.11.4")
        self.assertEqual(result.provenance["input_formats"]["records"], "h5ad@0.11")
        self.assertIn("parameters_digest", result.provenance)

    def test_detect_environment_uses_bounded_declared_probe_and_dependency_provider(self):
        commands = []

        snapshot = detect_environment(
            self.manifest,
            probe_runner=lambda command, timeout: commands.append((command, timeout)) or "scanpy 1.11.5",
            dependency_provider=lambda name, ecosystem: {("python", "runtime"): "3.14.3", ("anndata", "python"): "0.11.4"}[(name, ecosystem)],
            platform_name="macos-arm64",
        )

        self.assertEqual(snapshot.tools, {"scanpy": "1.11.5"})
        self.assertEqual(snapshot.dependencies["anndata"], "0.11.4")
        self.assertEqual(commands[0][0], tuple(self.manifest.tool_requirements[0].version_probe))
        self.assertLessEqual(commands[0][1], self.manifest.execution.timeout_seconds)

    def test_detect_environment_executes_declared_dependency_probe_types(self):
        commands = []
        callables = []

        snapshot = detect_environment(
            self.manifest,
            probe_runner=lambda command, timeout: commands.append((command, timeout)) or (
                "scanpy 1.11.5" if "scanpy" in " ".join(command) else "anndata 0.11.4"
            ),
            callable_probe_runner=lambda target, timeout: callables.append((target, timeout)) or "3.14.3",
            platform_name="macos-arm64",
        )

        self.assertEqual(snapshot.dependencies, {"python": "3.14.3", "anndata": "0.11.4"})
        self.assertEqual(callables[0][0], "biomed_workbench.modules.compatibility:probe_python_runtime")
        self.assertTrue(any("anndata" in " ".join(command) for command, _timeout in commands))


if __name__ == "__main__":
    unittest.main()
