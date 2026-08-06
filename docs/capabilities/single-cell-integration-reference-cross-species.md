# Single-Cell Integration, Reference Mapping, And Cross-Species Analysis

Languages: [English](single-cell-integration-reference-cross-species.md) · [中文](single-cell-integration-reference-cross-species.zh-CN.md)

Updated: 2026-07-31

This contract does not collapse every form of integration into one task. An analysis first distinguishes four objectives:

1. **Within-modality batch integration:** construct a common representation for neighbourhoods, clustering, and visualization.
2. **Frozen-reference mapping:** map a query into a reference while avoiding retraining or alteration of the reference where possible.
3. **Multimodal or mosaic integration:** integrate RNA, protein, or ATAC measurements while declaring which cells lack which modality.
4. **Cross-species integration:** compare conserved states, transfer labels, and identify homologous modules while preserving species-specific states.

These representations support neighbourhood analysis, annotation, trajectories, and visualization; they do not replace raw counts. Differential expression, differential accessibility, and cross-condition inference return to uncorrected counts and use sample, donor, or species as the statistical unit.

## Within-Modality Batch Integration

| Method | Preferred use | Main tunable parameters | Principal boundary |
|---|---|---|---|
| Seurat v5 CCA | Platform differences are substantial but shared cell states are expected; a mature anchor workflow is needed | `nfeatures`, `dims`, `k.anchor`, reference layers, `k.weight` | May force alignment when shared states are insufficient; labels cannot guide unsupervised tuning |
| Seurat v5 RPCA | Datasets are relatively similar and large; conservative, faster integration is preferred | PCA features, `dims`, anchor parameters, reference layers | May be insufficient for strong nonlinear system differences; must be compared with unintegrated data |
| FastMNN | Batches contain mutually connectable shared populations; a classical MNN baseline is needed | HVGs, PCA dimensions, `k`, merge order, cosine normalization | Merge order and shared-population coverage affect results; rare batch-specific populations must not be erased as batch effects |
| Harmony | PCA or LSI already exists, batch variables are explicit, and rapid iteration is needed | `theta`, `lambda`, `sigma`, iteration count, multiple covariates | Corrects only declared covariates and cannot repair perfect confounding |
| scVI/scANVI | Raw UMI counts, multiple batches, nonlinear effects, and larger datasets; scANVI only when trustworthy partial labels exist | latent dimensions, network depth, dispersion, batch/covariates, epochs, seed | Labels cannot leak into the query used for evaluation; a generative model is not automatically correct |
| sysVI | Candidate for strong system effects across tissues, species, or organoid–tissue comparisons | system covariates, cycle weight, latent dimensions, HVGs, epochs, seed | Candidate rather than default workflow; requires comparison with mature baselines and multiple seeds |

A complete evaluation uses both batch-removal and biological-conservation scIB metrics: batch ASW, graph connectivity, iLISI, kBET, and PCR; plus ARI, NMI, cLISI, label ASW, isolated-label, HVG, cell-cycle, and trajectory conservation. Metrics that cannot be computed retain a data-grounded N/A reason and are never silently removed. UMAP appearance does not select the winner.

