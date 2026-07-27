"""Contract tests for the bounded Bayesian DE branch in the scVI template."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

import pandas as pd


TEMPLATE = (
    Path(__file__).resolve().parents[2]
    / "biomed_workbench/modules/builtin/single-cell-generative-modeling/templates/train_scvi_scanvi.py"
)


def bayesian_de_function():
    tree = ast.parse(TEMPLATE.read_text(encoding="utf-8"), filename=str(TEMPLATE))
    node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == "bayesian_de_summary")
    namespace = {"argparse": argparse, "pd": pd}
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), node], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(TEMPLATE), "exec"), namespace)
    return namespace["bayesian_de_summary"]


class FakeModel:
    def __init__(self, table: pd.DataFrame):
        self.table = table
        self.calls = []

    def differential_expression(self, **kwargs):
        self.calls.append(kwargs)
        return self.table.copy()


class BayesianDETemplateTests(unittest.TestCase):
    def args(self, **overrides):
        values = {
            "de_group_key": "cluster",
            "de_group1": "A",
            "de_group2": "",
            "de_delta": 0.25,
            "de_top_genes": 2,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_change_mode_output_is_bounded_sorted_and_labeled_cell_level(self):
        function = bayesian_de_function()
        model = FakeModel(
            pd.DataFrame(
                {
                    "proba_de": [0.3, 0.9, 0.6],
                    "lfc_mean": [0.2, 1.1, -0.8],
                    "bayes_factor": [0.1, 3.0, 1.2],
                    "group1": ["A", "A", "A"],
                    "group2": ["rest", "rest", "rest"],
                },
                index=["gene-low", "gene-high", "gene-mid"],
            )
        )
        adata = SimpleNamespace(obs=pd.DataFrame({"cluster": ["A", "B", "B"]}))

        result = function(model, adata, self.args())

        self.assertEqual(model.calls, [{"groupby": "cluster", "group1": "A", "group2": None, "mode": "change", "delta": 0.25}])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["evidence_level"], "exploratory_cell_level")
        self.assertEqual([item["feature"] for item in result["top_features"]], ["gene-high", "gene-mid"])
        self.assertIn("cannot substitute", result["interpretation_boundary"])

    def test_rest_literal_and_missing_change_mode_fields_are_rejected(self):
        function = bayesian_de_function()
        model = FakeModel(pd.DataFrame({"proba_de": [0.9]}))
        adata = SimpleNamespace(obs=pd.DataFrame({"cluster": ["A", "B"]}))

        with self.assertRaisesRegex(ValueError, "not an scvi-tools category"):
            function(model, adata, self.args(de_group2="rest"))
        with self.assertRaisesRegex(RuntimeError, "lacks required fields"):
            function(model, adata, self.args())

    def test_unrequested_de_does_not_call_the_model(self):
        function = bayesian_de_function()
        model = FakeModel(pd.DataFrame())
        adata = SimpleNamespace(obs=pd.DataFrame({"cluster": ["A"]}))

        result = function(model, adata, self.args(de_group_key="none", de_group1="", de_group2=""))

        self.assertEqual(result, {"status": "not_requested", "evidence_level": "not_applicable"})
        self.assertEqual(model.calls, [])


if __name__ == "__main__":
    unittest.main()
