# Scientific Evidence Maps And Bilingual Reports

Languages: [English](scientific-evidence-map.md) · [中文](scientific-evidence-map.zh-CN.md)

A scientific evidence map explains how a project's conclusions were reached. It retains not only the final successful figures and tables, but also the rationale, source data, quality checks, conflicting findings, excluded branches, and decisions that shaped the project.

## Two Levels Of Detail

The first level shows the project narrative: the relationships among key datasets and figure groups. It lets a reader grasp the research question, principal findings, and remaining evidence gaps without implementation detail.

The second level expands each dataset or figure group and links:

- the preceding data and conclusions that support the analysis;
- the current dataset, statistical result, or figure group;
- the analysis code and plot-ready data;
- the layout code and final data, PDF, and PNG files;
- the caption, interpretive source, and original-study DOI.

Each file is recorded with a clickable project path and a content fingerprint. Files are checked again before a report is generated. A missing or changed file stops the report so that an outdated result cannot be cited accidentally.

## Why An Analysis May Begin

Before an important analysis starts, the project records:

- the scientific rationale and a hypothesis that the data could refute;
- the selected method, primary sources, and reasonable alternatives;
- the experimental unit, statistical design, and reasons for key parameters;
- the expected outputs and the conditions for accepting, questioning, or stopping the branch.

An incomplete analysis may remain in the plan, but it is not described as executed or supported.

## How Results Enter The Project Conclusion

Datasets, tables, models, and figures are reviewed for technical validity, statistical design, biological interpretation, and robustness. Multi-part figures are interpreted part by part rather than through a single montage-level paragraph.

After review, a result may be retained, retained with limitations, excluded, reanalysed, replaced by another method, held for more data, used to revise the hypothesis, or used to stop a branch. Only retained results support the current conclusion. Excluded results, failed analyses, and conflicting evidence remain visible so that the reasoning can be reconstructed and mistakes are not repeated.

A rerun or method change creates a new analysis branch and records what changed, why it changed, and whether the claim became narrower or different. Historical results are never overwritten.

## Versions And Reports

Each formal update creates a new version that identifies its predecessor, the reason for the change, and the evidence it contains. Earlier versions remain unchanged, allowing a reader to recover the basis of any conclusion at the time it was made.

Chinese and English reports are generated from the same validated map version. Both cover:

- scientific rationale and hypothesis;
- methods;
- results and scientific conclusions;
- interpretation of each figure part;
- limitations, conflicting evidence, and the reason for retaining or excluding a result;
- implications for the next stage of the project.

This keeps the two reports aligned to the same data, figures, citations, and decisions instead of reconstructing their sources independently.

## Reference Frameworks

- [W3C PROV-O](https://www.w3.org/TR/prov-o/)
- [FAIR Guiding Principles](https://www.nature.com/articles/sdata201618)
- [RO-Crate](https://www.researchobject.org/ro-crate/1.1/)
- [Nature Methods: reproducibility standards for machine learning in the life sciences](https://www.nature.com/articles/s41592-021-01256-7)
