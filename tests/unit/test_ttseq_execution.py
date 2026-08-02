import tempfile, unittest
from pathlib import Path
from biomed_workbench.implementations.ttseq import TTSeqExecutionError, execute_ttseq
class TTSeqExecutionTests(unittest.TestCase):
    def test_estimates_rates_and_flags_invalid_features(self):
        with tempfile.TemporaryDirectory(prefix='ttseq-') as temporary:
            root=Path(temporary); meta=root/'meta.tsv'; counts=root/'counts.tsv'
            meta.write_text('sample_id\tcondition\tbiological_replicate\tcomponent\tspikein_reads\tspikein_amount\tlabeling_minutes\nnew1\tctrl\t1\tnew\t100\t1\t5\ntotal1\tctrl\t1\ttotal\t100\t1\t5\n')
            counts.write_text('feature_id\tnew1\ttotal1\ng1\t20\t100\ng2\t120\t100\n')
            report=execute_ttseq({'schema_version':1,'module_id':'bulk-nascent-transcription','assay':'tt-seq','counts_tsv':str(counts),'metadata_tsv':str(meta),'parameters':{}},output_dir=root/'out',report_path=root/'report.json')
            self.assertTrue(report['passed']); self.assertEqual(report['status_counts']['estimated'],1); self.assertEqual(report['status_counts']['new_fraction_outside_open_unit_interval'],1)
    def test_unpaired_metadata_is_blocked(self):
        with tempfile.TemporaryDirectory(prefix='ttseq-invalid-') as temporary:
            root=Path(temporary); meta=root/'meta.tsv'; counts=root/'counts.tsv'
            meta.write_text('sample_id\tcondition\tbiological_replicate\tcomponent\tspikein_reads\tspikein_amount\tlabeling_minutes\nnew1\tctrl\t1\tnew\t100\t1\t5\n'); counts.write_text('feature_id\tnew1\ng1\t1\n')
            with self.assertRaisesRegex(TTSeqExecutionError,'exactly one new and one total'):
                execute_ttseq({'schema_version':1,'module_id':'bulk-nascent-transcription','assay':'tt-seq','counts_tsv':str(counts),'metadata_tsv':str(meta),'parameters':{}},output_dir=root/'out',report_path=root/'report.json')
    def test_relative_profile_runs_without_invented_spikein(self):
        with tempfile.TemporaryDirectory(prefix='ttseq-relative-') as temporary:
            root=Path(temporary); meta=root/'meta.tsv'; counts=root/'counts.tsv'
            meta.write_text('sample_id\tcondition\tbiological_replicate\tcomponent\tlabeling_minutes\nnew1\tctrl\t1\tnew\t5\ntotal1\tctrl\t1\ttotal\t5\nnew2\tctrl\t2\tnew\t5\ntotal2\tctrl\t2\ttotal\t5\n')
            counts.write_text('feature_id\tnew1\ttotal1\tnew2\ttotal2\ng1\t20\t100\t40\t200\ng2\t10\t50\t20\t100\n')
            report=execute_ttseq({'schema_version':1,'module_id':'bulk-nascent-transcription','assay':'tt-seq','counts_tsv':str(counts),'metadata_tsv':str(meta),'parameters':{}},output_dir=root/'out',report_path=root/'report.json')
            self.assertEqual(report['parameters']['analysis_mode'],'relative-profile')
            self.assertEqual(report['parameters']['normalization'],'median-ratio')
            self.assertEqual(report['status_counts']['relative_profile'],4)
            self.assertEqual(report['outputs']['kinetic_rates']['rows'],0)
if __name__ == '__main__': unittest.main()
