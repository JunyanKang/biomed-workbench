import copy
import unittest

from biomed_workbench.modules.contract import manifest_to_dict, parse_manifest


def closed_schema(properties=None, required=None):
    return {
        "type": "object",
        "properties": properties or {},
        "required": required or [],
        "additionalProperties": False,
    }


def format_contract(name="inline-json", versions=None):
    return {
        "name": name,
        "versions": versions or ["1"],
        "representations": ["structured"],
        "compression": ["none"],
        "required_indexes": [],
        "coordinate_systems": [],
        "genome_build_policy": "not_applicable",
        "genome_builds": [],
        "annotation_releases": [],
        "orientations": ["records"],
    }


def valid_manifest_payload():
    return {
        "schema_version": 1,
        "id": "fixture-analysis",
        "version": "1.0.0",
        "title": "Analyze a fixture",
        "description": "Analyze a structured fixture with explicit scientific quality controls.",
        "module_type": "analysis",
        "domains": ["omics"],
        "intents": ["analyze fixture", "分析测试数据"],
        "questions": ["Does the fixture contain the expected signal?"],
        "entrypoint": "biomed_workbench.capabilities.data:profile_table",
        "execution": {
            "kind": "python",
            "timeout_seconds": 30,
            "max_output_bytes": 1000000,
        },
        "maturity": "validated",
        "input_artifacts": [
            {
                "name": "records",
                "artifact_type": "feature_matrix",
                "formats": [format_contract()],
                "processing_levels": ["raw", "processed"],
                "required_metadata": ["sample_id"],
            }
        ],
        "output_artifacts": [
            {
                "name": "profile",
                "artifact_type": "quality_report",
                "formats": [format_contract()],
                "processing_levels": ["derived"],
                "required_metadata": ["module_version"],
            }
        ],
        "preconditions": ["At least one structured record is available."],
        "assumptions": ["Rows are observations and columns are consistently typed."],
        "quality_gates": [
            {
                "id": "missingness-reviewed",
                "severity": "major",
                "description": "Missingness is quantified before interpretation.",
                "blocks_interpretation": True,
            }
        ],
        "limitations": ["A profile does not establish a biological association."],
        "evidence_effects": ["describes_data_quality"],
        "alternatives": [],
        "complements": [],
        "tool_requirements": [],
        "dependencies": [
            {
                "name": "python",
                "ecosystem": "runtime",
                "identity": "python-runtime",
                "required": True,
                "tested_versions": ["3.14.3"],
                "allowed_versions": ["==3.14.3"],
                "version_source": "https://www.python.org/downloads/release/python-3143/",
                "verified_at": "2026-07-12",
                "version_probe": ["biomed_workbench.modules.compatibility:probe_python_runtime"],
                "version_probe_kind": "python_callable",
                "version_probe_timeout_seconds": 5,
                "version_pattern": "([0-9]+(?:\\.[0-9]+)+)",
                "purpose": "Execute the module entrypoint.",
                "conflicts": [],
                "platforms": ["any"],
            }
        ],
        "compatibility_matrix": [
            {
                "id": "python-3.14.3-inline-json-1",
                "module_version": "1.0.0",
                "tool_versions": {},
                "dependency_versions": {"python": ["3.14.3"]},
                "input_formats": {"records": ["inline-json@1"]},
                "output_formats": {"profile": ["inline-json@1"]},
                "platforms": ["any"],
                "regression_evidence_ids": ["fixture-analysis-regression-v1"],
                "end_to_end_evidence_ids": ["fixture-analysis-e2e-v1"],
                "verified_at": "2026-07-12",
            }
        ],
        "access": "offline",
        "mutability": "read_only",
        "credentials": [],
        "input_schema": closed_schema(
            {"rows": {"type": "array", "items": {"type": "object"}}},
            ["rows"],
        ),
        "output_schema": closed_schema(
            {"row_count": {"type": "integer"}, "columns": {"type": "object"}},
            ["row_count", "columns"],
        ),
        "kernel_compatibility": [">=0.2.0,<0.3.0"],
        "provenance": {
            "license": "Apache-2.0",
            "concept_sources": ["Project-owned clean-room scientific contract."],
        },
    }


