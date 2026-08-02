import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from biomed_workbench.implementations.capcmap import COMMIT, execute_capcmap

class Completed:
    def __init__(self, code=0, out='', err=''): self.returncode=code; self.stdout=out; self.stderr=err

class CapCMapTests(unittest.TestCase):
    def test_generates_official_config_and_reloads_target_profiles(self):
        with tempfile.TemporaryDirectory(prefix='capcmap-') as temp:
            root=Path(temp); tool=root/'tool'; tool.mkdir(); (tool/'capC-map').write_text('x'); (tool/'VERSION').write_text('1.1.3\n')
            files=[root/name for name in ('r1.fq','r2.fq','targets.bed','frags.bed')]
            for path in files: path.write_text('chr1\t1\t2\ttarget\n')
            index=root/'mm'; Path(str(index)+'.1.ebwt').write_text('x'); output=root/'out'; report=root/'report.json'
            def fake_run(argv, **kwargs):
                if argv[0]=='git': return Completed(out=COMMIT+'\n')
                out=Path(argv[-1]); out.mkdir(); (out/'reads_validpairs_target.pairs').write_text('x\n'); (out/'reads_rawpileup_target.bdg').write_text('x\n'); (out/'reads_bin_500_1000_RPM_target.bdg').write_text('x\n'); (out/'reads_report.dat').write_text('x\n'); return Completed(out='done')
            with patch('biomed_workbench.implementations.capcmap.subprocess.run',side_effect=fake_run):
                result=execute_capcmap({'schema_version':1,'module_id':'bulk-three-dimensional-genome','assay':'capture-c','fastq_1':str(files[0]),'fastq_2':str(files[1]),'targets_bed':str(files[2]),'restriction_fragments_bed':str(files[3]),'bowtie_index':str(index),'capcmap_root':str(tool),'parameters':{}},output_dir=output,report_path=report)
            self.assertTrue(result['passed']); self.assertEqual(result['workflow']['version'],'1.1.3'); self.assertIn('BIN 500 1000',(root/'.out.capcmap.config').read_text())

if __name__=='__main__': unittest.main()
