import unittest

from biomed_workbench.kernel.artifact_store import ArtifactPayload
from biomed_workbench.kernel.artifacts import ScientificArtifact
from biomed_workbench.kernel.identity import digest_value


def artifact(**overrides):
    values = {
        "id": "artifact-counts-01",
        "artifact_type": "count_matrix",
        "schema_version": "1.0",
        "format_name": "h5ad",
        "format_version": "0.11",
        "compression": "gzip",
        "orientation": "cells-by-genes",
        "indexes": ("h5ad-index",),
        "producing_module_id": "single-cell-qc",
        "producing_module_version": "1.0.0",
        "source_artifact_ids": ("artifact-raw-01",),
        "scientific_scope": {"species": "human", "tissue": "retina"},
        "experimental_unit": "independent-organoid-line",
        "denominator": "four-lines-two-batches",
        "processing_level": "quality-controlled",
        "quality_status": "passed",
        "coordinate_system": "zero-based-half-open",
        "genome_build": "GRCh38",
        "annotation_release": "GENCODE-47",
        "identifier_namespace": "ensembl-gene",
        "producer_tool_versions": {"scanpy": "1.11.5", "anndata": "0.11.4"},
        "content": {"cell_count": 1200, "sample_ids": ["s1", "s2", "s3", "s4"]},
    }
    values.update(overrides)
    return ScientificArtifact.create(**values)


class ScientificArtifactTests(unittest.TestCase):
    def test_artifact_records_version_format_scope_denominator_and_digest(self):
        value = artifact()
        payload = value.to_dict()

        self.assertEqual(value.format_version, "0.11")
        self.assertEqual(value.orientation, "cells-by-genes")
        self.assertEqual(value.indexes, ("h5ad-index",))
        self.assertEqual(value.experimental_unit, "independent-organoid-line")
        self.assertEqual(value.denominator, "four-lines-two-batches")
        self.assertEqual(payload["producer_tool_versions"]["scanpy"], "1.11.5")
        self.assertRegex(value.content_digest, r"^[0-9a-f]{64}$")
        self.assertEqual(ScientificArtifact.from_dict(payload), value)

    def test_artifact_is_deeply_immutable_and_detached(self):
        content = {"summary": {"retained": 100}}
        value = artifact(content=content)
        content["summary"]["retained"] = 1

        self.assertEqual(value.content["summary"]["retained"], 100)
        with self.assertRaises(TypeError):
            value.content["summary"]["retained"] = 2

    def test_digest_tampering_is_rejected_on_round_trip(self):
        payload = artifact().to_dict()
        payload["content"]["cell_count"] = 1

        with self.assertRaisesRegex(ValueError, "digest"):
            ScientificArtifact.from_dict(payload)

    def test_payload_descriptors_are_bound_into_artifact_identity(self):
        payload = ArtifactPayload(
            role="matrix",
            object_key=f"sha256/{'a' * 2}/{'a' * 64}/payload",
            media_type="application/x-hdf5",
            byte_size=10,
            sha256="a" * 64,
        )
        value = artifact(payloads=(payload,))
        serialized = value.to_dict()

        self.assertEqual(ScientificArtifact.from_dict(serialized), value)
        serialized["payloads"][0]["byte_size"] = 11
        with self.assertRaisesRegex(ValueError, "digest"):
            ScientificArtifact.from_dict(serialized)

    def test_inline_artifact_digest_remains_backward_compatible(self):
        value = artifact()

        self.assertEqual(value.payloads, ())
        self.assertEqual(value.content_digest, digest_value(value.content))
        self.assertNotIn("payloads", value.to_dict())

    def test_missing_scientific_or_version_metadata_is_rejected(self):
        invalid = (
            {"experimental_unit": ""},
            {"denominator": ""},
            {"format_version": ""},
            {"compression": ""},
            {"orientation": ""},
            {"producing_module_id": None, "producing_module_version": "1.0.0"},
            {"genome_build": "GRCh38", "coordinate_system": None},
            {"quality_status": "looks-good"},
            {"content": {"NCBI_API_KEY": "private"}},
            {"content": {"source": "/Users/researcher/source.tsv"}},
        )
        for overrides in invalid:
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                artifact(**overrides)


if __name__ == "__main__":
    unittest.main()
