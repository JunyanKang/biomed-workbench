import unittest
from unittest.mock import patch

from biomed_workbench.models import Capability
from biomed_workbench.runner import InputValidationError, MutationPermissionError, run, validate_inputs


class RunnerTests(unittest.TestCase):
    def test_schema_validation_rejects_missing_extra_and_wrong_types(self):
        capability = Capability(
            id="fixture",
            workflow="evidence",
            kind="python",
            title="Fixture",
            description="Validate structured runner input behavior.",
            entrypoint="fixture:call",
            input_schema={
                "type": "object",
                "properties": {"database": {"type": "string"}, "retmax": {"type": "integer", "maximum": 10}},
                "required": ["database"],
                "additionalProperties": False,
            },
            requirements=(),
            access="offline",
            mutability="read_only",
        )
        for value in ({}, {"database": 1}, {"database": "gene", "retmax": 11}, {"database": "gene", "extra": True}):
            with self.subTest(value=value), self.assertRaises(InputValidationError):
                validate_inputs(capability, value)

    def test_runner_executes_resolved_callable_and_returns_structured_result(self):
        with patch("biomed_workbench.runner.resolve_entrypoint", return_value=lambda database, term: {"database": database, "term": term}):
            result = run("ncbi-search", {"database": "gene", "term": "TP53"})

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.output["database"], "gene")
        self.assertEqual(result.capability_id, "ncbi-search")

    def test_mutating_capability_requires_explicit_permission(self):
        capability = Capability(
            id="fixture-write",
            workflow="publication",
            kind="python",
            title="Fixture write",
            description="A fixture that represents an output-writing capability.",
            entrypoint="fixture:call",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            requirements=(),
            access="offline",
            mutability="writes_output",
        )
        with patch("biomed_workbench.runner.resolve", return_value=capability):
            with self.assertRaises(MutationPermissionError):
                run("fixture-write", {}, allow_mutation=False)


if __name__ == "__main__":
    unittest.main()
