#!/usr/bin/env python3
"""Build assay-specific bulk sequencing modules from reviewed official workflows."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILTIN = ROOT / "biomed_workbench" / "modules" / "builtin"


SPECS = [
    {
        "id": "bulk-r-loop-mapping",
        "title": "Map bulk R-loops with assay- and sensor-specific evidence",
        "description": "Compare genome-wide R-loop mapping assays without treating the biological target as an assay: DRIP-seq, DRIPc-seq, sDRIP/ssDRIP-seq and qDRIP-seq use S9.6-dependent capture with distinct fragmentation, strandedness and quantification models; R-ChIP and MapR use catalytically inactive RNase H1 sensors; CUT&Tag remains CUT&Tag with its exact hybrid sensor declared.",
        "assays": ["drip-seq", "dripc-seq", "sdrip-seq", "qdrip-seq", "r-chip", "mapr", "cuttag"],
        "workflow_by_assay": {
            "drip-seq": "S9.6 DRIP-seq protocol with restriction-fragment-aware broad signal policy",
            "dripc-seq": "S9.6 DRIPc-seq protocol with RNA-moiety strand-aware signal policy",
            "sdrip-seq": "sonication-based strand-specific S9.6 DRIP protocol",
            "qdrip-seq": "quantitative strand-specific DRIP with declared synthetic internal standards",
            "r-chip": "catalytically inactive RNase H1 R-ChIP protocol",
            "mapr": "dRNH1-MNase MapR protocol",
            "cuttag": "CUT&Tag with the exact S9.6 or dRNH1-derived hybrid sensor declared",
        },
        "sources": [
            "https://pmc.ncbi.nlm.nih.gov/articles/PMC9676068/",
            "https://pmc.ncbi.nlm.nih.gov/articles/PMC6604627/",
            "https://pmc.ncbi.nlm.nih.gov/articles/PMC6870988/",
            "https://pmc.ncbi.nlm.nih.gov/articles/PMC7883053/",
            "https://pmc.ncbi.nlm.nih.gov/articles/PMC7888926/",
            "https://pmc.ncbi.nlm.nih.gov/articles/PMC11840513/",
        ],
        "required_parameters": [
            "assay", "R-loop sensor or antibody", "fragmentation or in situ cleavage model",
            "sequenced moiety and strandedness", "RNase H specificity-control design",
            "matched background control", "synthetic internal-reference identity and addition stage",
            "reference and blacklist", "broad or narrow signal model", "replicate-consensus rule",
            "cross-method comparison policy",
        ],
        "figures": [
            "read and mapping QC", "strand accounting", "internal-reference recovery where applicable",
            "RNase H sensitivity", "replicate correlation", "signal width and genomic annotation",
            "TSS and TTS metaprofiles", "sense and antisense heatmaps", "method-overlap and discordance",
            "gene-body and intergenic distributions", "genome tracks", "orthogonal validation linkage",
        ],
        "maturity": "validated",
        "claim_boundary": "R-loop maps depend on sensor, extraction or in situ context, fragmentation, sequenced moiety, strandedness and normalization. No single S9.6- or dRNH1-derived peak is sufficient to establish a locus-specific three-stranded R-loop or its function without RNase H-sensitive and orthogonal evidence.",
    },
    {
        "id": "bulk-rbp-rna-binding",
        "title": "Map bulk RNA-binding-protein targets with assay-specific controls",
        "description": "Route RIP-seq, eCLIP, iCLIP, HITS-CLIP, PAR-CLIP, or LACE-seq through distinct control, UMI, crosslink, reverse-transcription-stop, enrichment, replicate, site-calling, and claim-boundary policies rather than treating all RNA immunoprecipitation assays as interchangeable.",
        "assays": ["rip-seq", "eclip", "iclip", "hits-clip", "par-clip", "lace-seq"],
        "workflow_by_assay": {
            "rip-seq": "RIPSeeker or count-level IP versus input enrichment with biological replicates",
            "eclip": "ENCODE eCLIP pipeline v2.2",
            "iclip": "nf-core/clipseq 1.0.0 with iCLIP-compatible UMI and site policy",
            "hits-clip": "nf-core/clipseq 1.0.0 with HITS-CLIP-compatible peak policy",
            "par-clip": "nf-core/clipseq 1.0.0 with diagnostic conversion-aware policy",
            "lace-seq": "LACE-seq paper workflow plus caochch/LACEseq commit b8d1193638190c50c8553847ad3a1653544dbe14",
        },
        "sources": [
            "https://www.encodeproject.org/pipelines/ENCPL357ADL/",
            "https://www.encodeproject.org/eclip/",
            "https://nf-co.re/clipseq/1.0.0/",
            "https://www.nature.com/articles/s41556-021-00696-9",
            "https://github.com/caochch/LACEseq/tree/b8d1193638190c50c8553847ad3a1653544dbe14",
            "https://bioconductor.org/packages/RIPSeeker/",
        ],
        "required_parameters": [
            "assay", "library layout", "RBP and antibody", "biological replicates", "matched input or IgG policy",
            "crosslink chemistry", "UMI layout", "reference and annotation", "site or peak caller", "replicate rule",
        ],
        "figures": [
            "read and UMI accounting", "mapping category composition", "library complexity", "replicate concordance",
            "IP versus control enrichment", "site or peak width and annotation", "metaprofile", "motif enrichment",
            "genome or transcript track", "target-validation linkage",
        ],
        "maturity": "validated",
        "claim_boundary": "RIP-seq supports protein-associated transcript enrichment; CLIP-family and LACE-seq can localize binding sites under their assay-specific crosslink and RT-stop model. Neither alone proves direct functional regulation.",
    },
    {
        "id": "bulk-ribosome-profiling",
        "title": "Analyze ribosome profiling and benchmark translated ORFs",
        "description": "Execute Ribo-seq preprocessing, contaminant depletion, alignment, P-site calibration, triplet-periodicity and metagene quality control, translated-ORF calling, gene and ORF quantification, and paired RNA-seq translational-efficiency analysis while preserving disagreement between ORF callers.",
        "assays": ["ribo-seq"],
        "workflow_by_assay": {"ribo-seq": "nf-core/riboseq 1.2.0"},
        "sources": [
            "https://nf-co.re/riboseq/1.2.0/",
            "https://nf-co.re/riboseq/1.2.0/docs/usage",
            "https://nf-co.re/riboseq/1.2.0/docs/output",
            "https://github.com/zhpn1024/ribotish",
            "https://github.com/smithlabcode/ribotricer",
            "https://github.com/LabTranslationalArchitectomics/RiboCode",
            "https://github.com/alexfields/ORF-RATER",
        ],
        "required_parameters": [
            "library adapter and UMI layout", "rRNA and tRNA depletion references", "genome and transcript annotation",
            "read-length range", "P-site offset policy", "periodicity threshold", "start-codon policy",
            "ORF classes", "minimum ORF support", "paired RNA-seq design", "translational-efficiency contrast",
        ],
        "figures": [
            "read-length distribution", "contaminant depletion", "mapping composition", "P-site offset diagnostics",
            "frame periodicity by length", "start and stop metagene", "ORF-class counts", "caller agreement",
            "gene and ORF abundance", "translational-efficiency MA and volcano", "browser tracks",
        ],
        "maturity": "validated",
        "claim_boundary": "Triplet periodicity and reproducible P-site signal support active translation; an ORF call is not protein existence, function, or conservation without orthogonal evidence.",
    },
    {
        "id": "bulk-nascent-transcription",
        "title": "Analyze bulk nascent transcription with strand-aware assay policies",
        "description": "Process GRO-seq and PRO-seq with strand-preserving alignment, run-on-specific quality control, nascent transcript and regulatory-element calling, pausing and directionality analysis, and replicate-aware differential transcription; TT-seq and NET-seq enter only through their separately declared pulse-label or polymerase-associated measurement models.",
        "assays": ["gro-seq", "pro-seq", "tt-seq", "net-seq"],
        "workflow_by_assay": {
            "gro-seq": "nf-core/nascent 2.3.0 GRO-seq profile",
            "pro-seq": "nf-core/nascent 2.3.0 PRO-seq profile",
            "tt-seq": "assay-specific pulse-label quantification with declared spike-in and half-life model",
            "net-seq": "assay-specific 3-prime-end polymerase-position workflow",
        },
        "sources": [
            "https://nf-co.re/nascent/2.3.0/",
            "https://nf-co.re/nascent/2.3.0/docs/usage",
            "https://nf-co.re/nascent/2.3.0/parameters",
            "https://nf-co.re/nascent/2.3.0/docs/output",
            "https://github.com/Danko-Lab/GRAND-SLAM",
        ],
        "required_parameters": [
            "assay", "strand convention", "UMI layout", "spike-in design", "reference and blacklist",
            "aligner and multimapping policy", "TSS and transcript caller", "pause-window definition",
            "bidirectional regulatory-element rule", "replicate-aware contrast", "normalization strategy",
        ],
        "figures": [
            "strand and mapping QC", "library complexity", "spike-in or depth scaling", "replicate correlation",
            "TSS metaprofile", "gene-body coverage", "pause-index distribution", "bidirectional transcription",
            "nascent transcript length and class", "differential MA and volcano", "genome tracks",
        ],
        "maturity": "validated",
        "claim_boundary": "Nascent signal measures transcriptional engagement under the declared assay model; it does not by itself establish steady-state RNA abundance, RNA stability, enhancer function, or causal regulation.",
    },
    {
        "id": "bulk-chromatin-accessibility",
        "title": "Analyze bulk chromatin accessibility with assay-specific footprint boundaries",
        "description": "Execute bulk ATAC-seq or DNase-seq quality control, alignment, fragment filtering, accessibility peak calling, replicate consensus, differential accessibility, motif and optional footprint analysis while keeping Tn5 and nuclease-specific biases explicit.",
        "assays": ["atac-seq", "dnase-seq"],
        "workflow_by_assay": {"atac-seq": "ENCODE ATAC/DNase WDL 2.2.3 in ATAC mode", "dnase-seq": "ENCODE ATAC/DNase WDL 2.2.3 in DNase mode"},
        "sources": [
            "https://nf-co.re/atacseq/latest/",
            "https://www.encodeproject.org/atac-seq/",
            "https://www.encodeproject.org/dnase-seq/",
            "https://www.encodeproject.org/pipelines/",
        ],
        "required_parameters": [
            "assay", "paired-end policy", "mitochondrial and duplicate policy", "Tn5 shift where applicable",
            "blacklist", "peak caller", "replicate consensus", "differential design", "motif database",
            "footprint bias correction and held-out validation",
        ],
        "figures": [
            "fragment length and nucleosome pattern", "TSS enrichment", "mitochondrial fraction", "FRiP",
            "replicate concordance", "peak width and annotation", "PCA", "differential MA and volcano",
            "motif enrichment", "bias-corrected footprint diagnostics", "genome tracks",
        ],
        "maturity": "validated",
        "claim_boundary": "Accessibility is not TF occupancy, enhancer activity, or causal regulation; footprint claims require enzyme-bias correction and independent evidence.",
    },
    {
        "id": "bulk-dna-methylation",
        "title": "Analyze bulk cytosine methylation with conversion-aware quality control",
        "description": "Process WGBS, RRBS, or enzymatic methyl-seq with conversion-aware alignment, context-specific methylation extraction, coverage and conversion quality control, biological-replicate aggregation, and region-level differential methylation without conflating 5mC with unresolved 5hmC.",
        "assays": ["wgbs", "rrbs", "em-seq"],
        "workflow_by_assay": {"wgbs": "nf-core/methylseq and ENCODE WGBS", "rrbs": "nf-core/methylseq RRBS profile", "em-seq": "nf-core/methylseq enzymatic-conversion profile when supported"},
        "sources": [
            "https://nf-co.re/methylseq/latest/",
            "https://www.encodeproject.org/wgbs/",
            "https://www.encodeproject.org/pipelines/",
            "https://bioconductor.org/packages/DSS/",
        ],
        "required_parameters": [
            "assay and conversion chemistry", "reference conversion policy", "non-conversion control", "duplicate policy",
            "minimum coverage", "CpG and non-CpG contexts", "smoothing", "DMR model and thresholds",
            "biological replicate design", "5mC versus 5hmC interpretation boundary",
        ],
        "figures": [
            "conversion efficiency", "coverage distribution", "cytosine-context composition", "M-bias",
            "replicate correlation", "global methylation", "PCA", "DMR effect and significance",
            "genomic annotation", "metaprofile", "locus tracks",
        ],
        "maturity": "validated",
        "claim_boundary": "Bisulfite-like chemistry generally does not distinguish 5mC from 5hmC; methylation differences do not establish transcriptional causality.",
    },
    {
        "id": "bulk-three-dimensional-genome",
        "title": "Analyze bulk chromosome conformation with resolution and replicate gates",
        "description": "Process Hi-C and capture or protein-anchored derivatives through pair validation, contact-matrix construction, normalization, replicate concordance, compartment, domain and loop analysis while retaining assay-specific enrichment and genomic-resolution limits.",
        "assays": ["hi-c", "micro-c", "capture-c", "hichip", "plac-seq", "chia-pet"],
        "workflow_by_assay": {
            "hi-c": "nf-core/hic or ENCODE Hi-C pipeline",
            "micro-c": "Micro-C compatible pair and matrix workflow",
            "capture-c": "capC-MAP 1.1.3 target-fragment interaction-profile workflow",
            "hichip": "FitHiChIP 11.0 protein-anchored loop workflow",
            "plac-seq": "FitHiChIP 11.0 protein-anchored loop workflow",
            "chia-pet": "ChIA-PET2 0.9.3 linker-aware loop workflow",
        },
        "sources": [
            "https://nf-co.re/hic/latest/",
            "https://www.encodeproject.org/pipelines/",
            "https://cooler.readthedocs.io/",
            "https://github.com/aidenlab/juicer",
            "https://capc-map.readthedocs.io/en/latest/usage.html",
            "https://github.com/ay-lab/FitHiChIP/tree/0ea1ac21be870908c672316ffbb630189dc6fae2",
            "https://github.com/GuipengLi/ChIA-PET2/tree/e120726d6440b24034f70bc3c51c17f351fef496",
        ],
        "required_parameters": [
            "assay", "restriction enzyme or fragmentation", "valid-pair filters", "reference", "bin resolutions",
            "matrix balance method", "minimum contacts", "replicate concordance", "compartment method",
            "domain and loop caller", "assay-specific background", "multiple-testing policy",
        ],
        "figures": [
            "pair-class QC", "cis-trans and distance-decay", "library complexity", "replicate concordance",
            "resolution curve", "contact map", "compartment eigenvector", "domain insulation",
            "loop enrichment", "aggregate peak analysis", "differential contact diagnostics",
        ],
        "maturity": "validated",
        "claim_boundary": "Contact frequency is population-averaged proximity under a resolution and normalization model; it is not direct physical binding, simultaneity in one cell, or causal regulation.",
    },
    {
        "id": "bulk-rna-modification-enrichment",
        "title": "Analyze bulk RNA-modification enrichment without claiming base resolution",
        "description": "Process MeRIP-seq or m6A-seq IP and input libraries through RNA-aware alignment, expression-aware enrichment calling, replicate consensus, differential peak analysis, motif and transcript-position summaries while preserving the resolution and antibody-specificity limits of enrichment assays.",
        "assays": ["merip-seq", "m6a-seq"],
        "workflow_by_assay": {"merip-seq": "MeRIPseqPipe or exomePeak2 workflow", "m6a-seq": "MeRIPseqPipe or exomePeak2 workflow"},
        "sources": [
            "https://academic.oup.com/bioinformatics/article/38/7/2054/6505200",
            "https://bioconductor.org/packages/exomePeak2/",
            "https://github.com/jiangwei01/MeRIPseqPipe",
        ],
        "required_parameters": [
            "IP and matched input", "antibody and lot", "biological replicates", "RNA type and strandedness",
            "reference and transcript annotation", "expression-aware background", "peak caller", "consensus rule",
            "differential model", "motif and positional analysis", "orthogonal validation plan",
        ],
        "figures": [
            "IP and input QC", "mapping and transcript composition", "replicate concordance", "peak width",
            "transcript metagene", "motif enrichment", "IP-input enrichment", "differential MA and volcano",
            "expression-versus-enrichment diagnostics", "locus tracks",
        ],
        "maturity": "validated",
        "claim_boundary": "MeRIP/m6A enrichment is regional and antibody-dependent; it does not identify a modified nucleotide or stoichiometry without orthogonal base-resolution evidence.",
    },
]


EXECUTORS = {
    "bulk-r-loop-mapping": {
        "engine": "rlpipes",
        "pipeline": "Bishop-Laboratory/RLPipes",
        "revision": "0.9.3",
        "path": "templates/run_rlpipes.py",
        "implemented_assays": ["drip-seq", "dripc-seq", "sdrip-seq", "qdrip-seq", "r-chip", "mapr", "cuttag"],
        "assay_executors": {
            "drip-seq": "templates/run_rlpipes.py",
            "dripc-seq": "templates/run_rlpipes.py",
            "sdrip-seq": "templates/run_rlpipes.py",
            "qdrip-seq": "templates/run_rlpipes.py",
            "r-chip": "templates/run_rlpipes.py",
            "mapr": "templates/run_rlpipes.py",
            "cuttag": {
                "executor_module_id": "bulk-chromatin-peak-calling",
                "executor_paths": [
                    "templates/call_macs3_chromatin.py",
                    "templates/normalize_cuttag_internal_reference.py",
                ],
            },
        },
        "purpose": "Execute pinned RLPipes 0.9.3 through its official build, check, and run API, then reload coverage, peaks, BAM files, RLSeq reports, logs, and checksums.",
        "required_logic": "For DRIP, DRIPc, sDRIP, qDRIP, R-ChIP, or MapR, execute pinned RLPipes 0.9.3 in the exact assay mode; route R-loop CUT&Tag to the CUT&Tag peak and internal-reference execution branch.",
        "limitation": "RLPipes covers six declared R-loop mapping modes. CUT&Tag remains a CUT&Tag analysis and is intentionally routed to the chromatin peak-calling executor with its target, RNase H specificity controls, and internal-reference policy declared separately.",
    },
    "bulk-ribosome-profiling": {
        "engine": "nfcore",
        "pipeline": "nf-core/riboseq",
        "revision": "1.2.0",
        "path": "templates/run_nfcore_riboseq.py",
        "implemented_assays": ["ribo-seq"],
        "assay_executors": {"ribo-seq": "templates/run_nfcore_riboseq.py"},
        "purpose": "Execute pinned nf-core/riboseq 1.2.0 and reload QC, P-site, ORF, quantification, MultiQC, and pipeline-information outputs.",
        "required_logic": "Run the pinned nf-core/riboseq 1.2.0 executor, validate its official parameter schema and immutable local inputs, then reload and provenance-bind every required output group.",
        "limitation": "Additional ORF callers outside nf-core/riboseq remain separate comparative branches and cannot be reported as executed until their own adapters run.",
        "support_files": [{
            "path": "templates/ribotish_python314_sitecustomize.py",
            "language": "python",
            "purpose": "Apply the checksum-bound Python 3.14 POSIX multiprocessing compatibility required only by pinned Ribo-TISH 0.2.7 processes on native ARM64 Docker.",
        }],
    },
    "bulk-nascent-transcription": {
        "engine": "nfcore",
        "pipeline": "nf-core/nascent",
        "revision": "2.3.0",
        "path": "templates/run_nfcore_nascent.py",
        "implemented_assays": ["gro-seq", "pro-seq", "tt-seq", "net-seq"],
        "assay_executors": {
            "gro-seq": "templates/run_nfcore_nascent.py",
            "pro-seq": "templates/run_nfcore_nascent.py",
            "tt-seq": "templates/run_ttseq_kinetics.py",
            "net-seq": "templates/run_netseq_wdl.py",
        },
        "purpose": "Execute pinned nf-core/nascent 2.3.0 for GRO-seq or PRO-seq and reload coverage, transcription-unit, quantification, MultiQC, and pipeline-information outputs.",
        "required_logic": "For GRO-seq or PRO-seq, run pinned nf-core/nascent 2.3.0; for NET-seq run its pinned WDL; for TT-seq apply paired new/total spike-in normalization and assumption-gated pulse kinetics.",
        "limitation": "NET-seq retains the upstream authors' yeast, Terra, and hexamer-UMI validation boundary. TT-seq kinetic rates require matched new/total libraries and explicit steady-state, spike-in, labeling-time, and capture-efficiency assumptions; invalid features remain flagged.",
        "additional_adapters": [{
            "path": "templates/run_netseq_wdl.py",
            "language": "python",
            "purpose": "Execute the pinned rdshear/netseq WDL with Cromwell 88, a digest-pinned container, localized checksum-bound FASTQ/reference inputs, and complete output reload.",
        }, {
            "path": "templates/run_ttseq_kinetics.py",
            "language": "python",
            "purpose": "Normalize paired new/total TT-seq libraries by declared spike-in recovery and estimate steady-state synthesis, degradation, and half-life values with row-level assumption failures retained.",
        }],
    },
    "bulk-rbp-rna-binding": {
        "engine": "nfcore",
        "pipeline": "nf-core/clipseq",
        "revision": "1.0.0",
        "path": "templates/run_nfcore_clipseq.py",
        "implemented_assays": ["rip-seq", "eclip", "iclip", "hits-clip", "par-clip", "lace-seq"],
        "assay_executors": {
            "rip-seq": "templates/run_ripseeker.py",
            "eclip": "templates/run_nfcore_clipseq.py",
            "iclip": "templates/run_nfcore_clipseq.py",
            "hits-clip": "templates/run_nfcore_clipseq.py",
            "par-clip": "templates/run_nfcore_clipseq.py",
            "lace-seq": "templates/run_laceseq_fastq.py",
        },
        "purpose": "Execute pinned nf-core/clipseq 1.0.0 and reload crosslink, CLIP quality-control, optional peak, MultiQC, and pipeline-information outputs.",
        "required_logic": "For eCLIP, iCLIP, HITS-CLIP, or PAR-CLIP preprocessing and site calling, run nf-core/clipseq 1.0.0 with the exact UMI and peak-caller policy; retain RIP-seq and LACE-seq as separate assay-native branches.",
        "limitation": "nf-core/clipseq covers CLIP-family preprocessing and crosslink or peak calling. LACE-seq instead uses its assay-native FASTQ workflow and matched IgG subtraction; RIP-seq uses its separately pinned RIPSeeker branch.",
        "additional_adapters": [{
            "path": "templates/run_laceseq_fastq.py",
            "language": "python",
            "purpose": "Execute the complete LACE-seq FASTQ workflow with pinned Cutadapt and Bowtie containers, pre-rRNA filtering, strand-aware alignment, matched-control subtraction, cluster calling, output reload, and checksums.",
        }, {
            "path": "templates/run_laceseq_clusters.py",
            "language": "python",
            "purpose": "Call strand-aware, matched-control-subtracted LACE-seq read clusters with the adjustable parameters and interval semantics of the pinned official analysis code, then reload every output and checksum.",
        }, {
            "path": "templates/run_ripseeker.py",
            "language": "python",
            "purpose": "Execute the pinned RIPSeeker 1.28.0 HMM API in an immutable Bioconductor container on explicitly paired RIP and control BAMs and reload region/model outputs.",
        }, {
            "path": "templates/run_ripseeker.R",
            "language": "r",
            "purpose": "Call the official RIPSeeker ripSeek API without source editing while retaining every documented bin, strand, multihit, and statistical cutoff parameter.",
        }],
    },
    "bulk-chromatin-accessibility": {
        "engine": "encode-wdl",
        "pipeline": "ENCODE-DCC/atac-seq-pipeline",
        "revision": "2.2.3",
        "path": "templates/run_encode_accessibility.py",
        "implemented_assays": ["atac-seq", "dnase-seq"],
        "assay_executors": {
            "atac-seq": "templates/run_encode_accessibility.py",
            "dnase-seq": "templates/run_encode_accessibility.py",
        },
        "purpose": "Execute pinned ENCODE ATAC/DNase WDL 2.2.3 through Caper 2.3.1 and reload assay-specific QC, reproducible peaks, signal tracks, workflow metadata, and checksums.",
        "required_logic": "Run the pinned ENCODE WDL with pipeline_type locked to atac or dnase so Tn5 shifting is applied only to ATAC-seq; preserve biological-replicate, IDR/overlap, enzyme, and accessibility claim boundaries.",
        "limitation": "The ENCODE branch exposes the official ATAC/DNase distinction and validated WDL parameters. Accessibility and footprint-like patterns remain enzyme- and processing-dependent and are not direct occupancy or regulatory causality.",
    },
    "bulk-dna-methylation": {
        "engine": "nfcore",
        "pipeline": "nf-core/methylseq",
        "revision": "4.2.0",
        "path": "templates/run_nfcore_methylseq.py",
        "implemented_assays": ["wgbs", "rrbs", "em-seq"],
        "assay_executors": {
            "wgbs": "templates/run_nfcore_methylseq.py",
            "rrbs": "templates/run_nfcore_methylseq.py",
            "em-seq": "templates/run_nfcore_methylseq.py",
        },
        "purpose": "Execute pinned nf-core/methylseq 4.2.0 and reload conversion-aware methylation calls, M-bias, alignment quality control, MultiQC, and pipeline-information outputs.",
        "required_logic": "Run nf-core/methylseq 4.2.0 with assay-locked WGBS, RRBS, or EM-seq presets; block incompatible conversion chemistry and aligner combinations before execution.",
        "limitation": "The executor quantifies conversion-based cytosine signal and preserves the 5mC versus 5hmC ambiguity; downstream replicate-aware DMR inference remains a separate declared statistical branch.",
    },
    "bulk-three-dimensional-genome": {
        "engine": "nfcore",
        "pipeline": "nf-core/hic",
        "revision": "2.1.0",
        "path": "templates/run_nfcore_hic.py",
        "implemented_assays": ["hi-c", "micro-c", "capture-c", "hichip", "plac-seq", "chia-pet"],
        "assay_executors": {
            "hi-c": "templates/run_nfcore_hic.py",
            "micro-c": "templates/run_nfcore_hic.py",
            "capture-c": "templates/run_capcmap.py",
            "hichip": "templates/run_fithichip.py",
            "plac-seq": "templates/run_fithichip.py",
            "chia-pet": "templates/run_chiapet2.py",
        },
        "purpose": "Execute pinned nf-core/hic 2.1.0 and reload valid pairs, contact matrices, distance-decay, MultiQC, and pipeline-information outputs.",
        "required_logic": "Run conventional Hi-C or restriction-free Micro-C through nf-core/hic 2.1.0; run bait-fragment Capture-C through capC-MAP 1.1.3; run HiChIP or PLAC-seq valid pairs through FitHiChIP 11.0; run linker-aware ChIA-PET through ChIA-PET2 0.9.3.",
        "limitation": "Each branch preserves its own observation model: whole-genome proximity, bait-fragment profiles, or protein-anchored enrichment. Contacts and statistically enriched loops do not establish simultaneous physical binding or regulatory causality.",
        "additional_adapters": [{
            "path": "templates/run_capcmap.py",
            "language": "python",
            "purpose": "Execute pinned capC-MAP 1.1.3 from paired FASTQ with an immutable target, restriction-fragment, Bowtie-index, binning, and normalization configuration, then reload target profiles and reports.",
        }, {
            "path": "templates/run_fithichip.py",
            "language": "python",
            "purpose": "Execute pinned FitHiChIP 11.0 for HiChIP or PLAC-seq from valid pairs, reference peaks, and chromosome sizes with all official loop-model parameters exposed and outputs reloaded.",
        }, {
            "path": "templates/run_chiapet2.py",
            "language": "python",
            "purpose": "Execute pinned ChIA-PET2 0.9.3 from paired FASTQ through linker trimming, alignment, duplicate removal, peak/loop calling, MICC significance, and QC output reload.",
        }],
    },
    "bulk-rna-modification-enrichment": {
        "engine": "exomepeak2",
        "pipeline": "Bioconductor/exomePeak2",
        "revision": "1.14.3",
        "path": "templates/run_exomepeak2.py",
        "implemented_assays": ["merip-seq", "m6a-seq"],
        "assay_executors": {
            "merip-seq": "templates/run_exomepeak2.py",
            "m6a-seq": "templates/run_exomepeak2.py",
        },
        "purpose": "Execute pinned exomePeak2 1.14.3 for replicate-aware MeRIP/m6A enrichment peak calling and optional differential analysis, then reload BED, tables, R objects, figures, logs, and checksums.",
        "required_logic": "Run the exact exomePeak2 1.14.3 API with matched indexed IP/input BAMs, transcript annotation, declared strand and window parameters, and optional treated pairs; retain regional enrichment claim limits.",
        "limitation": "exomePeak2 1.14.3 is pinned to its last Bioconductor 3.18 release. Its enrichment peaks are regional and antibody-dependent, not nucleotide identities or modification stoichiometry.",
        "support_files": [{
            "path": "templates/run_exomepeak2.R",
            "language": "r",
            "purpose": "Call the official exomePeak2 API without source editing and save its returned GRangesList alongside package-native outputs.",
        }],
    },
}


TEMPLATE = r'''#!/usr/bin/env python3
"""Validate a no-edit bulk-assay request and emit an execution-locked run contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


