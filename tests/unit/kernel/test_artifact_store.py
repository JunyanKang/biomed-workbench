import os
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.kernel.artifact_store import ArtifactPayload, ProjectArtifactStore
from biomed_workbench.kernel.state import ProjectState, apply_event
from tests.unit.kernel.test_artifacts import artifact
from tests.unit.kernel.test_context import project_context


class ProjectArtifactStoreTests(unittest.TestCase):
    def test_import_is_content_addressed_deduplicated_and_source_path_free(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "private-sample-name.fastq.gz"
            second = root / "another-name.fq"
            first.write_bytes(b"@read-1\nACGT\n+\n!!!!\n")
            second.write_bytes(first.read_bytes())
            store = ProjectArtifactStore(root / "project-artifacts")

            first_payload = store.import_file(first, role="reads-r1", media_type="application/gzip")
            second_payload = store.import_file(second, role="reads-r1", media_type="application/gzip")

            self.assertEqual(first_payload, second_payload)
            self.assertFalse(Path(first_payload.object_key).is_absolute())
            self.assertNotIn(first.name, first_payload.object_key)
            self.assertNotIn(str(root), str(first_payload.to_dict()))
            self.assertEqual(store.resolve(first_payload).read_bytes(), first.read_bytes())

    def test_resolve_rejects_tampering_and_payload_references_reject_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "reads.fastq"
            source.write_bytes(b"@read-1\nACGT\n+\n!!!!\n")
            store = ProjectArtifactStore(root / "project-artifacts")
            payload = store.import_file(source, role="reads", media_type="text/plain")
            store.resolve(payload).write_bytes(b"changed")

            with self.assertRaisesRegex(ValueError, "digest|size"):
                store.resolve(payload)
            with self.assertRaises(ValueError):
                ArtifactPayload(
                    role="reads",
                    object_key="../outside.fastq",
                    media_type="text/plain",
                    byte_size=1,
                    sha256="0" * 64,
                )

    def test_import_rejects_symlinks_and_non_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "reads.fastq"
            source.write_text("reads", encoding="utf-8")
            symlink = root / "linked.fastq"
            try:
                os.symlink(source, symlink)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks are unavailable")
            store = ProjectArtifactStore(root / "project-artifacts")

            with self.assertRaises(ValueError):
                store.import_file(symlink, role="reads", media_type="text/plain")
            with self.assertRaises(ValueError):
                store.import_file(root, role="reads", media_type="text/plain")

    def test_payload_identity_round_trips_through_project_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "matrix.h5ad"
            source.write_bytes(b"bounded-h5ad-fixture")
            store = ProjectArtifactStore(root / "project-artifacts")
            payload = store.import_file(source, role="matrix", media_type="application/x-hdf5")
            value = artifact(source_artifact_ids=(), payloads=(payload,), content={"cell_count": 4})
            state = ProjectState.create(project_context())
            state = apply_event(
                state,
                "artifact_registered",
                {"artifact": value.to_dict()},
                rationale="Register a content-addressed matrix without retaining its source path.",
            )

            replayed = ProjectState.from_dict(state.to_dict())

            self.assertEqual(replayed.state_digest, state.state_digest)
            self.assertEqual(replayed.artifacts[0].payloads, (payload,))
            self.assertEqual(store.resolve(replayed.artifacts[0].payloads[0]).read_bytes(), source.read_bytes())


if __name__ == "__main__":
    unittest.main()
