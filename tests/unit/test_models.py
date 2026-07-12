import unittest

from biomed_workbench.models import Artifact, Capability, EvidenceItem, ExecutionResult


class ModelTests(unittest.TestCase):
    def test_capability_is_immutable_and_validated(self):
        capability = Capability(
            id="ncbi-search",
            workflow="evidence",
            kind="service",
            title="Search NCBI Entrez",
            description="Search a selected Entrez database with a bounded query.",
            entrypoint="biomed_workbench.capabilities.ncbi:search",
            input_schema={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            requirements=(),
            access="public_api",
            mutability="read_only",
        )
        self.assertEqual(capability.id, "ncbi-search")
        with self.assertRaises(Exception):
            capability.id = "changed"

    def test_capability_rejects_invalid_contract_values(self):
        base = dict(
            id="valid-id",
            workflow="evidence",
            kind="service",
            title="Valid",
            description="A sufficiently clear capability description.",
            entrypoint="module:function",
            input_schema={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            requirements=(),
            access="public_api",
            mutability="read_only",
        )
        for field, value in (("id", "Bad ID"), ("workflow", "source-project"), ("kind", "adapter"), ("access", "paid_api")):
            values = {**base, field: value}
            with self.subTest(field=field), self.assertRaises(ValueError):
                Capability(**values)

    def test_capability_rejects_open_or_inconsistent_input_schemas(self):
        base = dict(
            id="valid-id",
            workflow="evidence",
            kind="service",
            title="Valid",
            description="A sufficiently clear capability description.",
            entrypoint="module:function",
            requirements=(),
            access="public_api",
            mutability="read_only",
        )
        invalid = (
            {"type": "array"},
            {"type": "object", "properties": {}, "required": []},
            {"type": "object", "properties": {}, "required": ["missing"], "additionalProperties": False},
        )
        for schema in invalid:
            with self.subTest(schema=schema), self.assertRaises(ValueError):
                Capability(**base, input_schema=schema)

    def test_execution_result_serializes_scientific_outputs(self):
        result = ExecutionResult(
            capability_id="ncbi-search",
            status="completed",
            output={"count": 1},
            evidence=(EvidenceItem(identifier="7157", source="NCBI Gene", claim="TP53 gene record"),),
            artifacts=(Artifact(kind="json", path="results/tp53.json", description="Normalized record"),),
            warnings=(),
        )
        payload = result.to_dict()
        self.assertEqual(payload["evidence"][0]["identifier"], "7157")
        self.assertNotIn("api_key", str(payload).lower())


if __name__ == "__main__":
    unittest.main()
