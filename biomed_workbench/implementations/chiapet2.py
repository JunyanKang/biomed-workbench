"""Pinned ChIA-PET2 0.9.3 raw-read execution and output reload."""
from __future__ import annotations
import hashlib, json, re, shutil, subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
VERSION="0.9.3"; COMMIT="e120726d6440b24034f70bc3c51c17f351fef496"; SOURCE="https://github.com/GuipengLi/ChIA-PET2"
class ChIAPET2ExecutionError(ValueError): pass
def sha256(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
def stable(value:object,label:str)->Path:
    if not isinstance(value,str) or not value.strip(): raise ChIAPET2ExecutionError(f'{label} must be a local path')
    p=Path(value).expanduser()
    if p.is_symlink() or not p.is_file(): raise ChIAPET2ExecutionError(f'{label} must be a readable non-symlink file: {p}')
    return p.resolve()
def execute_chiapet2(request:dict[str,Any],*,output_dir:Path,report_path:Path,executable:str='ChIA-PET2',timeout_seconds:int=172800)->dict[str,Any]:
    if request.get('schema_version')!=1 or request.get('module_id')!='bulk-three-dimensional-genome' or str(request.get('assay','')).lower()!='chia-pet': raise ChIAPET2ExecutionError('request must target bulk-three-dimensional-genome assay=chia-pet schema version 1')
    fq1=stable(request.get('fastq_1'),'fastq_1'); fq2=stable(request.get('fastq_2'),'fastq_2'); chrom=stable(request.get('chrom_sizes'),'chrom_sizes')
    genome_index=str(request.get('bwa_genome_index','')).strip()
    if not genome_index or not any(Path(genome_index+s).is_file() for s in ('.bwt','.0123')): raise ChIAPET2ExecutionError('bwa_genome_index must reference an existing BWA index prefix')
    p=request.get('parameters',{})
    allowed={'name','linker_a','linker_b','mode','mismatches','keep_empty','threads','short_reads','macs2_parameters','mapq','pet_cutoff','slop','extend','minimum_read_length'}
    if not isinstance(p,dict) or set(p)-allowed: raise ChIAPET2ExecutionError('unknown ChIA-PET2 parameter')
    v={'name':str(p.get('name','chiapet')).strip(),'linker_a':str(p.get('linker_a','GTTGGATAAG')).upper(),'linker_b':str(p.get('linker_b','GTTGGAATGT')).upper(),'mode':int(p.get('mode',0)),'mismatches':int(p.get('mismatches',0)),'keep_empty':int(p.get('keep_empty',0)),'threads':int(p.get('threads',1)),'short_reads':int(p.get('short_reads',0)),'macs2_parameters':str(p.get('macs2_parameters','-q 0.05')),'mapq':int(p.get('mapq',30)),'pet_cutoff':int(p.get('pet_cutoff',2)),'slop':int(p.get('slop',100)),'extend':int(p.get('extend',500)),'minimum_read_length':int(p.get('minimum_read_length',15))}
    if not re.fullmatch(r'[A-Za-z0-9._-]+',v['name']) or not re.fullmatch(r'[ACGTN]+',v['linker_a']) or not re.fullmatch(r'[ACGTN]+',v['linker_b']): raise ChIAPET2ExecutionError('name or linker sequence is invalid')
    if v['mode'] not in {0,1,2} or v['keep_empty'] not in {0,1,2} or v['short_reads'] not in {0,1} or min(v['threads'],v['mapq'],v['pet_cutoff'],v['minimum_read_length'])<1 or min(v['mismatches'],v['slop'],v['extend'])<0: raise ChIAPET2ExecutionError('ChIA-PET2 numeric parameter is outside the official range')
    if output_dir.exists() or report_path.exists(): raise ChIAPET2ExecutionError('output directory and report path must not already exist')
    exe=shutil.which(executable) if '/' not in executable else str(stable(executable,'ChIA-PET2 executable'))
    if not exe: raise ChIAPET2ExecutionError(f'ChIA-PET2 executable not found: {executable}')
    ver=subprocess.run([exe,'-v'],capture_output=True,text=True,check=False,timeout=30); vertext=(ver.stdout+ver.stderr).strip()
    if ver.returncode!=0 or VERSION not in vertext: raise ChIAPET2ExecutionError(f'ChIA-PET2 {VERSION} required; observed {vertext!r}')
    argv=[exe,'-g',genome_index,'-b',str(chrom),'-f',str(fq1),'-r',str(fq2),'-A',v['linker_a'],'-B',v['linker_b'],'-o',str(output_dir),'-n',v['name'],'-m',str(v['mode']),'-e',str(v['mismatches']),'-k',str(v['keep_empty']),'-t',str(v['threads']),'-d',str(v['short_reads']),'-M',v['macs2_parameters'],'-Q',str(v['mapq']),'-C',str(v['pet_cutoff']),'-S',str(v['slop']),'-E',str(v['extend']),'-l',str(v['minimum_read_length'])]
    output_dir.parent.mkdir(parents=True,exist_ok=True); completed=subprocess.run(argv,capture_output=True,text=True,check=False,timeout=timeout_seconds)
    if completed.returncode!=0: raise ChIAPET2ExecutionError(f'ChIA-PET2 failed: {completed.stderr[-4000:]}')
    intra=list(output_dir.rglob(f"{v['name']}.interactions.intra.bedpe")); inter=list(output_dir.rglob(f"{v['name']}.interactions.inter.bedpe")); micc=list(output_dir.rglob(f"{v['name']}.interactions.MICC")); qc=list(output_dir.rglob(f"{v['name']}.QCplot.pdf"))
    if not intra or not inter or not micc or not qc or any(x.stat().st_size==0 for x in intra+inter+micc+qc): raise ChIAPET2ExecutionError('ChIA-PET2 completed without nonempty intra/inter loops, MICC statistics, and QC PDF')
    log=output_dir/'chiapet2.execution.log'; log.write_text('STDOUT\n'+completed.stdout+'\nSTDERR\n'+completed.stderr)
    impl=Path(__file__).resolve(); rec=lambda xs:[{'path':str(x.relative_to(output_dir)),'bytes':x.stat().st_size,'sha256':sha256(x)} for x in xs]
    report={'schema_version':1,'module_id':'bulk-three-dimensional-genome','assay':'chia-pet','passed':True,'executed_at':datetime.now(timezone.utc).isoformat(),'workflow':{'name':'ChIA-PET2','version':VERSION,'commit':COMMIT,'source':SOURCE,'version_probe':vertext},'implementation':{'path':str(impl.relative_to(impl.parents[2])),'sha256':sha256(impl)},'inputs':{'fastq_1':sha256(fq1),'fastq_2':sha256(fq2),'chrom_sizes':sha256(chrom),'bwa_genome_index':genome_index},'parameters':v,'outputs':{'intra_loops':rec(intra),'inter_loops':rec(inter),'micc':rec(micc),'qc':rec(qc)},'provenance':{'log_sha256':sha256(log)},'claim_boundary':'ChIA-PET2 loops are protein-anchored contact enrichment; statistical contacts do not by themselves establish regulatory causality.'}
    report_path.parent.mkdir(parents=True,exist_ok=True); report_path.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n'); return report
