#!/usr/bin/env python3
"""Align declared assembly FASTA records to a declared reference with minimap2."""
from __future__ import annotations
import argparse, hashlib, json, re, shutil, subprocess, sys
from pathlib import Path

class AlignmentError(ValueError):
    """Raised when a declared assembly-alignment contract is invalid."""

def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()

def fasta_ids(path: Path) -> dict[str, int]:
    if path.is_symlink() or not path.is_file(): raise AlignmentError("FASTA must be a stable regular file")
    ids, current, size = {}, None, 0
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith(">"):
            if current is not None: ids[current] = size
            current, size = line[1:].split()[0], 0
            if not current or current in ids: raise AlignmentError(f"invalid or duplicate FASTA identifier at line {n}")
        elif line:
            if current is None or re.search(r"[^ACGTRYSWKMBDHVNacgtryswkmbdhvn-]", line): raise AlignmentError(f"invalid DNA FASTA sequence at line {n}")
            size += len(line.replace("-", ""))
    if current is not None: ids[current] = size
    if not ids or any(v == 0 for v in ids.values()): raise AlignmentError("FASTA requires nonempty records")
    return ids

def parse_paf(path: Path, queries: dict[str, int], targets: dict[str, int]) -> dict[str, object]:
    rows, seen_q, seen_t = 0, set(), set()
    intervals: dict[str, list[tuple[int, int]]] = {record_id: [] for record_id in queries}
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        f = line.split("\t")
        if len(f) < 12: raise AlignmentError(f"PAF line {n} has fewer than 12 fields")
        try: ql, qs, qe, tl, ts, te, match, block, mapq = map(int, (f[1],f[2],f[3],f[6],f[7],f[8],f[9],f[10],f[11]))
        except ValueError as e: raise AlignmentError(f"PAF line {n} has invalid numeric fields") from e
        if f[0] not in queries or f[5] not in targets or ql != queries[f[0]] or tl != targets[f[5]] or not (0 <= qs < qe <= ql and 0 <= ts < te <= tl and 0 <= match <= block and 0 <= mapq <= 255): raise AlignmentError(f"PAF line {n} violates record identity or coordinates")
        rows += 1; intervals[f[0]].append((qs, qe)); seen_q.add(f[0]); seen_t.add(f[5])
    if not rows: raise AlignmentError("minimap2 produced no reloadable PAF alignments")
    covered: dict[str, int] = {}
    for record_id, spans in intervals.items():
        end = total = 0
        for start, stop in sorted(spans):
            if stop > max(start, end): total += stop - max(start, end)
            end = max(end, stop)
        covered[record_id] = total
    return {"rows": rows, "query_records_aligned": sorted(seen_q), "query_records_unaligned": sorted(set(queries)-seen_q), "target_records_aligned": sorted(seen_t), "target_records_unaligned": sorted(set(targets)-seen_t), "query_covered_bases": covered, "query_coverage": {record_id: covered[record_id] / queries[record_id] for record_id in sorted(queries)}, "query_length": sum(queries.values())}

def main() -> int:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--reference",type=Path,required=True); p.add_argument("--query",type=Path,required=True); p.add_argument("--preset",choices=("asm5","asm10","asm20"),required=True); p.add_argument("--output-dir",type=Path,required=True); p.add_argument("--minimum-query-coverage",type=float,default=0.0); p.add_argument("--minimap2",default="minimap2"); a=p.parse_args()
    ref, qry = fasta_ids(a.reference), fasta_ids(a.query)
    if not 0 <= a.minimum_query_coverage <= 1: raise AlignmentError("minimum query coverage must be in [0, 1]")
    exe=shutil.which(a.minimap2) if not Path(a.minimap2).is_file() else a.minimap2
    if not exe: raise AlignmentError("minimap2 is unavailable in the existing environment")
    version=subprocess.run([str(exe),"--version"],text=True,capture_output=True,check=False,timeout=30).stdout.strip()
    if not re.fullmatch(r"2\.3[01](?:-r\d+)?",version): raise AlignmentError(f"unvalidated minimap2 version: {version}")
    if a.output_dir.exists(): raise AlignmentError("output directory must be new")
    a.output_dir.mkdir(parents=True); paf=a.output_dir/"alignment.paf"
    run=subprocess.run([str(exe),"-x",a.preset,str(a.reference),str(a.query)],text=True,capture_output=True,check=False,timeout=300)
    if run.returncode: raise AlignmentError(run.stderr[-4000:])
    paf.write_text(run.stdout,encoding="utf-8"); evidence=parse_paf(paf,qry,ref)
    below = sorted(record_id for record_id, coverage in evidence["query_coverage"].items() if coverage < a.minimum_query_coverage)
    if below: raise AlignmentError(f"query records below declared coverage threshold: {', '.join(below)}")
    report={"passed":True,"module_id":"assembly-reference-alignment","module_version":"0.1.0","tool_versions":{"minimap2":version},"parameters":{"preset":a.preset,"minimum_query_coverage":a.minimum_query_coverage},"input":{"reference_sha256":digest(a.reference),"query_sha256":digest(a.query)},"alignment":evidence,"quality_gate_ids":["assembly-identity","assembly-paf-reload","assembly-claim-boundary"],"claim_boundary":"PAF alignment establishes declared sequence alignment evidence only, not variants, haplotypes, synteny, structural variation, gene orthology, or functional conservation."}
    (a.output_dir/"assembly-alignment-report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return 0
if __name__ == "__main__":
    try: raise SystemExit(main())
    except AlignmentError as e: print(f"assembly-reference-alignment: {e}",file=sys.stderr); raise SystemExit(2)
