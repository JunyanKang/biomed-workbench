import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "biomed_workbench/modules/builtin/single-cell-foundation-workflow/templates/seurat_foundation.R"


@unittest.skipUnless(shutil.which("Rscript"), "Rscript is required for the Seurat template fixture")
class SeuratFoundationTemplateTests(unittest.TestCase):
    def test_uses_declared_nondefault_assay_for_qc_columns(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.rds"
            output = root / "output.rds"
            qc_report = root / "qc.json"
            cluster_report = root / "clusters.json"
            build = subprocess.run(
                [
                    "Rscript", "-e",
                    "suppressPackageStartupMessages(library(Seurat)); "
                    "counts <- Matrix::Matrix(matrix((seq_len(600) %% 7) + 1, nrow = 30, ncol = 20), sparse = TRUE); "
                    "rownames(counts) <- c('MT-CO1', paste0('GENE', 2:30)); "
                    "colnames(counts) <- paste0('cell', 1:20); "
                    "object <- CreateSeuratObject(counts = counts, assay = 'GeneExpression'); "
                    "object$sample_id <- rep(c('donor1', 'donor2'), each = 10); "
                    f"saveRDS(object, '{source}')",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            run = subprocess.run(
                [
                    "Rscript", str(TEMPLATE),
                    "--input", str(source), "--output-rds", str(output),
                    "--qc-report", str(qc_report), "--cluster-report", str(cluster_report),
                    "--sample-key", "sample_id", "--assay", "GeneExpression",
                    "--min-counts", "1", "--max-counts", "0", "--min-features", "1", "--max-features", "0",
                    "--max-mito-percent", "100", "--n-variable-features", "20", "--n-pcs", "5",
                    "--n-neighbors", "5", "--resolutions", "0.2", "--seed", "17",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            report = json.loads(qc_report.read_text(encoding="utf-8"))

        self.assertEqual(report["assay_qc_columns"], {"counts": "nCount_GeneExpression", "features": "nFeature_GeneExpression"})
        self.assertEqual(report["retained_cells"], 20)


if __name__ == "__main__":
    unittest.main()
