import importlib.util
import unittest
from pathlib import Path

import anndata as ad
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "biomed_workbench/modules/builtin/spatial-multimethod-inference/templates/run_deconvolution.py"
SPEC = importlib.util.spec_from_file_location("spatial_deconvolution_template", TEMPLATE)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class TangramTemplateContractTests(unittest.TestCase):
    def test_tangram_accepts_official_style_normalized_expression(self):
        data = ad.AnnData(np.array([[0.0, 1.25], [2.5, 0.0]]))
        observed = MODULE.require_expression(data, None, integer_counts=False)
        self.assertEqual(observed.shape, (2, 2))

    def test_count_model_rejects_noninteger_expression(self):
        data = ad.AnnData(np.array([[0.0, 1.25], [2.0, 0.0]]))
        with self.assertRaisesRegex(ValueError, "cell2location requires"):
            MODULE.require_expression(data, None, integer_counts=True)

    def test_all_backends_reject_negative_expression(self):
        data = ad.AnnData(np.array([[0.0, -1.0], [2.0, 0.0]]))
        with self.assertRaisesRegex(ValueError, "finite nonnegative expression"):
            MODULE.require_expression(data, None, integer_counts=False)

    def test_density_prior_shim_changes_only_string_dispatch(self):
        source = np.array([0.2, 0.3, 0.5], dtype=np.float32)
        prior = source.view(MODULE.TangramDensityPrior)
        self.assertIs(prior == "rna_count_based", False)
        np.testing.assert_array_equal(np.asarray(prior), source)
        self.assertAlmostEqual(float(prior.sum()), 1.0)


if __name__ == "__main__":
    unittest.main()
