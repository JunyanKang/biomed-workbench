# Advanced omics evidence and workflow standard

Status: implementation authority for bulk CUT&Tag with a declared target,
optional internal-reference normalization and target-specific controls;
single-cell ATAC peak recall; DEqMS; GO/KEGG over-representation analysis;
preranked GSEA; WGCNA; and their figures. This document records the evidence used to choose
workflow relationships, exposed parameters, quality gates, and plots. It is not
a substitute for inspecting the actual experiment and installed tool versions.

## Source policy

1. A tool's official manual, vignette, or reference page controls function
   semantics and the list of adjustable parameters.
2. A primary methods paper and its deposited metadata control assay-specific
   choices.
3. Nature, Science, Cell, and major subjournal research papers and their
   available code are used to identify defensible workflow relationships and
   figure families. A paper-specific setting is an example, not a universal
   default.
4. Every run records the exact tool version, explicit parameters, annotation or
   pathway release, input/output digests, and all failed gates.
5. When a paper has no discoverable public analysis repository, the record says
   so; repository absence is never filled with invented code.

## Evidence matrix

| Capability | Official parameter authority | Primary or major-journal workflow evidence | Code evidence | Required upstream artifact | Required downstream artifacts and figures |
|---|---|---|---|---|---|
| Bulk CUT&Tag, including studies that declare S9.6 as the target | [MACS3 callpeak](https://macs3-project.github.io/MACS/docs/callpeak.html); [CUT&Tag tutorial](https://yezhengstat.github.io/CUTTag_tutorial/) | [Native R-loop sensor/CUT&Tag paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC7888926/); [GSE156400](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE156400); [PSIP1/LEDGF R-loop study](https://pmc.ncbi.nlm.nih.gov/articles/PMC10774266/); [co-localized G4/R-loop mapping](https://pmc.ncbi.nlm.nih.gov/articles/PMC11469684/) | No public analysis repository was identified for GSE156400 during the 2026-07-30 search; deposited Methods and GEO processing records are the implementation authority | Paired FASTQ or immutable aligned fragments; declared target or antibody; host and optional exogenous reference identities; biological sample/replicate sheet; relevant background and specificity controls; for S9.6, the explicit role of RNase H-treated material | Host/exogenous alignment accounting when applicable; raw and scaled tracks; per-replicate peaks; reproducible consensus; count matrix; target-specific controls; fragment/QC plots, replicate correlation, metaprofile/heatmap, genomic tracks, annotation, differential MA/volcano |
| Single-cell ATAC or multiome peak recall | [Signac CallPeaks](https://stuartlab.org/signac/reference/callpeaks); [Signac FeatureMatrix](https://stuartlab.org/signac/reference/featurematrix); [Signac peak-calling vignette](https://stuartlab.org/signac2/articles/peak_calling); [ArchR reproducible peak set](https://www.archrproject.com/reference/addReproduciblePeakSet.html) | [ArchR, Nature Genetics](https://www.nature.com/articles/s41588-021-00790-6); [Slide-tags, Nature](https://www.nature.com/articles/s41586-023-06837-4); [kidney multiome, Nature Communications](https://www.nature.com/articles/s41467-023-44467-6) | [ArchR paper code](https://github.com/GreenleafLab/ArchR_2020); [ArchR](https://github.com/GreenleafLab/ArchR); [Signac](https://github.com/stuart-lab/signac) | Indexed fragment files; reviewed cell/sample identities; predeclared pseudobulk grouping; genome build; blacklist; original ATAC assay retained | Per-sample or predeclared-group pseudobulks; reproducible/union peak BED; filtered frozen peak set; `FeatureMatrix`; new ChromatinAssay; rerun TF-IDF/LSI and RNA–ATAC WNN; before/after FRiP and LSI-depth sensitivity; UMAP, marker heatmap, browser tracks |
| DEqMS proteomics | [DEqMS manual](https://bioconductor.org/packages/release/bioc/manuals/DEqMS/man/DEqMS.pdf) and installed DEqMS vignette | [DEqMS protocol, Nature Protocols](https://www.nature.com/articles/s41596-026-01349-7); [CLL proteomics, Nature Communications](https://www.nature.com/articles/s41467-022-33385-8) | [DEqMS](https://github.com/yafeng/DEqMS); [eIF5A SILAC analysis](https://github.com/MRCToxBioinformatics/eIF5A_hypusination_inhibition_silac) | Protein abundance matrix; protein-by-sample peptide/PSM counts with declared semantics; sample design; explicit full-rank contrast; normalization and missingness policy | limma fit plus `spectraCounteBayes`; coefficient-bound DEqMS result; count–variance and residual diagnostics; PCA/correlation, count distribution, MA, volcano, protein heatmap |
| GO/KEGG ORA | [clusterProfiler manual](https://bioconductor.org/packages/release/bioc/manuals/clusterProfiler/man/clusterProfiler.pdf) | [Nature Communications functional analyses](https://www.nature.com/articles/s41467-024-52171-2); [GO redundancy handling example](https://www.nature.com/articles/s41467-025-56124-1) | [clusterProfiler](https://github.com/YuLab-SMU/clusterProfiler) | Selected identifiers plus the measured/tested universe; organism; input and target identifier namespaces; OrgDb/KEGG source and release | Separate GO and KEGG tables with raw and adjusted p values, ratios, counts, unmapped IDs; dot/bar plots; optional term-similarity map, gene–term network, overlap plot |
| Preranked GSEA | [fgsea manual](https://bioconductor.org/packages/release/bioc/manuals/fgsea/man/fgsea.pdf); clusterProfiler `gseGO`/`gseKEGG` manual entries | [Nature Communications GSEA](https://www.nature.com/articles/s41467-023-44020-5); [ranking and ORA/GSEA comparison](https://www.nature.com/articles/s41467-024-49211-2) | [fgsea](https://github.com/alserglab/fgsea); [clusterProfiler](https://github.com/YuLab-SMU/clusterProfiler) | Complete, finite, uniquely named ranked vector; declared ranking statistic and tie policy; versioned gene-set collection | NES, adjusted p value, size, leading edge, collapsed redundant pathways; NES dot plot, enrichment curve with hits and ranked metric, leading-edge heatmap; optional similarity map/ridge plot |
| WGCNA | [WGCNA official tutorials](https://edo98811.github.io/WGCNA_official_documentation/) and installed WGCNA help/formals | [Original WGCNA paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC2631488/); [Nature Communications module–trait analysis](https://www.nature.com/articles/s41467-025-56715-y); [TOM/module example](https://www.nature.com/articles/s41467-023-42300-8) | [resampled consensus WGCNA](https://github.com/talkowski-lab/rWGCNA) | Properly normalized quantitative feature-by-biological-sample matrix transposed to samples-by-features; sample/trait manifest; enough independent samples; missingness/outlier policy | sample QC; chosen soft threshold with diagnostics; adjacency/TOM/modules/eigengenes; module–trait correlations and p values; membership/significance table; sample dendrogram, threshold plots, module dendrogram, module–trait heatmap, optional TOM/hub network |

## Adjustable parameter contract

The user interface must expose these parameters and their rationale. It may
offer evidence-backed presets, but must not silently choose them from desired
results.

### Bulk CUT&Tag with a declared S9.6 target

- Reference policy: host reference, exogenous species/reference, competitive or
  separately aligned policy, Bowtie2 options, MAPQ, proper-pair and duplicate
  treatment.
- Scale policy: `none`, declared exogenous-spike target-over-observed, or
  matched RNase-H-pair scaling. These policies are not interchangeable.
- Reliability gates: absolute exogenous fragments and fraction thresholds are
  study QC thresholds and have no universal official default; they must be
  declared or learned from a blinded library-QC distribution.
- Peak policy: MACS3 or SEACR, paired-end format, genome size, narrow/broad
  mode, q/p threshold, duplicate policy, fixed extension/shift, control,
  per-replicate and consensus rule.
- RNase H is specificity evidence. Pooled or unreplicated RNase H material is
  not a biological condition replicate.

### Single-cell ATAC peak recall

- `CallPeaks`: grouping field/identities, `broad`, input format, genome size,
  `extsize`, `shift`, additional MACS3 arguments, and peak-combination rule.
- ArchR-style alternative: `groupBy`, `peakMethod`, reproducibility rule,
  `peaksPerCell`, `maxPeaks`, `minCells`, excluded chromosomes, genome size,
  shift, extension, significance cutoff, summit extension, promoter exclusion,
  seed and threads.
- Peak-set filters: standard chromosomes, genome blacklist, minimum/maximum
  width, minimum pseudobulk support, and the exact union/merge algorithm.
- The frozen recalled set must be quantified with `FeatureMatrix`; a new assay
  must be created and TF-IDF/LSI/WNN rerun. The original assay remains available
  for sensitivity comparison.

### DEqMS

- Design formula, factor reference levels, coefficient/contrast, normalization,
  missingness and imputation policy, protein filtering, abundance scale, count
  definition, count aggregation across samples, and `fit.method`.
- The DEqMS count supplied to `spectraCounteBayes` must represent the peptide or
  PSM support appropriate to the quantification method and contrast. The
  coefficient passed to `spectraCounteBayes` and `outputResult` must be recorded
  and identical.
- Official diagnostic plot families are variance box/scatter, residual, and
  volcano; the workbench adds sample-level QC, MA and heatmap under the common
  figure contract.

### GO/KEGG ORA and preranked GSEA

- ORA: organism, `OrgDb`, `keyType`, ontology, universe, p-value cutoff,
  adjustment method, q-value cutoff, minimum/maximum gene-set size, readable
  conversion, GO pooling, and KEGG online/internal data policy.
- GSEA: ranking statistic and direction, duplicate/tie policy, exponent,
  minimum/maximum gene-set size, epsilon/precision, simple-permutation count,
  score type, seed and threads.
- ORA requires a selected list and explicit measured background; GSEA requires
  the complete ranked list and must not receive only significant genes.
- Database/annotation release and identifier conversion losses are mandatory
  output metadata.

### WGCNA

- Missingness limits, outlier policy, correlation (`pearson` or robust
  alternative), network type, candidate powers, selected power and selection
  criterion, TOM type, maximum block size, `deepSplit`, minimum module size,
  PAM rule, module merge height, seed and threads.
- Soft power is selected from the diagnostic trade-off between topology fit and
  connectivity, not from a fixed universal value.
- Small or unstable studies must be blocked or labeled exploratory. Resampling
  or consensus stability is required for consequential hub/module claims.

## Cross-tool workflow contract

```text
raw assay
  -> assay-specific QC and immutable sample design
  -> assay-specific quantification
  -> sample-aware differential or coexpression model
  -> stable gene/protein/peak identifiers and tested universe
  -> ORA (selected set + universe) and/or GSEA (complete ranking)
  -> figure contract and evidence ledger
```

For CUT&Tag with an S9.6 target, quantification means replicate-level peak/count
evidence after applicable host/exogenous accounting and RNase H specificity
review. For multiome, it means a
frozen recalled peak set, rebuilt peak-by-cell matrix, rerun LSI, and rerun WNN
before regulatory analysis. DEqMS produces a protein ranking/list that can feed
enrichment. WGCNA consumes the normalized sample-level matrix rather than a
differential-result table; its module members can subsequently feed ORA, while
signed module membership or trait statistics can support a separately declared
GSEA-style ranking.

No enrichment result establishes causality. No WGCNA edge establishes physical
interaction. No CUT&Tag peak obtained with S9.6 alone establishes a
locus-specific R-loop. These
boundaries remain in reports and plot legends.

## Figure contract and journal profiles

The common contract standardizes meaning: color identity, axes and units,
experimental `n`, test and multiple-testing statement, effect size and
uncertainty, legend ordering, missing-value display, and vector-first export.
It does not force every analysis into the same plot.

The `nature` export profile follows Nature's current
[research figure guide](https://research-figure-guide.nature.com/figures/building-and-exporting-figure-panels/):
89 mm and 183 mm widths, maximum 170 mm height, standard sans-serif fonts,
5–7 pt final-size text, editable text/layers, compact alphabetical panels, and
PDF/SVG or other accepted editable vector formats. Nature's manuscript
[formatting guide](https://www.nature.com/nature/for-authors/formatting-guide)
also requires units, lower-case panel lettering conventions, scale bars rather
than magnification, and restrained in-panel text. A historical Nature checklist
specifies approximately 0.5 pt lines at final size; this is used as the default
stroke, while dense raster elements retain a separate resolution policy.

Science and Cell-family exports are explicit target-journal overrides. The
workbench does not label values as official Science or Cell specifications
unless the exact target journal's current author guide is linked in the run.
Representative papers from all three families inform plot inventories, but
publisher formatting and biological plot choice remain separate evidence
layers.
