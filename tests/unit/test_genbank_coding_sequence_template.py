import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "biomed_workbench" / "modules" / "builtin" / "genbank-coding-sequence-extraction" / "templates" / "run_genbank_coding_sequence_extraction.py"


def artifact():
    return {
        "port": "genbank_record",
        "format": "genbank",
        "format_version": "flatfile",
        "compression": "none",
        "indexes": [],
        "coordinate_system": "one-based-closed-feature-notation",
        "genome_build": "declared-in-project",
        "annotation_release": "declared-in-record",
        "orientation": "record-with-feature-table",
        "metadata_fields": ["record-identifier", "assembly-or-construct-provenance"],
        "representation": "text",
        "sort_order": "unsorted",
        "reference_sequence_digest": None,
        "identifier_namespace": None,
        "sample_manifest_digest": None,
        "payload_roles": [],
        "processing_level": "annotated",
    }


class GenbankCodingSequenceTemplateTests(unittest.TestCase):
    def test_template_executes_annotation_bound_cds_extraction(self):
        record = """LOCUS       TESTREC                   39 bp    DNA     linear   SYN 01-JAN-2000
DEFINITION  synthetic test record.
ACCESSION   TEST000001
VERSION     TEST000001.1
FEATURES             Location/Qualifiers
     source          1..39
                     /organism="synthetic construct"
     CDS             4..15
                     /gene="testgene"
                     /locus_tag="LT0001"
                     /codon_start=1
                     /transl_table=1
                     /translation="MKF"
ORIGIN
        1 cccatgaaat tttaaacccc ggggttttaa acccgggtt
//
"""
        request = {
            "parameters": {"genbank_record": record, "identifier": "LT0001"},
            "artifacts": [artifact()],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request_path = root / "request.json"
            output_path = root / "result.json"
            request_path.write_text(json.dumps(request), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(TEMPLATE), "--request", str(request_path), "--output", str(output_path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            output = json.loads(output_path.read_text(encoding="utf-8")) if output_path.exists() else {}

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(output["module_id"], "genbank-coding-sequence-extraction")
        self.assertEqual(output["result"]["matched_cds_count"], 1)
        self.assertEqual(output["result"]["coding_sequences"][0]["coding_sequence"], "ATGAAATTTTAA")
        self.assertTrue(output["provenance"]["output_digest"])


if __name__ == "__main__":
    unittest.main()