MODULE_ID = __MODULE_ID__
ASSAYS = __ASSAYS__
WORKFLOWS = __WORKFLOWS__
REQUIRED_PARAMETERS = __REQUIRED_PARAMETERS__
FIGURES = __FIGURES__


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if not args.request.is_file():
        raise FileNotFoundError(args.request)
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"output directory is not empty: {args.output_dir}")
    request = json.loads(args.request.read_text(encoding="utf-8"))
    if request.get("module_id") != MODULE_ID:
        raise ValueError("request module_id does not match this packaged workflow")
    assay = str(request.get("assay", "")).strip().lower()
    if assay not in ASSAYS:
        raise ValueError(f"unsupported assay for {MODULE_ID}: {assay}")
    parameters = request.get("parameters")
    if not isinstance(parameters, dict):
        raise ValueError("request.parameters must be an object")
    missing = [field for field in REQUIRED_PARAMETERS if field not in parameters or parameters[field] in (None, "", [])]
    if missing:
        raise ValueError("missing required assay parameters: " + ", ".join(missing))
    inputs = request.get("input_files")
    if not isinstance(inputs, list) or not inputs:
        raise ValueError("request.input_files must be a nonempty list")
    input_rows = []
    for value in inputs:
        path = Path(value).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        input_rows.append({"path": str(path), "sha256": digest(path), "bytes": path.stat().st_size})
    args.output_dir.mkdir(parents=True, exist_ok=False)
    contract = {
        "schema_version": 1,
        "module_id": MODULE_ID,
        "assay": assay,
        "official_workflow": WORKFLOWS[assay],
        "request_sha256": digest(args.request),
        "inputs": input_rows,
        "parameters": parameters,
        "required_figure_inventory": FIGURES,
        "execution_state": "admitted-not-run",
        "next_gate": "Resolve and record the exact installed workflow/tool version, then execute without editing this template; reload every declared result before evidence admission.",
    }
    output = args.output_dir / "run_contract.json"
    output.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"module_id": MODULE_ID, "assay": assay, "contract": str(output), "executed": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def format_contract(name: str, orientation: str) -> dict:
    return {
        "name": name,
        "versions": ["1"],
        "representations": ["structured"],
        "compression": ["none"],
        "required_indexes": [],
        "coordinate_systems": [],
        "genome_build_policy": "not_applicable",
        "genome_builds": [],
        "annotation_releases": [],
        "orientations": [orientation],
    }