def command_manifest_payload():
    payload = valid_manifest_payload()
    payload["entrypoint"] = "scientific-command"
    payload["execution"] = {
        "kind": "command",
        "timeout_seconds": 30,
        "max_output_bytes": 1000000,
        "command": {
            "tool_name": "fixture-tool",
            "executable": "fixture-tool",
            "arguments": ["--input", "{input:records}", "--output", "{output:profile}", "--label", "{parameter:label}"],
            "inputs": [{"name": "records", "port": "records", "role": "records", "filename": "records.json"}],
            "outputs": [
                {"name": "profile", "port": "profile", "role": "profile", "filename": "profile.json", "media_type": "application/json"}
            ],
            "parameter_names": ["label"],
            "timeout_seconds": 30,
            "max_output_bytes": 1000000,
            "max_payload_bytes": 1000000,
        },
    }
    payload["tool_requirements"] = [
        {
            "name": "fixture-tool",
            "ecosystem": "system",
            "identity": "fixture-tool",
            "required": True,
            "tested_versions": ["2.4.1"],
            "allowed_versions": ["==2.4.1"],
            "version_source": "https://example.org/fixture-tool/releases/2.4.1",
            "verified_at": "2026-07-12",
            "version_probe": ["fixture-tool", "--version"],
            "version_probe_kind": "command",
            "version_probe_timeout_seconds": 10,
            "version_pattern": "([0-9]+(?:\\.[0-9]+)+)",
            "mismatch_policy": "block",
            "version_differences": [],
            "platforms": ["any"],
        }
    ]
    payload["compatibility_matrix"][0]["tool_versions"] = {"fixture-tool": ["2.4.1"]}
    return payload


