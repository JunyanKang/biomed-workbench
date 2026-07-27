#!/usr/bin/env python3
"""Execute planted MACS3, motifmatchr, chromVAR, and LinkPeaks evidence."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


MODULE_ID = "single-cell-atac-regulatory"
MODULE_ROOT = BUILTIN_ROOT / MODULE_ID
MACS3_TEMPLATE = MODULE_ROOT / "templates" / "call_macs3_fragments.py"
REGULATORY_TEMPLATE = MODULE_ROOT / "templates" / "run_atac_regulatory.R"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], environment: dict[str, str], *, timeout: int = 1200) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, check=False, timeout=timeout)
    if completed.returncode != 0:
        raise RuntimeError(
            f"ATAC regulatory command failed ({completed.returncode}): {' '.join(command[:3])}\n"
            f"stderr:\n{completed.stderr[-8000:]}\nstdout:\n{completed.stdout[-4000:]}"
        )
    return completed


def write_fragments(work: Path) -> None:
    rng = random.Random(1201)
    selected = [f"cell-{index:03d}" for index in range(1, 21)]
    excluded = [f"excluded-{index:02d}" for index in range(1, 5)]
    records: list[tuple[str, int, int, str, int]] = []
    for barcode in selected:
        for center in (20_000, 60_000):
            for _ in range(60):
                start = center + rng.randint(-120, 120)
                records.append(("chr1", start, start + rng.randint(70, 160), barcode, 1))
        for _ in range(20):
            start = rng.randint(1_000, 110_000)
            records.append(("chr1", start, start + rng.randint(50, 140), barcode, 1))
    for barcode in excluded:
        for _ in range(180):
            start = 95_000 + rng.randint(-120, 120)
            records.append(("chr1", start, start + rng.randint(70, 160), barcode, 1))
    records.sort(key=lambda value: (value[0], value[1], value[2], value[3]))
    with gzip.open(work / "fragments.tsv.gz", "wt", encoding="utf-8") as handle:
        for record in records:
            handle.write("\t".join(map(str, record)) + "\n")
    (work / "barcodes.tsv").write_text("\n".join(selected) + "\n", encoding="utf-8")


def fixture_r(work: Path) -> str:
    return f"""
suppressPackageStartupMessages({{library(Matrix);library(Biostrings);library(TFBSTools)}})
set.seed(1202)
n <- 180L; cells <- paste0('cell-', sprintf('%03d', seq_len(n))); truth <- rep(c('A','B','C'), each=60)
chrom <- rep(c('chr1','chr2'), each=60); starts <- c(seq(1000, by=500, length.out=60), seq(1000, by=500, length.out=60)); ends <- starts + 99L
peak_ids <- paste(chrom, starts, ends, sep='-')
atac <- matrix(rpois(120*n, 1.2), nrow=120, dimnames=list(peak_ids,cells))
atac[1:15,truth=='A'] <- atac[1:15,truth=='A'] + matrix(rpois(15*60,8),15)
atac[20:34,truth=='B'] <- atac[20:34,truth=='B'] + matrix(rpois(15*60,8),15)
latent <- scale(as.numeric(atac[1,]) + rnorm(n,0,.2))[,1]
genes <- paste0('GENE',sprintf('%03d',1:18)); rna <- matrix(rpois(18*n,2),nrow=18,dimnames=list(genes,cells))
rna[1,] <- pmax(0,round(4 + 2.8*as.numeric(atac[1,]) + rnorm(n,0,1)))
rna[2,] <- pmax(0,round(4 + 2.4*as.numeric(atac[20,]) + rnorm(n,0,1)))
saveRDS(as(atac,'dgCMatrix'),{str(work / 'atac-counts.rds')!r}); saveRDS(as(rna,'dgCMatrix'),{str(work / 'rna-counts.rds')!r})
write.table(data.frame(cell_id=cells,truth=truth,latent=latent),{str(work / 'cells.tsv')!r},sep='\t',quote=FALSE,row.names=FALSE)
write.table(data.frame(peak_id=peak_ids,seqnames=chrom,start=starts,end=ends),{str(work / 'peaks.tsv')!r},sep='\t',quote=FALSE,row.names=FALSE)
gene_start <- seq(1200,by=1200,length.out=18); write.table(data.frame(gene_id=paste0('ENSG',sprintf('%06d',1:18)),gene_name=genes,seqnames='chr1',start=gene_start,end=gene_start+500,strand='+'),{str(work / 'genes.tsv')!r},sep='\t',quote=FALSE,row.names=FALSE)
bases <- c('A','C','G','T'); sequences <- replicate(120,paste(sample(bases,100,replace=TRUE),collapse=''))
insert <- function(sequence,motif,position=35) paste0(substr(sequence,1,position-1),motif,substr(sequence,position+nchar(motif),nchar(sequence)))
sequences[1:15] <- vapply(sequences[1:15],insert,character(1),motif='ACGTACGT')
sequences[20:34] <- vapply(sequences[20:34],insert,character(1),motif='TTGCAATG')
dna <- DNAStringSet(sequences); names(dna) <- peak_ids; writeXStringSet(dna,{str(work / 'peak-sequences.fa')!r})
make_motif <- function(id,sequence) {{m<-matrix(1,nrow=4,ncol=nchar(sequence),dimnames=list(bases,NULL));for(i in seq_len(nchar(sequence)))m[substr(sequence,i,i),i]<-100;PFMatrix(ID=id,name=id,matrixClass='fixture',strand='+',bg=c(A=.25,C=.25,G=.25,T=.25),profileMatrix=m)}}
motifs <- PFMatrixList(MOTIF_A=make_motif('MOTIF_A','ACGTACGT'),MOTIF_B=make_motif('MOTIF_B','TTGCAATG'),MOTIF_C=make_motif('MOTIF_C','GGGGCCCC'))
saveRDS(motifs,{str(work / 'motifs.rds')!r})
"""


def evaluate_r(work: Path) -> str:
    return f"""
