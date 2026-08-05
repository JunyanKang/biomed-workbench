import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from biomed_workbench.modules.semantic_output_validation import (
    _PROFILE_VALIDATORS,
    registered_semantic_profiles,
)


class SemanticProfileAdversarialFixtureTests(unittest.TestCase):
    def _file(self, root: Path, name: str, content: str | bytes) -> Path:
        path = root / name
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        return path

    def _json(self, root: Path, *, valid: bool) -> tuple[dict, tuple[dict, ...], int]:
        value = (
            {
                "schema_version": 1,
                "analysis_mode": "observed",
                "records": [{"id": "record-1", "value": 2.0}],
                "summary": "One observed scientific record.",
            }
            if valid
            else {}
        )
        path = self._file(root, "result.json", json.dumps(value))
        primary = {"role": "primary", "path": str(path), "media_type": "application/json"}
        return primary, (primary,), 1

    def _bulk(self, root: Path, *, valid: bool):
        value = {
            "schema_version": 1,
            "analysis_mode": "observed" if valid else "not-run",
            "records": [{"sample_id": "s1", "metric": "mapped_reads", "value": 100, "unit": "reads"}],
            "summary": "Observed assay accounting.",
        }
        path = self._file(root, "bulk.json", json.dumps(value))
        primary = {"role": "primary", "path": str(path), "media_type": "application/json"}
        return primary, (primary,), 1

    def _table(self, root: Path, *, valid: bool):
        text = "feature\teffect\nA\t1.2\n" if valid else "feature\teffect\nA\tnot-numeric\n"
        path = self._file(root, "statistics.tsv", text)
        primary = {"role": "primary", "path": str(path), "media_type": "text/tab-separated-values"}
        return primary, (primary,), 1

    def _genomic(self, root: Path, *, valid: bool):
        text = "chr1\t10\t20\n" if valid else "chr1\t20\t10\n"
        path = self._file(root, "regions.bed", text)
        primary = {"role": "primary", "path": str(path), "media_type": "text/tab-separated-values"}
        return primary, (primary,), 1

    def _sequence(self, root: Path, *, valid: bool):
        text = ">seq1\nACGT\n" if valid else "ACGT\n"
        path = self._file(root, "sequences.fa", text)
        primary = {"role": "primary", "path": str(path), "media_type": "text/x-fasta"}
        return primary, (primary,), 1

    def _matrix(self, root: Path, *, valid: bool):
        value = 3 if valid else -3
        text = f"%%MatrixMarket matrix coordinate integer general\n2 2 1\n1 2 {value}\n"
        path = self._file(root, "matrix.mtx", text)
        primary = {"role": "primary", "path": str(path), "media_type": "text/plain"}
        return primary, (primary,), 1

    def _single_cell(self, root: Path, *, valid: bool):
        import h5py

        path = root / "object.h5ad"
        with h5py.File(path, "w") as handle:
            obs = handle.create_group("obs")
            obs.attrs["_index"] = "_index"
            obs.create_dataset("_index", data=[b"cell-1", b"cell-2"])
            if valid:
                var = handle.create_group("var")
                var.attrs["_index"] = "_index"
                var.create_dataset("_index", data=[b"gene-1"])
        primary = {"role": "primary", "path": str(path), "media_type": "application/x-hdf5"}
        return primary, (primary,), 2

    def _structure(self, root: Path, *, valid: bool):
        text = (
            "ATOM      1  CA  ALA A   1      11.000  12.000  13.000  1.00 20.00           C\n"
            if valid else "HEADER empty\n"
        )
        path = self._file(root, "structure.pdb", text)
        primary = {"role": "primary", "path": str(path), "media_type": "chemical/x-pdb"}
        return primary, (primary,), 1

    def _archive(self, root: Path, *, valid: bool, model: bool = False):
        path = root / "bundle.zip"
        member = "model.json" if model else "results.tsv"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(member, "{}" if model else "id\tvalue\nA\t1\n")
            if valid:
                archive.writestr(
                    "manifest.json",
                    json.dumps({
                        "schema_version": 1,
                        "artifact_family": "model" if model else "analysis",
                        "record_count": 1,
                        "members": [member],
                    }),
                )
        primary = {"role": "primary", "path": str(path), "media_type": "application/zip"}
        return primary, (primary,), 1

    def _figure(self, root: Path, *, valid: bool):
        text = (
            '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0L1 1"/></svg>'
            if valid else '<svg xmlns="http://www.w3.org/2000/svg"></svg>'
        )
        path = self._file(root, "figure.svg", text)
        primary = {"role": "primary", "path": str(path), "media_type": "image/svg+xml"}
        return primary, (primary,), 1

    def _configuration(self, root: Path, *, valid: bool):
        text = "receptor: A\nligand: B\n" if valid else "receptor: TODO\n"
        path = self._file(root, "config.yaml", text)
        primary = {"role": "primary", "path": str(path), "media_type": "application/yaml"}
        return primary, (primary,), 2 if valid else 1

    def _html(self, root: Path, *, valid: bool):
        text = "<html><body>Interactive structure view</body></html>" if valid else "<html></html>"
        path = self._file(root, "view.html", text)
        primary = {"role": "primary", "path": str(path), "media_type": "text/html"}
        return primary, (primary,), 1

    def _functional(self, root: Path, *, valid: bool):
        background = "25/100" if valid else "25/1"
        path = self._file(
            root,
            "enrichment.tsv",
            "term_id\tterm_name\tp_value\tadjusted_p_value\tgene_ratio\tbackground_ratio\tgene_set_size\toverlap_genes\n"
            f"GO:1\tDNA repair\t0.01\t0.02\t1/1\t{background}\t25\tTP53\n",
        )
        primary = {"role": "primary", "path": str(path), "media_type": "text/tab-separated-values"}
        return primary, (primary,), 1

    def test_every_registered_profile_has_a_positive_and_scientific_negative_fixture(self):
        factories = {
            "functional-enrichment-v2": self._functional,
            "bulk-assay-summary-v1": self._bulk,
            "statistical-results-v1": self._table,
            "genomic-records-v1": self._genomic,
            "sequence-phylogeny-v1": self._sequence,
            "count-matrix-v1": self._matrix,
            "single-cell-object-v1": self._single_cell,
            "single-cell-results-v1": self._json,
            "spatial-results-v1": self._json,
            "structure-coordinate-v1": self._structure,
            "structure-analysis-v1": self._json,
            "analysis-archive-v1": self._archive,
            "figure-package-v1": self._figure,
            "scientific-report-v1": self._json,
            "configuration-v1": self._configuration,
            "interactive-html-v1": self._html,
            "svg-figure-v1": self._figure,
            "model-bundle-v1": lambda root, *, valid: self._archive(root, valid=valid, model=True),
        }
        self.assertEqual(set(factories), set(registered_semantic_profiles()))
        self.assertEqual(set(factories), set(_PROFILE_VALIDATORS))
        metadata = {
            "analysis_mode": "ora",
            "input_accounting": {"tested_entities": 1, "background_entities": 100},
        }
        for profile, factory in factories.items():
            with self.subTest(profile=profile, fixture="positive"):
                with tempfile.TemporaryDirectory() as temporary:
                    primary, payloads, record_count = factory(Path(temporary), valid=True)
                    _PROFILE_VALIDATORS[profile](metadata, primary, payloads, record_count)
            with self.subTest(profile=profile, fixture="negative"):
                with tempfile.TemporaryDirectory() as temporary:
                    primary, payloads, record_count = factory(Path(temporary), valid=False)
                    with self.assertRaises((ValueError, OSError, KeyError)):
                        _PROFILE_VALIDATORS[profile](metadata, primary, payloads, record_count)

    def test_figure_family_decodes_pdf_and_tiff_content(self):
        import fitz
        from PIL import Image

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf = root / "figure.pdf"
            document = fitz.open()
            page = document.new_page(width=144, height=96)
            page.insert_text((12, 24), "Observed figure")
            document.save(pdf)
            document.close()
            primary = {"role": "primary", "path": str(pdf), "media_type": "application/pdf"}
            _PROFILE_VALIDATORS["figure-package-v1"]({}, primary, (primary,), 1)

            tiff = root / "figure.tiff"
            Image.new("RGB", (32, 24), color=(255, 255, 255)).save(tiff)
            primary = {"role": "primary", "path": str(tiff), "media_type": "image/tiff"}
            _PROFILE_VALIDATORS["figure-package-v1"]({}, primary, (primary,), 1)

            pdf.write_bytes(b"%PDF-1.7\nnot a document")
            primary = {"role": "primary", "path": str(pdf), "media_type": "application/pdf"}
            with self.assertRaisesRegex(ValueError, "cannot be parsed"):
                _PROFILE_VALIDATORS["figure-package-v1"]({}, primary, (primary,), 1)


if __name__ == "__main__":
    unittest.main()
