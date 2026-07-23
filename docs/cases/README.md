# Public-Data Acceptance Cases

Public-data cases complement deterministic fixtures by executing packaged
workflows against stable, independently published scientific datasets. Each case
binds the source identity and digest to a module, compatibility row, code
template, detected runtime, parameters, quality gates, observed results, reload
checks, and explicit inferential boundaries.

| Case | Scientific surface | Current evidence |
| --- | --- | --- |
| [PBMC3k single-cell foundation](pbmc3k-foundation.md) | 10x matrix validation, cell accounting, raw-count preservation, normalization, HVG, PCA, neighbors, UMAP, Leiden sensitivity, and H5AD reload | 2700 source cells; 2638 retained cells; 13656 retained genes; all declared gates passed |
| [PBMC3k atlas annotation](pbmc3k-atlas-annotation.md) | Official CellTypist immune-model mapping, full probability evidence, frozen Unknown policy, count preservation, reload, and posthoc broad marker coherence | 2700 source cells; 98 model classes; exact query/model digests; all declared gates passed |
| [GSE96583 paired donor pseudobulk](gse96583-donor-pseudobulk.md) | Published singlet filtering, raw-count pseudobulk aggregation, eight-donor paired edgeR design, result reload, and independent IFN-response recovery | 29065 published cells; 24673 retained singlets with labels; 8 paired donors; all declared gates passed |
| [Zebrafish neural-crest RegVelo](zebrafish-regvelo.md) | Official continuous-layer preprocessing, target-regulator GRN alignment, hard/soft RegVelo fitting, model reload, withheld-stage direction, and explicit mode sensitivity | 697 cells; 1008 modeled genes; 81 TFs; 4309 edges; exact source/GRN digests |
| [Zebrafish RegVelo-to-CellRank fate](zebrafish-cellrank-fate.md) | CellRank 2.3.2 velocity kernel, exact repeat, withheld-stage direction, GPCCA fate probabilities, lineage drivers, and connectivity-weight sensitivity | 697 cells; 4 annotation-defined terminal states; 467 transient cells; pure-versus-blended fate Pearson 0.9981 |
| [Multi-database live evidence](public-database-contracts.md) | Citation, preprint, compound, trial, experimental structure, structure search, polymer, ligand, and predicted-structure records | Nine current module/service checks across seven public database families; all declared gates passed |

A checked report is evidence only for the source, module version, template,
runtime, parameters, and gates recorded in that report. It is not a claim that
the same workflow or thresholds are valid for another dataset.