Authorities: [Seurat v5 integration](https://satijalab.org/seurat/articles/seurat5_integration); [batchelor/FastMNN](https://bioconductor.org/packages/release/bioc/html/batchelor.html); [Harmony](https://portals.broadinstitute.org/harmony/); [scVI](https://docs.scvi-tools.org/en/stable/user_guide/models/scvi.html); [scANVI](https://docs.scvi-tools.org/en/stable/user_guide/models/scanvi.html); [sysVI](https://docs.scvi-tools.org/en/1.3.3/user_guide/models/sysvi.html); [scIB, Nature Methods](https://www.nature.com/articles/s41592-021-01336-8).

## Frozen-Reference Mapping And Label Proposals

| Method | Preferred use | Output meaning | Main boundary |
|---|---|---|---|
| scArches | A generative scVI, scANVI, or totalVI reference; query mapping into a frozen latent space | query latent representation, posterior, optional label probabilities | Reference model, gene order, and registry must remain frozen; unknown query groups must be retained |
| Symphony | Fast, lightweight, reproducible mapping to a large reference atlas | reference coordinates, query embedding, label proposals | Reference centroids, loadings, normalization parameters, and versions must be preserved together |
| RCTD | Cell-type weights or abundances for spatial spots from an scRNA-seq reference | location-by-cell-type composition | Spatial-mixture deconvolution, not ordinary single-cell query label transfer |
| Tangram | Mapping cells or clusters to spatial positions | cell/cluster-by-location mapping probability | Mapping probability is not a cell proportion; mismatched tissue regions can force spurious mappings |

Query labels are predictions, not facts. Outputs must include maximum probability, margin or entropy, unknown or unsupported states, and held-out validation. Query truth labels cannot first guide model selection and then be presented as independent validation.

Authorities: [scArches, Nature Biotechnology](https://www.nature.com/articles/s41587-021-01001-7); [scArches documentation](https://docs.scvi-tools.org/en/stable/user_guide/models/scarches.html); [Symphony, Nature Communications](https://www.nature.com/articles/s41467-021-25991-3); [Symphony code](https://github.com/immunogenomics/symphony).

## Multimodal And Mosaic Integration

| Method | Modalities and design | Preferred use | Principal boundary |
|---|---|---|---|
| WNN | Paired multimodal measurements from the same cells | Neighbourhood fusion for fully paired 10x Multiome or CITE-seq data | Not suitable for extensively unpaired data; per-cell modality weights require review |
| MOFA+ | Multi-view factor model for bulk or single-cell data; missing views allowed | Discover shared and view-specific factors and sample-level variation | Factors are statistical representations, not mechanisms by default |
| totalVI | RNA and protein counts | CITE-seq with protein-background and batch modelling | Protein-panel QC remains independent; denoised protein is not an observed measurement |
| MultiVI | RNA and ATAC, paired or mosaic with single-modality cells | RNA–ATAC data with paired anchors and a shared peak universe | scvi-tools 1.4 or later uses `setup_mudata`; missing modalities must be explicit and cannot be fabricated |
| GLUE | Paired or unpaired RNA and ATAC linked by a graph prior | Unpaired integration with a credible promoter/peak/gene guidance graph | Results depend on graph genome build, annotation release, and edge definitions |

Evaluation includes modality and batch mixing, label preservation, cross-modal label transfer, paired-anchor FOSCTTM, rare-state preservation, donor reproducibility, and held-out reconstruction in which an observed modality is hidden before fitting. Random masking after fitting is not independent reconstruction evidence.

Authorities: [totalVI, Nature Methods](https://www.nature.com/articles/s41592-020-01050-x); [MultiVI API](https://docs.scvi-tools.org/en/stable/api/reference/scvi.model.MULTIVI.html); [MultiVI, Nature Methods](https://www.nature.com/articles/s41592-023-01909-9); [GLUE, Nature Biotechnology](https://www.nature.com/articles/s41587-022-01284-4); [GLUE documentation](https://scglue.readthedocs.io/en/latest/).

## Cross-Species Integration

Cross-species analysis first constructs an auditable homolog ledger. Every row retains source and target species, gene, orthogroup, one-to-one, one-to-many, or many-to-many relation, confidence, resource, and release. The first hit must never silently flatten a complex homology relation.

| Method | Homology information | Preferred use | Limits and tunable parameters |
|---|---|---|---|
| Shared one-to-one genes with scVI/scANVI, Harmony, or CCA/RPCA | High-confidence one-to-one orthogroups shared by all species | Conservative, interpretable baseline for closer species or sufficient shared genes | Loses paralog and many-to-many information; HVGs, latent dimensions, batch variables, and seeds require matched comparison |
| SAMap | Bidirectional protein-sequence similarity and expression neighbourhoods | Two or more evolutionarily distant species; cell-type evolution and paralog substitution | Requires NCBI BLAST and a reviewed map; species short IDs, map, neighbourhoods, and iterations are tunable; similarity is not proof of homology |
| SATURN | Protein-language-model embeddings for each species and learned macrogenes | Multiple species, complex homology, or insufficient one-to-one genes; GPU and versioned protein embeddings available | Computationally intensive; `hv_genes`, `num_macrogenes`, pretraining/metric epochs, embedding model, batch size, and seed affect results |
| CAME | Heterogeneous cell–gene graph with one-to-one, one-to-many, and many-to-many relations | Pairwise reference-to-query label transfer retaining complex gene relations and joint gene modules | Original workflow is pairwise; `ntop_deg`, `ntop_deg_nodes`, non-1v1 features, epochs, and batch size are tunable |

The standard comparison includes:

1. An unintegrated baseline, a one-to-one classical baseline, and at least one dedicated cross-species method on the same cell set.
2. Leave-one-species-out label transfer; truth classes absent from training species are unsupported rather than forced into ordinary errors and renamed.
3. Separate reports for species mixing, label or cell-state preservation, and species predictability; species signal is not required to become zero.
4. Preservation of species-specific populations in unintegrated and integrated spaces, with independent marker or functional evidence.
5. Conserved-module concordance for matched cell types; module comparison and label transfer cannot rely only on the same markers.
6. Differential analysis on raw counts for each species using sample, donor, or species-level models, or species-stratified analyses followed by meta-analysis.

Authorities: [SAMap code and v3 API](https://github.com/atarashansky/SAMap); [SAMap, eLife](https://elifesciences.org/articles/66747); [SATURN, Nature Methods](https://www.nature.com/articles/s41592-024-02191-z); [SATURN code](https://github.com/snap-stanford/SATURN); [CAME tutorial](https://xingyanliu.github.io/CAME/tut_notebooks/getting_started_pipeline_un.html); [CAME, Genome Research](https://genome.cshlp.org/content/early/2022/12/16/gr.276868.122); [cross-species benchmark, Nature Communications](https://www.nature.com/articles/s41467-023-41855-w).

## Role Of JSD In Single-Cell And Spatial Mapping

Jensen–Shannon divergence (JSD) is a symmetric difference measure between two nonnegative normalized distributions. It is not a mapping or deconvolution algorithm.

- With independent truth or a mixture withheld before fitting, prediction-versus-truth JSD can measure accuracy on a 0–1 scale, where lower is better.
- Method-versus-method JSD, such as RCTD versus cell2location or scArches versus Symphony, describes agreement only and cannot be called accuracy.
- JSD is reported both by spot or cell and by cell type or label, after verifying row and column identities and normalizing every distribution.
- Truth derived from the same model, markers, or post-fit imputation is not independent validation.

## Unified Admission Rules

An integration result enters interpretation only when all conditions are met:

1. Input counts, cells, features, samples, batches, species, modality missingness, and reference version are traceable.
2. Target biology is not perfectly confounded with technical batch; algorithms do not repair an effect that the design cannot identify.
3. All candidates use the same foundational cells and a pre-frozen evaluation set; native outputs are retained separately.
4. Mixing and biological preservation are evaluated separately rather than collapsed into a score that conceals failure.
5. Unknown, unsupported, rare, and species-specific states remain intact.
6. Outputs can be reloaded with consistent cell count, order, feature namespace, parameters, versions, seed, and digest.
7. Confirmatory inference explicitly returns to raw counts and biological replicates.