class ModuleContractTests(unittest.TestCase):
    def test_manifest_requires_complete_scientific_and_version_contracts(self):
        manifest = parse_manifest(valid_manifest_payload())

        self.assertEqual(manifest.id, "fixture-analysis")
        self.assertEqual(manifest.module_type, "analysis")
        self.assertEqual(manifest.execution.kind, "python")
        self.assertEqual(manifest.input_artifacts[0].artifact_type, "feature_matrix")
        self.assertEqual(manifest.input_artifacts[0].formats[0].versions, ("1",))
        self.assertEqual(manifest.quality_gates[0].severity, "major")
        self.assertEqual(manifest.dependencies[0].tested_versions, ("3.14.3",))
        self.assertEqual(manifest.compatibility_matrix[0].input_formats["records"], ("inline-json@1",))
        self.assertEqual(manifest.compatibility_matrix[0].regression_evidence_ids, ("fixture-analysis-regression-v1",))

    def test_manifest_round_trip_is_canonical_and_detached(self):
        payload = valid_manifest_payload()
        manifest = parse_manifest(payload)
        payload["intents"].append("mutated")

        serialized = manifest_to_dict(manifest)
        self.assertNotIn("mutated", serialized["intents"])
        self.assertEqual(parse_manifest(serialized), manifest)

    def test_command_manifest_binds_versioned_tool_ports_roles_argv_and_limits(self):
        manifest = parse_manifest(command_manifest_payload())
        command = manifest.execution.command

        self.assertEqual(command.tool_name, "fixture-tool")
        self.assertEqual(command.inputs[0].port, "records")
        self.assertEqual(command.outputs[0].role, "profile")
        self.assertEqual(parse_manifest(manifest_to_dict(manifest)), manifest)

    def test_command_manifest_accepts_one_bounded_output_directory_for_derived_files(self):
        payload = command_manifest_payload()
        payload["execution"]["command"]["arguments"] = [
            "--input", "{input:records}", "--outdir", "{output-directory}", "--label", "{parameter:label}"
        ]

        manifest = parse_manifest(payload)

        self.assertIn("{output-directory}", manifest.execution.command.arguments)

    def test_command_manifest_rejects_unversioned_executable_or_port_drift(self):
        cases = (
            lambda payload: payload["tool_requirements"][0].__setitem__("identity", "other-tool"),
            lambda payload: payload["execution"]["command"]["inputs"][0].__setitem__("port", "missing-port"),
            lambda payload: payload["execution"]["command"].__setitem__("timeout_seconds", 29),
        )
        for mutator in cases:
            payload = command_manifest_payload()
            mutator(payload)
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                parse_manifest(payload)

    def test_version_difference_requires_typed_affected_surface_action_and_source(self):
        payload = command_manifest_payload()
        payload["tool_requirements"][0]["version_differences"] = [
            {
                "id": "fixture-output-field-v2",
                "affected_versions": ["==2.4.1"],
                "category": "field",
                "description": "Version 2.4.1 emits the validated result field names.",
                "compatibility_effect": "requires-parser",
                "required_action": "Use the version-specific output parser and regression fixture.",
                "source": "https://example.org/fixture-tool/releases/2.4.1",
            }
        ]

        manifest = parse_manifest(payload)

        self.assertEqual(manifest.tool_requirements[0].version_differences[0].category, "field")
        invalid = copy.deepcopy(payload)
        del invalid["tool_requirements"][0]["version_differences"][0]["required_action"]
        with self.assertRaises(ValueError):
            parse_manifest(invalid)
        outside = copy.deepcopy(payload)
        outside["tool_requirements"][0]["version_differences"][0]["affected_versions"] = ["==9.0.0"]
        with self.assertRaisesRegex(ValueError, "outside"):
            parse_manifest(outside)

    def test_manifest_rejects_unknown_top_level_and_nested_fields(self):
        for mutator in (
            lambda payload: payload.__setitem__("unexpected", True),
            lambda payload: payload["execution"].__setitem__("shell", True),
            lambda payload: payload["input_artifacts"][0]["formats"][0].__setitem__("guess", True),
        ):
            payload = valid_manifest_payload()
            mutator(payload)
            with self.subTest(payload=payload), self.assertRaisesRegex(ValueError, "unsupported"):
                parse_manifest(payload)

    def test_external_tool_requires_tested_versions_source_probe_and_matrix_row(self):
        payload = valid_manifest_payload()
        payload["tool_requirements"] = [
            {
                "name": "scanpy",
                "ecosystem": "python",
                "identity": "scanpy",
                "required": True,
                "tested_versions": [],
                "allowed_versions": ["==1.11.5"],
                "version_source": "",
                "verified_at": "2026-07-12",
                "version_probe": ["python", "-c", "import scanpy; print(scanpy.__version__)"],
                "version_probe_kind": "command",
                "version_probe_timeout_seconds": 10,
                "version_pattern": "([0-9]+(?:\\.[0-9]+)+)",
                "mismatch_policy": "block",
                "version_differences": [],
                "platforms": ["any"],
            }
        ]

        with self.assertRaisesRegex(ValueError, "tested versions"):
            parse_manifest(payload)

    def test_format_versions_are_mandatory_and_not_inferred(self):
        payload = valid_manifest_payload()
        payload["input_artifacts"][0]["formats"][0]["versions"] = []

        with self.assertRaisesRegex(ValueError, "format versions"):
            parse_manifest(payload)

    def test_tested_versions_must_fall_inside_declared_allowed_versions(self):
        payload = valid_manifest_payload()
        payload["dependencies"][0]["tested_versions"] = ["3.14.3"]
        payload["dependencies"][0]["allowed_versions"] = [">=3.10,<3.14"]

        with self.assertRaisesRegex(ValueError, "outside allowed versions"):
            parse_manifest(payload)

    def test_compatibility_rows_must_reference_declared_ports_and_versions(self):
        payload = valid_manifest_payload()
        payload["compatibility_matrix"][0]["input_formats"] = {"missing-port": ["inline-json@1"]}

        with self.assertRaisesRegex(ValueError, "unknown input artifact"):
            parse_manifest(payload)

    def test_open_input_or_output_schema_is_rejected(self):
        for field in ("input_schema", "output_schema"):
            payload = valid_manifest_payload()
            del payload[field]["additionalProperties"]
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "closed object"):
                parse_manifest(payload)

    def test_manifest_is_immutable(self):
        manifest = parse_manifest(copy.deepcopy(valid_manifest_payload()))

        with self.assertRaises(Exception):
            manifest.id = "changed"


if __name__ == "__main__":
    unittest.main()