suppressPackageStartupMessages(library(jsonlite))
d <- read.delim({str(work / 'deviations.tsv')!r},check.names=FALSE); c <- read.delim({str(work / 'cells.tsv')!r},check.names=FALSE); d <- merge(d,c,by='cell_id')
z <- aggregate(z~motif_id+truth,d,mean); za <- z$z[z$motif_id=='MOTIF_A' & z$truth=='A']; zc <- z$z[z$motif_id=='MOTIF_A' & z$truth=='C']
m <- read.delim({str(work / 'motif-matches.tsv')!r},check.names=FALSE); motif_a_planted <- sum(m$motif_id=='MOTIF_A' & m$peak_id %in% read.delim({str(work / 'peaks.tsv')!r})$peak_id[1:15])
l <- read.delim({str(work / 'links.tsv')!r},check.names=FALSE); target <- if(nrow(l)) any(l$gene=='GENE001' & l$score>0.5) else FALSE
cat(toJSON(list(motif_a_group_a_mean_z=za,motif_a_group_c_mean_z=zc,motif_a_group_contrast=za-zc,motif_a_planted_matches=motif_a_planted,peak_gene_link_rows=nrow(l),target_gene1_positive_link=target),auto_unbox=TRUE,digits=NA))
"""


def verify(python: Path, rscript: Path) -> dict[str, object]:
    python = python.expanduser().absolute()
    rscript = rscript.expanduser().absolute()
    with tempfile.TemporaryDirectory(prefix="biomed-atac-regulatory-") as temporary:
        work = Path(temporary)
        (work / "home").mkdir()
        (work / "cache").mkdir()
        environment = {
            "PATH": str(python.parent) + os.pathsep + str(rscript.parent) + os.pathsep + os.environ.get("PATH", ""),
            "HOME": str(work / "home"), "XDG_CACHE_HOME": str(work / "cache"), "PYTHONHASHSEED": "0", "LANG": "C", "LC_ALL": "C",
        }
        write_fragments(work)
        run([str(rscript), "-e", fixture_r(work)], environment)
        run([
            str(python), str(MACS3_TEMPLATE), "--fragments", str(work / "fragments.tsv.gz"), "--barcode-allowlist", str(work / "barcodes.tsv"),
            "--output-dir", str(work / "macs3"), "--name", "fixture", "--genome-size", "120000", "--qvalue", "0.05",
            "--macs3", str(python.parent / "macs3"), "--report", str(work / "macs3.json"),
        ], environment)
        run([
            str(rscript), str(REGULATORY_TEMPLATE), "--peak-counts-rds", str(work / "atac-counts.rds"), "--cell-metadata", str(work / "cells.tsv"),
            "--peak-metadata", str(work / "peaks.tsv"), "--peak-sequences-fasta", str(work / "peak-sequences.fa"), "--motifs-rds", str(work / "motifs.rds"),
            "--rna-counts-rds", str(work / "rna-counts.rds"), "--gene-metadata", str(work / "genes.tsv"), "--output-rds", str(work / "regulatory.rds"),
            "--motif-match-table", str(work / "motif-matches.tsv"), "--deviation-table", str(work / "deviations.tsv"), "--background-table", str(work / "backgrounds.tsv"),
            "--link-table", str(work / "links.tsv"), "--report", str(work / "regulatory.json"), "--seed", "1203", "--background-iterations", "50",
            "--background-window", "0.1", "--background-bins", "50", "--link-distance", "20000", "--link-min-cells", "5",
            "--link-background-samples", "20", "--link-pvalue", "0.05", "--link-score", "0.05",
        ], environment)
        macs3 = json.loads((work / "macs3.json").read_text(encoding="utf-8"))
        regulatory = json.loads((work / "regulatory.json").read_text(encoding="utf-8"))
        evaluation = json.loads(run([str(rscript), "-e", evaluate_r(work)], environment).stdout)
        narrow = (work / "macs3" / "fixture_peaks.narrowPeak").read_text(encoding="utf-8").splitlines()
        peak_centers = [(int(row.split("\t")[1]) + int(row.split("\t")[2])) / 2 for row in narrow if row.strip()]
        expected_peak_20k = any(abs(center - 20_000) < 1_000 for center in peak_centers)
        expected_peak_60k = any(abs(center - 60_000) < 1_000 for center in peak_centers)
        excluded_peak_absent = not any(abs(center - 95_000) < 1_000 for center in peak_centers)
        if not all((macs3["passed"], regulatory["passed"], expected_peak_20k, expected_peak_60k, excluded_peak_absent)):
            raise RuntimeError("MACS3 planted peaks or barcode exclusion failed")
        if evaluation["motif_a_planted_matches"] < 14 or evaluation["motif_a_group_contrast"] < 2 or not evaluation["target_gene1_positive_link"]:
            raise RuntimeError(f"planted motif, chromVAR, or peak-gene signal was not recovered: {evaluation}")
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        versions = regulatory["versions"]
        return {
            "schema_version": 1, "passed": True, "module_id": MODULE_ID, "module_version": "1.1.0",
            "compatibility_row_id": "agent-protocol-1-macs3-304-signac-116-chromvar-124-motifmatchr-124", "registry_digest": registry.digest,
            "templates": {
                "macs3": {"name": MACS3_TEMPLATE.name, "sha256": sha256(MACS3_TEMPLATE)},
                "regulatory": {"name": REGULATORY_TEMPLATE.name, "sha256": sha256(REGULATORY_TEMPLATE)},
            },
            "tool_versions": {"MACS3": macs3["tool_version"], "Signac": versions["Signac"], "chromVAR": versions["chromVAR"], "motifmatchr": versions["motifmatchr"]},
            "dependency_versions": {key: versions[key] for key in ("Seurat", "Matrix", "GenomicRanges", "Biostrings", "SummarizedExperiment", "TFBSTools", "jsonlite", "digest")} | {"python": subprocess.run([str(python), "-c", "import platform;print(platform.python_version())"], capture_output=True, text=True, check=True).stdout.strip(), "r": versions["R"]},
            "fixture": {"selected_barcodes": 20, "excluded_barcodes": 4, "paired_cells": 180, "peaks": 120, "genes": 18, "motifs": 3},
            "execution": {"macs3_completed": True, "motifmatchr_completed": True, "chromvar_completed": True, "linkpeaks_completed": True, "outputs_reloaded": True},
            "backend_summaries": {"macs3": macs3, "regulatory": {"input": regulatory["input"], "results": regulatory["results"], "parameters": regulatory["parameters"]}},
            "independent_evaluation": {**evaluation, "expected_peak_20k_recovered": expected_peak_20k, "expected_peak_60k_recovered": expected_peak_60k, "excluded_barcode_peak_absent": excluded_peak_absent},
            "scientific_summary": {
                "macs3_frag_peak_calling_executed": True, "barcode_filtering_and_fragment_accounting_reconciled": True,
                "motifmatchr_sequence_scan_executed": True, "gc_accessibility_matched_chromvar_executed": True,
                "signac_linkpeaks_executed": True, "planted_peaks_motif_activity_and_peak_gene_link_recovered": True,
                "paired_cells_source_counts_and_fragments_preserved": True, "method_specific_outputs_retained": True,
                "outputs_reloaded": True, "evaluation_truth_posthoc_only": True, "no_environment_or_compute_infrastructure_managed": True,
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scientific-python", type=Path, required=True)
    parser.add_argument("--rscript", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.scientific_python, args.rscript)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"module_id": MODULE_ID, "passed": True, "tool_versions": report["tool_versions"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
