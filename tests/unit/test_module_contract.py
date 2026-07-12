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
                "required": True,
                "tested_versions": ["3.14.3"],
                "allowed_versions": ["==3.14.3"],
                "version_source": "https://www.python.org/downloads/release/python-3143/",
                "verified_at": "2026-07-12",
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

    def test_manifest_round_trip_is_canonical_and_detached(self):
        payload = valid_manifest_payload()
        manifest = parse_manifest(payload)
        payload["intents"].append("mutated")

        serialized = manifest_to_dict(manifest)
        self.assertNotIn("mutated", serialized["intents"])
        self.assertEqual(parse_manifest(serialized), manifest)

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
