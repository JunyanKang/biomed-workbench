import json
import unittest
from pathlib import Path

from biomed_workbench.formats import FormatRegistry, FormatSnapshot, validate_format
from biomed_workbench.kernel.artifact_store import ArtifactPayload
from tests.unit.kernel.test_artifacts import artifact


def valid_snapshot(profile, **overrides):
    compression = profile.compression[0]
    indexes = []
    for requirement in profile.index_requirements:
        if requirement.when_compression and compression not in requirement.when_compression:
            continue
        indexes.extend(requirement.all_of)
        if requirement.one_of:
            indexes.append(requirement.one_of[0])
    values = {
        "profile_id": profile.id,
        "representation": profile.representations[0],
        "compression": compression,
        "indexes": tuple(dict.fromkeys(indexes)),
        "sort_order": profile.sort_orders[0],
        "coordinate_system": profile.coordinate_systems[0] if profile.coordinate_systems else None,
        "genome_build": "GRCh38" if profile.reference_policy == "required" else None,
        "reference_sequence_digest": "a" * 64 if profile.reference_policy == "required" else None,
        "annotation_release": "GENCODE-47" if profile.annotation_policy == "required" else None,
        "identifier_namespace": "ensembl-gene" if profile.identifier_namespace_policy == "required" else None,
        "sample_manifest_digest": "b" * 64 if profile.sample_manifest_policy == "required" else None,
        "orientation": profile.orientations[0],
        "processing_level": profile.processing_levels[0],
        "metadata_fields": profile.required_metadata,
        "payload_roles": profile.required_payload_roles,
    }
    values.update(overrides)
    return FormatSnapshot(**values)


class FormatRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = FormatRegistry.builtin()

    def test_catalog_covers_foundational_omics_formats_with_exact_profiles(self):
        expected = {
            "fastq", "fasta", "sam", "bam", "cram", "vcf", "bcf", "bed", "gtf", "gff3",
            "count-matrix", "h5ad", "loom", "matrix-market", "fragments", "bigwig", "tabular",
        }

        self.assertEqual({profile.name for profile in self.registry.all()}, expected)
        self.assertEqual(len(self.registry.all()), 17)
        self.assertTrue(all(profile.specification_version and profile.specification_source for profile in self.registry.all()))

    def test_every_builtin_profile_accepts_a_complete_snapshot(self):
        for profile in self.registry.all():
            with self.subTest(profile=profile.id):
                self.assertEqual(validate_format(profile, valid_snapshot(profile)), ())

    def test_format_specific_failures_are_machine_readable(self):
        cases = (
            ("bam-v1", {"indexes": ()}, "MISSING_INDEX"),
            ("bed-v1", {"coordinate_system": "one-based-inclusive"}, "COORDINATE_SYSTEM_MISMATCH"),
            ("cram-v3", {"reference_sequence_digest": None}, "REFERENCE_METADATA_MISSING"),
            ("gff3-v126", {"annotation_release": None}, "ANNOTATION_RELEASE_MISSING"),
            ("h5ad-v010", {"sample_manifest_digest": None}, "SAMPLE_MANIFEST_MISSING"),
            ("matrix-market-v2", {"payload_roles": ("matrix",)}, "PAYLOAD_ROLE_MISSING"),
            ("vcf-v45", {"sort_order": "unsorted"}, "SORT_ORDER_MISMATCH"),
            ("count-matrix-v1", {"orientation": "unknown"}, "ORIENTATION_MISMATCH"),
        )
        for profile_id, overrides, code in cases:
            profile = self.registry.get(profile_id)
            with self.subTest(profile=profile_id, code=code):
                findings = validate_format(profile, valid_snapshot(profile, **overrides))
                self.assertIn(code, {finding.code for finding in findings})

    def test_compression_conditional_indexes_are_enforced(self):
        profile = self.registry.get("vcf-v45")

        plain = valid_snapshot(profile, compression="none", indexes=())
        compressed = valid_snapshot(profile, compression="bgzf", indexes=())

        self.assertNotIn("MISSING_INDEX", {finding.code for finding in validate_format(profile, plain)})
        self.assertIn("MISSING_INDEX", {finding.code for finding in validate_format(profile, compressed)})

    def test_scientific_artifact_bridges_to_format_validation(self):
        payload = ArtifactPayload(
            role="matrix",
            object_key=f"sha256/{'c' * 2}/{'c' * 64}/payload",
            media_type="application/x-hdf5",
            byte_size=10,
            sha256="c" * 64,
        )
        value = artifact(
            format_name="h5ad",
            format_version="0.1.0",
            representation="container",
            indexes=(),
            orientation="observations-by-variables",
            processing_level="filtered-counts",
            sort_order="matrix-index-order",
            sample_manifest_digest="b" * 64,
            metadata_fields=("encoding-type", "encoding-version", "obs-index", "var-index"),
            payloads=(payload,),
        )
        profile = self.registry.get("h5ad-v010")

        snapshot = FormatSnapshot.from_artifact(value, profile.id)

        self.assertEqual(validate_format(profile, snapshot), ())
        self.assertEqual(snapshot.payload_roles, ("matrix",))

    def test_unknown_profile_is_never_guessed(self):
        with self.assertRaisesRegex(KeyError, "unknown format profile"):
            self.registry.get("h5ad-latest")

    def test_static_format_pair_fixtures_preserve_accept_and_reject_boundaries(self):
        fixture = Path(__file__).resolve().parents[1] / "fixtures" / "format-pairs.json"
        payload = json.loads(fixture.read_text(encoding="utf-8"))

        self.assertEqual(payload["schema_version"], 1)
        self.assertGreaterEqual(len(payload["cases"]), 8)
        for case in payload["cases"]:
            profile = self.registry.get(case["profile_id"])
            findings = validate_format(profile, FormatSnapshot(profile_id=profile.id, **case["snapshot"]))
            codes = sorted({finding.code for finding in findings})
            with self.subTest(case=case["id"]):
                self.assertEqual(not findings, case["accepted"])
                self.assertEqual(codes, case["expected_codes"])


if __name__ == "__main__":
    unittest.main()
