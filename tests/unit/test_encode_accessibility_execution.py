import gzip, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from biomed_workbench.implementations.encode_accessibility import PIPELINE_COMMIT, execute_encode_accessibility

class Completed:
    def __init__(self, code=0, out='', err=''): self.returncode=code; self.stdout=out; self.stderr=err

class EncodeAccessibilityTests(unittest.TestCase):
    def test_dnase_mode_generates_wdl_inputs_and_reloads_outputs(self):
        with tempfile.TemporaryDirectory(prefix='encode-access-') as temp:
            root=Path(temp); tool=root/'tool'; tool.mkdir(); (tool/'atac.wdl').write_text('workflow atac {}')
            caper=root/'caper'; caper.write_text('x'); caper.chmod(0o755); fq=root/'r1.fq'; genome=root/'genome.tsv'; fq.write_text('x'); genome.write_text('genome_name\thg38\n')
            output=root/'out'; report=root/'report.json'
            def fake_run(argv, **kwargs):
                if argv[0]=='git': return Completed(out=PIPELINE_COMMIT+'\n')
                if '--version' in argv: return Completed(out='caper 2.3.1')
                output.mkdir(); metadata=output/'metadata.json'; metadata.write_text('{"status":"Succeeded"}'); (output/'sample_qc.json').write_text('{}'); (output/'sample_qc.html').write_text('<html>ok</html>')
                execution=output/'atac'/'workflow'/'call-qc_report'/'execution'; execution.mkdir(parents=True)
                (output/'metadata.json').replace(execution/'metadata.json'); (execution/'sample_qc.json').write_text('{}'); (execution/'sample_qc.html').write_text('<html>ok</html>')
                with gzip.open(execution/'sample.optimal_peak.narrowPeak.gz','wt') as handle: handle.write('chr1\t1\t20\tpeak\n')
                (execution/'sample.fc.signal.bigwig').write_bytes(b'\x26\xfc\x8f\x88signal');
                (output/'metadata.json').write_text('{"status":"Succeeded"}'); return Completed(out='done')
            with patch('biomed_workbench.implementations.encode_accessibility.subprocess.run',side_effect=fake_run), patch('biomed_workbench.implementations.encode_accessibility.shutil.which',return_value=str(caper)):
                result=execute_encode_accessibility({'schema_version':1,'module_id':'bulk-chromatin-accessibility','assay':'dnase-seq','pipeline_root':str(tool),'genome_tsv':str(genome),'fastq_replicates':[{'fastq_1':[str(fq)]}],'parameters':{'duplicate_marker':'sambamba','enable_gc_bias':False,'enable_fraglen_stat':False,'enable_idr':False,'fraglen_stat_picard_java_heap':'1G'}},output_dir=output,report_path=report,caper_executable=str(caper))
            self.assertTrue(result['passed']); inputs=(root/'.out.encode-accessibility.inputs.json').read_text(); self.assertIn('"atac.pipeline_type": "dnase"',inputs); self.assertIn('"atac.dup_marker": "sambamba"',inputs); self.assertIn('"atac.enable_gc_bias": false',inputs); self.assertIn('"atac.enable_fraglen_stat": false',inputs); self.assertIn('"atac.enable_idr": false',inputs); self.assertIn('"atac.fraglen_stat_picard_java_heap": "1G"',inputs)
            self.assertEqual(result['reloaded']['peak_intervals'],1)

    def test_official_unfiltered_bam_input_is_supported(self):
        with tempfile.TemporaryDirectory(prefix='encode-access-bam-') as temp:
            root=Path(temp); tool=root/'tool'; tool.mkdir(); (tool/'atac.wdl').write_text('workflow atac {}')
            caper=root/'caper'; caper.write_text('x'); caper.chmod(0o755); bam=root/'rep1.bam'; genome=root/'genome.tsv'; header=b'@HD\tVN:1.6\tSO:coordinate\n'; bam.write_bytes(b'BAM\x01'+len(header).to_bytes(4,'little',signed=True)+header); genome.write_text('genome_name\thg38\n')
            output=root/'out'; report=root/'report.json'
            def fake_run(argv, **kwargs):
                if argv[0]=='git': return Completed(out=PIPELINE_COMMIT+'\n')
                if '--version' in argv: return Completed(out='caper 2.3.1')
                output.mkdir(); (output/'metadata.json').write_text('{"status":"Succeeded"}'); execution=output/'atac'/'workflow'/'call-qc_report'/'execution'; execution.mkdir(parents=True)
                (execution/'sample_qc.json').write_text('{}'); (execution/'sample_qc.html').write_text('<h1>QC Report</h1><table><tr><td>ok</td></tr></table>')
                with gzip.open(execution/'sample.optimal_peak.narrowPeak.gz','wt') as handle: handle.write('chr1\t1\t20\tpeak\n')
                (execution/'sample.fc.signal.bigwig').write_bytes(b'\x26\xfc\x8f\x88signal'); return Completed(out='done')
            with patch('biomed_workbench.implementations.encode_accessibility.subprocess.run',side_effect=fake_run), patch('biomed_workbench.implementations.encode_accessibility.shutil.which',return_value=str(caper)):
                result=execute_encode_accessibility({'schema_version':1,'module_id':'bulk-chromatin-accessibility','assay':'atac-seq','pipeline_root':str(tool),'genome_tsv':str(genome),'bam_replicates':[{'bam':str(bam),'paired_end':True}],'bam_provenance':{'producer':'Bowtie2','producer_version':'2.5.5','source':'https://bowtie-bio.sourceforge.net/bowtie2/','parameters':{'multimapping':5},'source_files':[str(bam)],'quality_files':[]}},output_dir=output,report_path=report,caper_executable=str(caper))
            inputs=json.loads((root/'.out.encode-accessibility.inputs.json').read_text())
            self.assertEqual(inputs['atac.bams'],[str(bam.resolve())]); self.assertTrue(inputs['atac.paired_end']); self.assertEqual(result['input_mode'],'unfiltered_bam'); self.assertEqual(result['upstream_bam_provenance']['producer_version'],'2.5.5')

if __name__=='__main__': unittest.main()