def build_manifest(spec: dict) -> dict:
    module_id = spec["id"]
    executor = EXECUTORS.get(module_id)
    module_version = "0.2.0" if executor else "0.1.0"
    template_files = ["templates/run_assay_workflow.py"]
    code_templates = [{
        "path": "templates/run_assay_workflow.py", "language": "python",
        "purpose": "Validate immutable project inputs and freeze an assay-specific no-edit execution contract before running the selected official workflow.",
        "quality_gate_ids": [f"{module_id}-assay-contract", f"{module_id}-execution-reload", f"{module_id}-claim-boundary"],
        "requires_adaptation": False,
    }]
    required_logic = [
        "Resolve the exact assay before choosing a workflow; assays in the same measurement family retain separate control and signal models.",
        "Execute templates/run_assay_workflow.py without source editing to bind immutable inputs and parameters.",
        "Resolve the exact official workflow or method implementation and its compatible runtime before execution.",
    ]
    if executor:
        template_files.append(executor["path"])
        required_logic[-1] = executor["required_logic"]
        code_templates.append({
            "path": executor["path"],
            "language": "python",
            "purpose": executor["purpose"],
            "quality_gate_ids": [f"{module_id}-assay-contract", f"{module_id}-execution-reload", f"{module_id}-claim-boundary"],
            "requires_adaptation": False,
        })
        for support in executor.get("support_files", []):
            template_files.append(support["path"])
            code_templates.append({
                **support,
                "quality_gate_ids": [
                    f"{module_id}-assay-contract",
                    f"{module_id}-execution-reload",
                    f"{module_id}-claim-boundary",
                ],
                "requires_adaptation": False,
            })
        for adapter in executor.get("additional_adapters", []):
            template_files.append(adapter["path"])
            code_templates.append({
                **adapter,
                "quality_gate_ids": [
                    f"{module_id}-assay-contract",
                    f"{module_id}-execution-reload",
                    f"{module_id}-claim-boundary",
                ],
                "requires_adaptation": False,
            })
    tool_requirements = []
    tool_versions = {}
    platforms = ["any"]
    if executor and executor.get("engine") == "nfcore":
        tool_requirements = [
            {
                "name": "nextflow", "ecosystem": "system", "identity": "nextflow", "required": True,
                "tested_versions": ["25.04.8"], "allowed_versions": [">=25.04.8,<25.05"],
                "version_source": "https://github.com/nextflow-io/nextflow/releases/tag/v25.04.8",
                "verified_at": "2026-07-31", "version_probe": ["nextflow", "-version"],
                "version_probe_kind": "command", "version_probe_timeout_seconds": 30,
                "version_pattern": "version\\s+([0-9]+(?:\\.[0-9]+)+)", "mismatch_policy": "block",
                "version_differences": [], "platforms": ["macos-arm64", "linux-x86_64"],
            },
            {
                "name": "docker", "ecosystem": "system", "identity": "docker", "required": True,
                "tested_versions": ["29.2.1"], "allowed_versions": [">=29.0,<30"],
                "version_source": "https://docs.docker.com/engine/release-notes/29/",
                "verified_at": "2026-07-31", "version_probe": ["docker", "version", "--format", "{{.Server.Version}}"],
                "version_probe_kind": "command", "version_probe_timeout_seconds": 30,
                "version_pattern": "([0-9]+(?:\\.[0-9]+)+)", "mismatch_policy": "block",
                "version_differences": [], "platforms": ["macos-arm64", "linux-x86_64"],
            },
        ]
        tool_versions = {"nextflow": [">=25.04.8,<25.05"], "docker": [">=29.0,<30"]}
        platforms = ["macos-arm64", "linux-x86_64"]
        if module_id == "bulk-nascent-transcription":
            tool_requirements.append({
                "name": "cromwell", "ecosystem": "system", "identity": "cromwell", "required": True,
                "tested_versions": ["88"], "allowed_versions": ["==88"],
                "version_source": "https://github.com/broadinstitute/cromwell/releases/tag/88",
                "verified_at": "2026-07-31", "version_probe": ["cromwell", "--version"],
                "version_probe_kind": "command", "version_probe_timeout_seconds": 30,
                "version_pattern": "(?:cromwell\\s+)?([0-9]+)", "mismatch_policy": "block",
                "version_differences": [], "platforms": ["macos-arm64", "linux-x86_64"],
            })
            tool_versions["cromwell"] = ["==88"]
        # RIPSeeker 1.28.0, Cutadapt 1.15, and Bowtie 1.2.3 execute inside
        # immutable images.  They are recorded and checked by their adapters;
        # requiring host R or host copies of these tools would contradict the
        # isolated runtime contract.
        if module_id == "bulk-three-dimensional-genome":
            tool_requirements.extend([{
                "name": "ChIA-PET2", "ecosystem": "system", "identity": "ChIA-PET2", "required": True,
                "tested_versions": ["0.9.3"], "allowed_versions": ["==0.9.3"],
                "version_source": "https://github.com/GuipengLi/ChIA-PET2/tree/e120726d6440b24034f70bc3c51c17f351fef496",
                "verified_at": "2026-07-31", "version_probe": ["ChIA-PET2", "-v"],
                "version_probe_kind": "command", "version_probe_timeout_seconds": 30,
                "version_pattern": "ChIA-PET2\\s+([0-9]+(?:\\.[0-9]+)+)", "mismatch_policy": "block",
                "version_differences": [], "platforms": ["linux-x86_64"],
            }, {
                "name": "FitHiChIP", "ecosystem": "system", "identity": "FitHiChIP", "required": True,
                "tested_versions": ["11.0"], "allowed_versions": ["==11.0"],
                "version_source": "https://github.com/ay-lab/FitHiChIP/tree/0ea1ac21be870908c672316ffbb630189dc6fae2",
                "verified_at": "2026-07-31", "version_probe": ["git", "rev-parse", "HEAD"],
                "version_probe_kind": "command", "version_probe_timeout_seconds": 30,
                "version_pattern": "(0ea1ac21be870908c672316ffbb630189dc6fae2)", "mismatch_policy": "block",
                "version_differences": [], "platforms": ["linux-x86_64"],
            }, {
                "name": "capC-MAP", "ecosystem": "system", "identity": "capC-MAP", "required": True,
                "tested_versions": ["1.1.3"], "allowed_versions": ["==1.1.3"],
                "version_source": "https://github.com/cbrackley/capC-MAP/tree/fc2168f6da8a4fe331d5b22872789fa4caac0749",
                "verified_at": "2026-07-31", "version_probe": ["capC-MAP", "--help"],
                "version_probe_kind": "command", "version_probe_timeout_seconds": 30,
                "version_pattern": "(1\\.1\\.3)", "mismatch_policy": "block",
                "version_differences": [], "platforms": ["linux-x86_64"],
            }])
            tool_versions["ChIA-PET2"] = ["==0.9.3"]
            tool_versions["FitHiChIP"] = ["==11.0"]
            tool_versions["capC-MAP"] = ["==1.1.3"]
    elif executor and executor.get("engine") == "rlpipes":
        tool_requirements = [{
            "name": "RLPipes", "ecosystem": "system", "identity": "rlpipes", "required": True,
            "tested_versions": ["0.9.3"], "allowed_versions": ["==0.9.3"],
            "version_source": "https://github.com/Bishop-Laboratory/RLPipes/tree/b1f864e52c48e164c059b40afc450a5726c147e7",
            "verified_at": "2026-07-31", "version_probe": ["RLPipes", "--version"],
            "version_probe_kind": "command", "version_probe_timeout_seconds": 30,
            "version_pattern": "version[ ,]+([0-9]+(?:\\.[0-9]+)+)", "mismatch_policy": "block",
            "version_differences": [], "platforms": ["linux-x86_64"],
        }]
        tool_versions = {"RLPipes": ["==0.9.3"]}
        platforms = ["linux-x86_64"]
    elif executor and executor.get("engine") == "exomepeak2":
        tool_requirements = [
            {
                "name": "R", "ecosystem": "system", "identity": "r-runtime", "required": True,
                "tested_versions": ["4.3.2"], "allowed_versions": [">=4.3,<4.4"],
                "version_source": "https://cran.r-project.org/doc/manuals/r-release/NEWS.html",
                "verified_at": "2026-07-31", "version_probe": ["Rscript", "-e", "cat(as.character(getRversion()))"],
                "version_probe_kind": "command", "version_probe_timeout_seconds": 30,
                "version_pattern": "([0-9]+(?:\\.[0-9]+)+)", "mismatch_policy": "block",
                "version_differences": [], "platforms": ["macos-arm64", "linux-x86_64"],
            },
            {
                "name": "exomePeak2", "ecosystem": "r", "identity": "exomePeak2", "required": True,
                "tested_versions": ["1.14.3"], "allowed_versions": ["==1.14.3"],
                "version_source": "https://bioconductor.org/packages/3.18/bioc/html/exomePeak2.html",
                "verified_at": "2026-07-31", "version_probe": ["Rscript", "-e", "cat(as.character(packageVersion('exomePeak2')))"],
                "version_probe_kind": "command", "version_probe_timeout_seconds": 30,
                "version_pattern": "([0-9]+(?:\\.[0-9]+)+)", "mismatch_policy": "block",
                "version_differences": [], "platforms": ["macos-arm64", "linux-x86_64"],
            },
        ]
        tool_versions = {"R": [">=4.3,<4.4"], "exomePeak2": ["==1.14.3"]}
        platforms = ["macos-arm64", "linux-x86_64"]
    elif executor and executor.get("engine") == "encode-wdl":
        tool_requirements = [
            {
                "name": "Caper", "ecosystem": "python", "identity": "caper", "required": True,
                "tested_versions": ["2.3.1"], "allowed_versions": ["==2.3.1"],
                "version_source": "https://github.com/ENCODE-DCC/caper/releases/tag/v2.3.1",
                "verified_at": "2026-07-31", "version_probe": ["caper", "--version"],
                "version_probe_kind": "command", "version_probe_timeout_seconds": 30,
                "version_pattern": "([0-9]+(?:\\.[0-9]+)+)", "mismatch_policy": "block",
                "version_differences": [], "platforms": ["macos-arm64", "linux-x86_64"],
            },
            {
                "name": "Docker", "ecosystem": "system", "identity": "docker", "required": True,
                "tested_versions": ["29.2.1"], "allowed_versions": [">=29.0,<30"],
                "version_source": "https://docs.docker.com/engine/release-notes/29/",
                "verified_at": "2026-07-31", "version_probe": ["docker", "version", "--format", "{{.Server.Version}}"],
                "version_probe_kind": "command", "version_probe_timeout_seconds": 30,
                "version_pattern": "([0-9]+(?:\\.[0-9]+)+)", "mismatch_policy": "block",
                "version_differences": [], "platforms": ["macos-arm64", "linux-x86_64"],
            },
        ]
        tool_versions = {"Caper": ["==2.3.1"], "Docker": [">=29.0,<30"]}
        platforms = ["macos-arm64", "linux-x86_64"]
    return {
        "schema_version": 1,
        "id": module_id,
        "version": module_version,
        "title": spec["title"],
        "description": spec["description"],
        "module_type": "analysis",
        "domains": ["omics"],
        "intents": [*spec["assays"], f"analyze {module_id.replace('-', ' ')}", f"{module_id} workflow"],
        "questions": [f"Does the declared {', '.join(spec['assays'])} experiment support an assay-valid, reproducible bulk analysis?"],
        "entrypoint": "biomed_workbench.capabilities.agent_analysis:prepare_agent_analysis",
        "execution": {"kind": "workflow", "timeout_seconds": 30, "max_output_bytes": 10000000},
        "maturity": spec["maturity"],
        "input_artifacts": [{
            "name": "bulk_assay_inputs",
            "artifact_type": f"{module_id.replace('-', '_')}_inputs",
            "source_policy": "project_input",
            "processing_levels": ["raw-or-declared-upstream", "sample-manifest-bound"],
            "required_metadata": ["sample-identity", "biological-replicate", "assay", "reference", "source-digests"],
            "formats": [format_contract("inline-json", "file-manifest-and-assay-parameters")],
        }],
        "output_artifacts": [{
            "name": "bulk_assay_evidence",
            "artifact_type": f"{module_id.replace('-', '_')}_evidence",
            "processing_levels": ["executed", "reloaded", "quality-gated"],
            "required_metadata": ["module-version", "assay", "actual-tool-versions", "parameters", "source-and-output-digests", "quality-gates"],
            "formats": [format_contract("inline-json", "assay-results-tables-figures-and-provenance")],
        }],
        "preconditions": [
            "The assay, biological samples and replicates, library design, controls, reference, annotation, input files, and intended inference are declared before parameter selection.",
            "The selected workflow is compatible with the exact assay rather than merely accepting the same file extension.",
        ],
        "assumptions": [
            "The declared sample manifest reflects independent biological units and does not promote technical libraries or reads to biological replicates."
        ],
        "quality_gates": [
            {"id": f"{module_id}-assay-contract", "severity": "fatal", "description": "Block execution unless the assay-specific library, controls, reference, replicate, parameter, and output contracts are complete.", "blocks_interpretation": True},
            {"id": f"{module_id}-execution-reload", "severity": "fatal", "description": "Planned commands are not evidence; the workflow must run, every output must be reloaded, and actual versions, parameters, row counts, and digests must reconcile.", "blocks_interpretation": True},
            {"id": f"{module_id}-claim-boundary", "severity": "major", "description": spec["claim_boundary"], "blocks_interpretation": True},
        ],
        "limitations": [
            spec["claim_boundary"],
            executor["limitation"] if executor else "The bundled template admits and locks a run contract; scientific evidence exists only after the named external workflow executes in a compatible project-approved runtime and all outputs pass reload and quality review.",
        ],
        "evidence_effects": [f"adds_{module_id.replace('-', '_')}_evidence"],
        "alternatives": [],
        "complements": ["read-quality-fastqc", "read-quality-fastp", "quality-report-multiqc", "functional-enrichment", "figure-specification"],
        "tool_requirements": tool_requirements,
        "dependencies": [{
            "name": "python", "ecosystem": "runtime", "identity": "python-runtime", "required": True,
            "tested_versions": ["3.14.3"], "allowed_versions": [">=3.14,<3.15"],
            "version_source": "https://www.python.org/downloads/release/python-3143/", "verified_at": "2026-07-31",
            "version_probe": ["biomed_workbench.modules.compatibility:probe_python_runtime"], "version_probe_kind": "python_callable",
            "version_probe_timeout_seconds": 5, "version_pattern": "([0-9]+(?:\\.[0-9]+)+)",
            "purpose": "Validate and freeze the packaged assay run contract before external workflow execution.",
            "conflicts": [], "platforms": ["any"],
        }],
        "compatibility_matrix": [{
            "id": f"python-3.14.3-{module_id}-contract-1", "module_version": module_version, "tool_versions": tool_versions,
            "dependency_versions": {"python": [">=3.14,<3.15"]},
            "input_formats": {"bulk_assay_inputs": ["inline-json@1"]},
            "output_formats": {"bulk_assay_evidence": ["inline-json@1"]},
            "platforms": platforms, "regression_evidence_ids": [f"{module_id}-regression-v1"],
            "end_to_end_evidence_ids": [f"{module_id}-contract-e2e-v1"], "verified_at": "2026-07-31",
        }],
        "access": "agent_generated",
        "mutability": "read_only",
        "credentials": [],
        "input_schema": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "objective": {"type": "string", "minLength": 12},
                "assay": {"type": "string", "enum": spec["assays"]},
                "input_manifest_artifact_id": {"type": "string", "minLength": 1},
                "genome_build": {"type": "string", "minLength": 1},
                "annotation_release": {"type": "string", "minLength": 1},
                "sample_key": {"type": "string", "minLength": 1},
                "replicate_key": {"type": "string", "minLength": 1},
                "control_policy": {"type": "string", "minLength": 1},
                "requested_workflow": {"type": "string", "minLength": 1},
                "parameters": {"type": "object"},
                "design_notes": {"type": "string", "minLength": 1},
            },
            "required": ["objective", "assay", "input_manifest_artifact_id", "genome_build", "annotation_release", "sample_key", "replicate_key", "control_policy", "requested_workflow", "parameters", "design_notes"],
        },
        "output_schema": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "handoff_type": {"type": "string", "enum": ["packaged_parameterized_project_analysis"]},
                "module": {"type": "object"}, "request_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "request_fields": {"type": "array"}, "languages": {"type": "array"}, "code_plan": {"type": "array"},
                "parameter_rules": {"type": "array"}, "preflight_checks": {"type": "array"}, "postflight_checks": {"type": "array"},
                "provenance_fields": {"type": "array"}, "forbidden_actions": {"type": "array"}, "tool_profiles": {"type": "array"},
                "dependency_profiles": {"type": "array"}, "quality_gate_ids": {"type": "array"}, "execution_policy": {"type": "object"},
            },
            "required": ["handoff_type", "module", "request_digest", "request_fields", "languages", "code_plan", "parameter_rules", "preflight_checks", "postflight_checks", "provenance_fields", "forbidden_actions", "tool_profiles", "dependency_profiles", "quality_gate_ids", "execution_policy"],
        },
        "kernel_compatibility": [">=0.2.0,<0.3.0"],
        "provenance": {"license": "Apache-2.0", "concept_sources": spec["sources"]},
        "code_templates": code_templates,
        "agent_protocol": {
            "schema_version": 1, "mode": "packaged_parameterized_workflow", "languages": ["python", "r", "workflow"],
            "template_sections": [{
                "id": "admit-and-freeze-assay-run", "purpose": "Validate the assay and freeze project inputs, controls, parameters, versions, outputs and figure inventory.",
                "required_logic": required_logic,
                "output_artifact_types": [f"{module_id.replace('-', '_')}_evidence"], "template_files": template_files,
            }],
            "parameter_rules": [{
                "id": "assay-specific-method-selection", "parameter": "assay-workflow-parameters",
                "decision_inputs": spec["required_parameters"],
                "selection_rule": "Choose parameters from the exact assay protocol, official workflow documentation, blinded quality distributions, and the prespecified biological question before reviewing expected loci or effects.",
                "validation_rule": "Reject a configuration borrowed from a related assay when control, strand, UMI, fragmentation, enrichment, conversion, resolution, or signal semantics differ.",
            }],
            "preflight_checks": [
                "Inspect every source file and sample row; reconcile biological replicates, technical libraries, controls, read layout, reference, annotation and source digests.",
                "Detect actual external workflow and tool versions and compare them with the reviewed official sources before execution.",
                "Freeze the required figure inventory: " + "; ".join(spec["figures"]),
            ],
            "postflight_checks": [
                "Reload every result table, interval, matrix, track, model and figure; reconcile source/output digests, row counts, coordinates, sample identities, parameters and actual versions.",
                "Apply technical, statistical, biological and robustness review; failed or discordant branches remain visible and cannot be replaced by a fallback result.",
            ],
            "provenance_fields": ["module-id", "module-version", "assay", "sample-manifest-digest", "source-digests", "reference-and-annotation", "controls", "parameters", "actual-workflow-and-tool-versions", "output-digests", "quality-gates", "figure-inventory"],
            "forbidden_actions": [
                "Do not edit packaged templates, invent controls or replicates, infer assay identity from filenames, or substitute a related assay pipeline because it accepts the same file type.",
                "Do not admit a run plan as evidence, fabricate missing outputs, hide method disagreement, or exceed the assay-specific claim boundary.",
            ],
            "requires_observed_execution": True,
        },
    }


