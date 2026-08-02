import tempfile,unittest
from pathlib import Path
from biomed_workbench.implementations.chiapet2 import execute_chiapet2
FAKE=r'''#!/usr/bin/env python3
import sys
from pathlib import Path
if '-v' in sys.argv: print('ChIA-PET2 0.9.3'); raise SystemExit(0)
out=Path(sys.argv[sys.argv.index('-o')+1]); name=sys.argv[sys.argv.index('-n')+1]; out.mkdir(); (out/f'{name}.interactions.intra.bedpe').write_text('chr1\t1\t2\tchr1\t10\t11\n'); (out/f'{name}.interactions.inter.bedpe').write_text('chr1\t1\t2\tchr2\t10\t11\n'); (out/f'{name}.interactions.MICC').write_text('chr1\t1\t2\tchr1\t10\t11\t.\t.\t1\t1\t2\t3\t0.01\n'); (out/f'{name}.QCplot.pdf').write_bytes(b'%PDF-1.4')
'''
class ChIAPET2Tests(unittest.TestCase):
 def test_executes_and_reloads(self):
  with tempfile.TemporaryDirectory(prefix='chiapet2-') as t:
   r=Path(t); exe=r/'ChIA-PET2'; exe.write_text(FAKE); exe.chmod(0o755); f1=r/'r1.fq'; f2=r/'r2.fq'; chrom=r/'chrom.sizes'; idx=r/'genome'; f1.write_text('x'); f2.write_text('x'); chrom.write_text('chr1\t20\n'); Path(str(idx)+'.bwt').write_text('x')
   report=execute_chiapet2({'schema_version':1,'module_id':'bulk-three-dimensional-genome','assay':'chia-pet','fastq_1':str(f1),'fastq_2':str(f2),'chrom_sizes':str(chrom),'bwa_genome_index':str(idx),'parameters':{}},output_dir=r/'out',report_path=r/'report.json',executable=str(exe)); self.assertTrue(report['passed']); self.assertEqual(report['workflow']['version'],'0.9.3')
if __name__=='__main__': unittest.main()
