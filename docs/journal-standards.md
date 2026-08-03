# Journal targeting and manuscript standards

Biomed Workbench uses a machine-readable standards library rather than asking an agent to recall submission rules. Catalog version `2026.07.31` covers 54 high-level life-science and biomedical journals across Nature Portfolio, Science/AAAS, Cell Press, The Lancet, NEJM, JAMA, The BMJ, PNAS, EMBO Press, Genome Biology, Genome Research, Nucleic Acids Research, Bioinformatics, PLOS Biology, and related titles.

Authoritative files:

- active snapshot: `biomed_workbench/knowledge/journal_standards/v2026.07.31.json`
- active-version index: `biomed_workbench/knowledge/journal_standards/index.json`
- reproducible builder: `tools/build_journal_standards.py`

## Journals currently covered

The following table maps one-to-one to the 54 profiles in catalog version `2026.07.31`. The field summary supports quick human browsing; targeting still reads each journal's complete audience, topic-fit, article-type, and study-design record.

The metric frame is the **2026 Journal Citation Reports (2025 data)**, [released by Clarivate on 17 June 2026](https://clarivate.com/news/clarivate-releases-journal-citation-reports-2026/). The impact-factor column therefore means the **2025 Journal Impact Factor (JIF)**, not the year in which a webpage was accessed. JCR quartiles are calculated separately for each subject category, so one journal can have several category-specific quartiles. A number or `Q1` is recorded only when a journal or publisher page publicly states the 2025 JIF and provides either an explicit quartile or a category rank sufficient to verify it. “Institutional check required” means that the current value could not be fully verified from an official public page; it does not mean zero, no JIF, or exclusion from JCR.

<!-- journal-coverage-table:start -->
| Journal | Publisher / publishing organization | Principal fields | JCR 2026 quartile | 2025 JIF |
| --- | --- | --- | --- | ---: |
| [Nature](https://www.nature.com/nature/for-authors/formatting-guide) | Springer Nature · Nature Portfolio | multidisciplinary science, mechanisms, conceptual advances | Institutional category check required | [56.1](https://www.nature.com/nature/journal-impact) |
| [Nature Medicine](https://www.nature.com/nm/content) | Springer Nature · Nature Portfolio | translational medicine, clinical research, disease mechanisms | Institutional category check required | [52.5](https://www.nature.com/nm/journal-impact) |
| [Nature Biotechnology](https://www.nature.com/nbt/content) | Springer Nature · Nature Portfolio | biotechnology, technology development, engineering | Institutional category check required | [44.5](https://www.nature.com/nbt/journal-impact) |
| [Nature Genetics](https://www.nature.com/ng/content) | Springer Nature · Nature Portfolio | genetics, genomics, human genetics | Institutional category check required | [25.5](https://www.nature.com/ng/journal-impact) |
| [Nature Methods](https://www.nature.com/nmeth/content) | Springer Nature · Nature Portfolio | methods, benchmarking, technology | Institutional category check required | [28.3](https://www.nature.com/nmeth/journal-impact) |
| [Nature Neuroscience](https://www.nature.com/neuro/content) | Springer Nature · Nature Portfolio | neuroscience, brain science, neural circuits | Institutional category check required | [20.3](https://www.nature.com/neuro/journal-impact) |
| [Nature Immunology](https://www.nature.com/ni/content) | Springer Nature · Nature Portfolio | immunology, immune mechanisms, infection | Institutional category check required | [26.5](https://www.nature.com/ni/journal-impact) |
| [Nature Cancer](https://www.nature.com/natcancer/content) | Springer Nature · Nature Portfolio | cancer biology, oncology, tumor biology | Institutional category check required | [28.0](https://www.nature.com/natcancer/journal-impact) |
| [Nature Cell Biology](https://www.nature.com/ncb/content) | Springer Nature · Nature Portfolio | cell biology, mechanisms, organelles | Institutional category check required | [22.7](https://www.nature.com/ncb/journal-impact) |
| [Nature Microbiology](https://www.nature.com/nmicrobiol/content) | Springer Nature · Nature Portfolio | microbiology, pathogens, microbiomes | Institutional category check required | [18.7](https://www.nature.com/nmicrobiol/journal-impact) |
| [Nature Metabolism](https://www.nature.com/natmetab/content) | Springer Nature · Nature Portfolio | metabolism, metabolic disease, physiology | Institutional category check required | [27.5](https://www.nature.com/natmetab/journal-impact) |
| [Nature Biomedical Engineering](https://www.nature.com/natbiomedeng/submission-guidelines/aip-and-formatting) | Springer Nature · Nature Portfolio | biomedical engineering, devices, diagnostics | Institutional category check required | [26.3](https://www.nature.com/natbiomedeng/journal-impact) |
| [Nature Communications](https://www.nature.com/ncomms/submit/article) | Springer Nature · Nature Portfolio | biology, medicine, methods | Institutional category check required | [18.9](https://www.nature.com/ncomms/journal-impact) |
| [Communications Biology](https://www.nature.com/commsbio/submission-guidelines) | Springer Nature · Nature Portfolio | biology, cell biology, genomics | Institutional category check required | [5.8](https://www.nature.com/commsbio/journal-impact) |
| [Nature Structural & Molecular Biology](https://www.nature.com/nsmb/content) | Springer Nature · Nature Portfolio | structural biology, molecular biology, biochemistry | Institutional category check required | [10.1](https://www.nature.com/nsmb/journal-impact) |
| [Scientific Data](https://www.nature.com/sdata/publish/submission-guidelines) | Springer Nature · Nature Portfolio | data resources, datasets, data reuse | Institutional category check required | [7.2](https://www.nature.com/sdata/journal-impact) |
| [Science](https://www.science.org/content/page/science-information-authors) | AAAS | multidisciplinary science, conceptual advances, biology | Institutional category check required | Institutional check required |
| [Science Translational Medicine](https://www.science.org/journal/stm/information-for-authors) | AAAS | translational medicine, clinical research, therapeutics | Institutional category check required | Institutional check required |
| [Science Immunology](https://www.science.org/journal/sciimmunol/information-for-authors) | AAAS | immunology, immune mechanisms, infection | Institutional category check required | Institutional check required |
| [Science Signaling](https://www.science.org/journal/signaling/information-for-authors) | AAAS | signaling, cell communication, kinases and pathways | Institutional category check required | Institutional check required |
| [Science Advances](https://www.science.org/journal/sciadv/information-for-authors) | AAAS | multidisciplinary science, biology, medicine | Institutional category check required | Institutional check required |
| [Cell](https://www.cell.com/cell/home) | Elsevier · Cell Press | cell biology, mechanisms, broad life sciences | Institutional category check required | Institutional check required |
| [Cell Stem Cell](https://www.cell.com/cell-stem-cell/home) | Elsevier · Cell Press | stem cells, development, regenerative medicine | Institutional category check required | Institutional check required |
| [Cancer Cell](https://www.cell.com/cancer-cell/home) | Elsevier · Cell Press | cancer biology, oncology, tumor biology | Institutional category check required | Institutional check required |
| [Immunity](https://www.cell.com/immunity/home) | Elsevier · Cell Press | immunology, immune mechanisms, infection | Institutional category check required | Institutional check required |
| [Neuron](https://www.cell.com/neuron/home) | Elsevier · Cell Press | neuroscience, brain science, neural circuits | Institutional category check required | Institutional check required |
| [Molecular Cell](https://www.cell.com/molecular-cell/home) | Elsevier · Cell Press | molecular biology, gene regulation, chromatin | Institutional category check required | Institutional check required |
| [Cell Metabolism](https://www.cell.com/cell-metabolism/home) | Elsevier · Cell Press | metabolism, physiology, nutrition | Institutional category check required | Institutional check required |
| [Cell Host & Microbe](https://www.cell.com/cell-host-microbe/home) | Elsevier · Cell Press | microbiology, infection, microbiomes | Institutional category check required | Institutional check required |
| [Developmental Cell](https://www.cell.com/developmental-cell/home) | Elsevier · Cell Press | developmental biology, cell biology, morphogenesis | Institutional category check required | Institutional check required |
| [Cell Reports Medicine](https://www.cell.com/cell-reports-medicine/home) | Elsevier · Cell Press | medicine, translational science, clinical research | Institutional category check required | Institutional check required |
| [Current Biology](https://www.cell.com/current-biology/home) | Elsevier · Cell Press | biology, evolution, neuroscience | Institutional category check required | Institutional check required |
| [The Lancet](https://www.thelancet.com/journals/lancet/home) | Elsevier · The Lancet Group | clinical medicine, global health, public health | Institutional category check required | Institutional check required |
| [The Lancet Oncology](https://www.thelancet.com/journals/lanonc/home) | Elsevier · The Lancet Group | oncology, cancer therapy, clinical trials | [Q1 (public rank verified)](https://info.thelancet.com/lanonc/request-access) | [33.7](https://info.thelancet.com/lanonc/request-access) |
| [The Lancet Neurology](https://www.thelancet.com/journals/laneur/home) | Elsevier · The Lancet Group | neurology, brain disease, clinical research | [Q1 (public rank verified)](https://info.thelancet.com/laneur/request-access) | [54.6](https://info.thelancet.com/laneur/request-access) |
| [The Lancet Infectious Diseases](https://www.thelancet.com/journals/laninf/home) | Elsevier · The Lancet Group | infectious diseases, pathogens, epidemiology | [Q1 (public rank verified)](https://info.thelancet.com/laninf/request-access) | [29.4](https://info.thelancet.com/laninf/request-access) |
| [The Lancet Digital Health](https://www.thelancet.com/journals/landig/home) | Elsevier · The Lancet Group | digital health, machine learning, clinical AI | Institutional category check required | Institutional check required |
| [The Lancet Haematology](https://www.thelancet.com/journals/lanhae/home) | Elsevier · The Lancet Group | hematology, blood disorders, clinical trials | [Q1 (public rank verified)](https://info.thelancet.com/lanhae/request-access) | [20.4](https://info.thelancet.com/lanhae/request-access) |
| [The Lancet Respiratory Medicine](https://www.thelancet.com/journals/lanres/home) | Elsevier · The Lancet Group | respiratory medicine, lung disease, clinical research | [Q1 (public rank verified)](https://info.thelancet.com/lanres/request-access) | [34.7](https://info.thelancet.com/lanres/request-access) |
| [The Lancet Gastroenterology & Hepatology](https://www.thelancet.com/journals/langas/home) | Elsevier · The Lancet Group | gastroenterology, hepatology, clinical research | [Q1 (public rank verified)](https://info.thelancet.com/langas/request-access) | [39.1](https://info.thelancet.com/langas/request-access) |
| [New England Journal of Medicine](https://www.nejm.org/author-center/article-types) | Massachusetts Medical Society | clinical medicine, clinical trials, public health | [Q1 (officially identified as category-leading)](https://www.nejm.org/about-nejm/about-nejm) | [84.5](https://www.nejm.org/about-nejm/about-nejm) |
| [JAMA](https://jamanetwork.com/journals/jama/pages/instructions-for-authors) | American Medical Association | clinical medicine, health policy, clinical trials | Institutional category check required | Institutional check required |
| [The BMJ](https://www.bmj.com/about-bmj/resources-authors/article-types) | BMJ Group | clinical medicine, public health, evidence synthesis | Institutional category check required | Institutional check required |
| [Proceedings of the National Academy of Sciences](https://www.pnas.org/author-center/submitting-your-manuscript) | National Academy of Sciences | multidisciplinary science, biology, medicine | Institutional category check required | Institutional check required |
| [eLife](https://elifesciences.org/articles/research-article) | eLife Sciences Publications | biology, medicine, methods | Institutional category check required | Institutional check required |
| [The EMBO Journal](https://www.embopress.org/page/journal/14602075/authorguide) | EMBO Press | molecular biology, cell biology, mechanisms | Institutional category check required | Institutional check required |
| [Molecular Systems Biology](https://www.embopress.org/page/journal/17444292/authorguide) | EMBO Press | systems biology, computational biology, networks | Institutional category check required | Institutional check required |
| [Genome Biology](https://genomebiology.biomedcentral.com/submission-guidelines) | Springer Nature · BMC | genomics, single-cell biology, bioinformatics | Institutional category check required | Institutional check required |
| [Genome Research](https://genome.cshlp.org/site/misc/ifora.xhtml) | Cold Spring Harbor Laboratory Press | genomics, functional genomics, methods | Institutional category check required | Institutional check required |
| [Nucleic Acids Research](https://academic.oup.com/nar/pages/author-guidelines) | Oxford University Press | DNA, RNA, genomics | Institutional category check required | Institutional check required |
| [Bioinformatics](https://academic.oup.com/bioinformatics/pages/author-guidelines) | Oxford University Press | bioinformatics, software, algorithms | Institutional category check required | Institutional check required |
| [PLOS Biology](https://journals.plos.org/plosbiology/s/submission-guidelines) | Public Library of Science | biology, open science, methods | Institutional category check required | Institutional check required |
| [Blood](https://ashpublications.org/blood/pages/manuscript_types) | American Society of Hematology | hematology, blood cancers, immunology | Institutional category check required | Institutional check required |
| [Circulation](https://www.ahajournals.org/circ/author-instructions) | American Heart Association | cardiovascular medicine, cardiac research, clinical trials | Institutional category check required | Institutional check required |
<!-- journal-coverage-table:end -->

Impact factors and quartiles are descriptive context for human comparison only. They are not recommendation features and are never used to predict acceptance. Before submission work begins, the agent must recheck every category-specific quartile and JIF in the institution's JCR access and record the JCR edition and verification date in the project provenance.

## Per-journal record

Every journal independently records:

- intended readership and scope;
- favored article types;
- project-fit and evidence-maturity signals;
- officially stated abstract, main-text, display-item, and reference limits;
- required sections, language style, figure principles, and reporting requirements;
- official scope, content-type, author-instruction, and figure sources;
- standard version, review date, and catalog digest.

A field can be an exact journal rule, a publisher-wide rule that a journal page may override, or an unresolved official field. An unresolved value remains null and becomes a mandatory live check. It never means “no limit.”

## Recommendation and compliance

`journal-targeting-and-compliance` compares the project's question, study type, methods, intended audience, and evidentiary maturity with the catalog. It reports positive fit, gaps, article-type alignment, the bound standard version, and official sources. Impact factor is not a ranking feature and the module never predicts acceptance probability.

Before structured drafting, an agent must bind the journal ID, article type, standard version, catalog digest, official sources, and review date. Field-level compliance checks then compare measured manuscript properties with the bound profile. Submission-ready status requires every exact rule to pass, every required section and declaration to be present, every unresolved field to be checked, and the official source to be revisited immediately before submission.

## Updating and extending the catalog

History is immutable. A journal update creates a new version, changes only fields supported by current official evidence, regenerates the digest, and reruns completeness, recommendation, and compliance regression tests. Previous manuscripts therefore retain the standard that governed their preparation. A newly added journal must provide the same structured record and tests; a name and URL alone are insufficient.
