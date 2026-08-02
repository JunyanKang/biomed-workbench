import tempfile, unittest
from pathlib import Path
from biomed_workbench.implementations.ripseeker import RIPSeekerExecutionError, execute_ripseeker
FAKE_R = r'''#!/usr/bin/env python3
import json, sys
from pathlib import Path
out=Path(sys.argv[-2]); out.mkdir(parents=True); (out/'RIPSeeker_version.txt').write_text(sys.argv[-1]+'\n'); (out/'RIPregions.gff3').write_text('##gff-version 3\nchr1\tRIP\tregion\t1\t10\t.\t+\t.\tID=p1\n'); (out/'seekOutput.RData').write_bytes(b'RData'); (out/'RIPSeeker_result.rds').write_bytes(b'RDS'); (out/'RIPSeeker_validation.json').write_text(json.dumps({'ripseeker_version':sys.argv[-1],'reload_passed':True,'total_region_rows':1,'model_files':[{'file':'seekOutput.RData','objects':['hmm'],'object_count':1}],'result_rds':{'class':['list'],'length':1}}))
'''
class RIPSeekerExecutionTests(unittest.TestCase):
    def test_executes_and_reloads(self):
        with tempfile.TemporaryDirectory(prefix='ripseeker-') as temporary:
            root=Path(temporary); exe=root/'Rscript'; exe.write_text(FAKE_R); exe.chmod(0o755)
            paths=[]
            for name in ('rip','control'):
                bam=root/f'{name}.bam'; bam.write_bytes(b'bam'); Path(str(bam)+'.bai').write_bytes(b'index'); paths.append(bam)
            report=execute_ripseeker({'schema_version':1,'module_id':'bulk-rbp-rna-binding','assay':'rip-seq','rip_bams':[str(paths[0])],'control_bams':[str(paths[1])],'parameters':{}},output_dir=root/'run',report_path=root/'report.json',rscript=str(exe))
            self.assertTrue(report['passed']); self.assertEqual(report['workflow']['version'],'1.28.0'); self.assertEqual(report['validation']['total_region_rows'],1)
    def test_unindexed_bam_is_blocked(self):
        with tempfile.TemporaryDirectory(prefix='ripseeker-invalid-') as temporary:
            root=Path(temporary); bam=root/'x.bam'; bam.write_bytes(b'bam')
            with self.assertRaisesRegex(RIPSeekerExecutionError,'indexed BAM'):
                execute_ripseeker({'schema_version':1,'module_id':'bulk-rbp-rna-binding','assay':'rip-seq','rip_bams':[str(bam)],'control_bams':[str(bam)],'parameters':{}},output_dir=root/'run',report_path=root/'report.json')
if __name__ == '__main__': unittest.main()
