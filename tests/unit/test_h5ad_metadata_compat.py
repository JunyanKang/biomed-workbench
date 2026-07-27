"""Regression tests for H5AD-safe metadata handling in executable templates."""

from __future__ import annotations

import ast
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import anndata
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = (
    ROOT / "biomed_workbench/modules/builtin/single-cell-foundation-workflow/templates/scanpy_foundation.py",
    ROOT / "biomed_workbench/modules/builtin/single-cell-generative-modeling/templates/train_scvi_scanvi.py",
)


def helpers_from_template(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in {"h5ad_safe_frame", "sanitize_h5ad_metadata"}
    ]
    if len(functions) != 2:
        raise AssertionError(f"template does not expose both metadata helpers: {path.name}")
    namespace = {"np": np, "pd": pd}
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *functions], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(path), "exec"), namespace)
    return namespace["h5ad_safe_frame"], namespace["sanitize_h5ad_metadata"]


class H5ADMetadataCompatibilityTests(unittest.TestCase):
    def test_templates_preserve_values_and_make_string_metadata_hdf5_safe(self):
        for template in TEMPLATES:
            with self.subTest(template=template.name):
                safe_frame, sanitize = helpers_from_template(template)
                source = pd.DataFrame(
                    {
                        "label": pd.array(["naive", None], dtype="string"),
                        "sample": pd.array(["donor-1", "donor-2"], dtype="string"),
                        "numeric": [1, 2],
                    },
                    index=pd.Index(pd.array(["cell-1", "cell-2"], dtype="string"), name="cell_id"),
                )
                original = source.copy(deep=True)

                sanitized = safe_frame(source)
                object_like = SimpleNamespace(obs=source.copy(deep=True), var=source.iloc[:, :1].copy(deep=True))
                accounting = sanitize(object_like)

                self.assertIsInstance(sanitized["label"].dtype, pd.CategoricalDtype)
                self.assertIsInstance(sanitized["sample"].dtype, pd.CategoricalDtype)
                self.assertEqual(sanitized.index.tolist(), ["cell-1", "cell-2"])
                self.assertTrue(pd.isna(sanitized.loc["cell-2", "label"]))
                self.assertEqual(sanitized["sample"].astype(str).tolist(), ["donor-1", "donor-2"])
                self.assertEqual(sanitized["numeric"].tolist(), [1, 2])
                self.assertEqual(source.dtypes.astype(str).to_dict(), original.dtypes.astype(str).to_dict())
                self.assertTrue(source.equals(original))
                self.assertEqual(accounting, {"obs_columns": 3, "var_columns": 1})
                self.assertIsInstance(object_like.obs["label"].dtype, pd.CategoricalDtype)

    def test_normalized_metadata_writes_and_reloads_with_ann_data(self):
        for template in TEMPLATES:
            with self.subTest(template=template.name):
                _safe_frame, sanitize = helpers_from_template(template)
                adata = anndata.AnnData(
                    X=np.array([[1, 0], [0, 2]], dtype=np.int64),
                    obs=pd.DataFrame(
                        {"label": pd.array(["naive", None], dtype="string")},
                        index=pd.Index(pd.array(["cell-1", "cell-2"], dtype="string"), name="cell_id"),
                    ),
                    var=pd.DataFrame(
                        {"feature_class": pd.array(["protein_coding", "lncRNA"], dtype="string")},
                        index=pd.Index(pd.array(["gene-1", "gene-2"], dtype="string"), name="feature_id"),
                    ),
                )
                sanitize(adata)
                with tempfile.TemporaryDirectory() as temporary:
                    output = Path(temporary) / "normalized.h5ad"
                    adata.write_h5ad(output)
                    reloaded = anndata.read_h5ad(output)

                self.assertEqual(reloaded.obs_names.tolist(), ["cell-1", "cell-2"])
                self.assertEqual(reloaded.var_names.tolist(), ["gene-1", "gene-2"])
                self.assertEqual(reloaded.obs["label"].astype(str).tolist(), ["naive", "nan"])
                self.assertEqual(reloaded.var["feature_class"].astype(str).tolist(), ["protein_coding", "lncRNA"])


if __name__ == "__main__":
    unittest.main()
