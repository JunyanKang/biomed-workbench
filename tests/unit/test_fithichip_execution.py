import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from biomed_workbench.implementations.fithichip import COMMIT, execute_fithichip

class Completed:
    def __init__(self, code=0, out='', err=''): self.returncode=code; self.stdout=out; self.stderr=err

class FitHiChIPTests(unittest.TestCase):
    def test_generates_official_config_and_reloads_loops(self):
        with tempfile.TemporaryDirectory(prefix='fithichip-') as temp:
            root=Path(temp); tool=root/'tool'; tool.mkdir(); (tool/'FitHiChIP_HiCPro.sh').write_text('x')
            pairs=root/'pairs.txt'; chrom=root/'chrom.sizes'; peaks=root/'peaks.bed'
            for path in (pairs,chrom,peaks): path.write_text('chr1\t1\t2\n')
            output=root/'out'; report=root/'report.json'
            def fake_run(argv, **kwargs):
                if argv[0]=='git': return Completed(out=COMMIT+'\n')
                config=Path(argv[-1]); values=dict(line.split('=',1) for line in config.read_text().splitlines()); out=Path(values['OutDir']); target=out/'FitHiC_BiasCorr'; target.mkdir(parents=True); (target/'FitHiChIP.interactions_FitHiC.bed').write_text('h\n1\n'); (target/'FitHiChIP.interactions_FitHiC_Q0.01.bed').write_text('h\n1\n'); return Completed(out='done')
            with patch('biomed_workbench.implementations.fithichip.subprocess.run',side_effect=fake_run):
                result=execute_fithichip({'schema_version':1,'module_id':'bulk-three-dimensional-genome','assay':'hichip','valid_pairs':str(pairs),'chrom_sizes':str(chrom),'peak_file':str(peaks),'fithichip_root':str(tool),'parameters':{}},output_dir=output,report_path=report)
            self.assertTrue(result['passed']); self.assertEqual(result['workflow']['commit'],COMMIT)
            self.assertIn('BINSIZE=5000', (root/'.out.fithichip.config').read_text())

if __name__=='__main__': unittest.main()