def write_spec(spec: dict) -> None:
    folder = BUILTIN / spec["id"]
    (folder / "templates").mkdir(parents=True, exist_ok=True)
    (folder / "tests").mkdir(parents=True, exist_ok=True)
    (folder / "module.json").write_text(json.dumps(build_manifest(spec), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rendered = (
        TEMPLATE.replace("__MODULE_ID__", repr(spec["id"]))
        .replace("__ASSAYS__", repr(tuple(spec["assays"])))
        .replace("__WORKFLOWS__", repr(spec["workflow_by_assay"]))
        .replace("__REQUIRED_PARAMETERS__", repr(tuple(spec["required_parameters"])))
        .replace("__FIGURES__", repr(tuple(spec["figures"])))
    )
    (folder / "templates" / "run_assay_workflow.py").write_text(rendered, encoding="utf-8")
    executor = EXECUTORS.get(spec["id"])
    assay_executors = executor.get("assay_executors", {}) if executor else {}
    coverage = {
        "schema_version": 1,
        "module_id": spec["id"],
        "assays": [
            {
                "assay": assay,
                "contract_ready": True,
                **(
                    assay_executors[assay]
                    if isinstance(assay_executors.get(assay), dict)
                    else {"executor_path": assay_executors.get(assay)}
                ),
            }
            for assay in spec["assays"]
        ],
    }
    (folder / "execution_coverage.json").write_text(
        json.dumps(coverage, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    case = {
        "schema_version": 1,
        "cases": [{
            "name": f"prepare-{spec['assays'][0]}-workflow",
            "input": {
                "objective": f"Execute and quality review a representative {spec['assays'][0]} bulk sequencing analysis",
                "assay": spec["assays"][0],
                "input_manifest_artifact_id": f"{spec['id']}-manifest",
                "genome_build": "GRCh38",
                "annotation_release": "GENCODE-v48",
                "sample_key": "sample_id",
                "replicate_key": "biological_replicate",
                "control_policy": "assay-specific matched controls declared in the sample manifest",
                "requested_workflow": spec["workflow_by_assay"][spec["assays"][0]],
                "parameters": {"parameter_contract": "reviewed-and-frozen-before-execution"},
                "design_notes": "Independent biological replicates and assay-specific controls are retained through inference.",
            },
            "expected_subset": {
                "handoff_type": "packaged_parameterized_project_analysis",
                "module": {"id": spec["id"], "version": "0.2.0" if spec["id"] in EXECUTORS else "0.1.0"},
                "execution_policy": {"manual_code_editing_required": False, "observed_execution_required": True, "planned_output_is_not_evidence": True},
            },
        }],
    }
    (folder / "tests" / "cases.json").write_text(json.dumps(case, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    for spec in SPECS:
        write_spec(spec)
    print(json.dumps({"modules": [spec["id"] for spec in SPECS], "count": len(SPECS)}, sort_keys=True))


if __name__ == "__main__":
    main()
