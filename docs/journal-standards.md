# Journal targeting and manuscript standards

Biomed Workbench uses a machine-readable standards library rather than asking an agent to recall submission rules. Catalog version `2026.08.03` covers 100 high-level life-science and biomedical journals across general life science, basic and mechanistic biology, omics and computational methods, oncology, immunology, neuroscience, metabolism, cardiovascular science, infectious disease, public health, and major clinical specialties. The list is displayed in descending 2025 JIF order; JIF is not a journal-fit scoring feature.

Authoritative files:

- active snapshot: `biomed_workbench/knowledge/journal_standards/v2026.08.03.json`
- active-version index: `biomed_workbench/knowledge/journal_standards/index.json`
- reproducible builder: `tools/build_journal_standards.py`

## Journals currently covered

The following table maps one-to-one to the 100 profiles in catalog version `2026.08.03`. The field summary supports quick human browsing; targeting still reads each journal's complete audience, topic-fit, article-type, and study-design record.

The metric frame is the **2026 Journal Citation Reports (2025 data)**, [released by Clarivate on 17 June 2026](https://clarivate.com/news/clarivate-releases-journal-citation-reports-2026/). The impact-factor column therefore means the **2025 Journal Impact Factor (JIF)**, not the webpage access year. JCR quartiles are recorded separately for every subject category.

<!-- journal-coverage-table:start -->
| Journal | Publisher / publishing organization | JCR categories | JCR 2026 quartiles | 2025 JIF |
| --- | --- | --- | --- | ---: |
| [CA: A Cancer Journal for Clinicians](https://acsjournals.onlinelibrary.wiley.com/journal/15424863) | American Cancer Society · Wiley | Oncology (SCIE) | Oncology: Q1 | 685.2 |
| [Nature Reviews Molecular Cell Biology](https://www.nature.com/nrm/content) | Springer Nature · Nature Portfolio | Cell Biology (SCIE) | Cell Biology: Q1 | 118.0 |
| [The Lancet](https://www.thelancet.com/journals/lancet/home) | Elsevier · The Lancet Group | Medicine, General & Internal (SCIE) | Medicine, General & Internal: Q1 | 109.0 |
| [Nature Reviews Microbiology](https://www.nature.com/nrmicro/content) | Springer Nature · Nature Portfolio | Microbiology (SCIE) | Microbiology: Q1 | 104.6 |
| [Nature Reviews Clinical Oncology](https://www.nature.com/nrclinonc/content) | Springer Nature · Nature Portfolio | Oncology (SCIE) | Oncology: Q1 | 94.6 |
| [Nature Reviews Drug Discovery](https://www.nature.com/nrd/content) | Springer Nature · Nature Portfolio | Biotechnology & Applied Microbiology (SCIE)<br>Pharmacology & Pharmacy (SCIE) | Biotechnology & Applied Microbiology: Q1<br>Pharmacology & Pharmacy: Q1 | 91.2 |
| [New England Journal of Medicine](https://www.nejm.org/author-center/article-types) | Massachusetts Medical Society | Medicine, General & Internal (SCIE) | Medicine, General & Internal: Q1 | 84.5 |
| [Signal Transduction and Targeted Therapy](https://www.nature.com/sigtrans/) | Springer Nature | Biochemistry & Molecular Biology (SCIE)<br>Cell Biology (SCIE) | Biochemistry & Molecular Biology: Q1<br>Cell Biology: Q1 | 81.2 |
| [Annals of Oncology](https://www.annalsofoncology.org/content/authorinfo) | European Society for Medical Oncology · Elsevier | Oncology (SCIE) | Oncology: Q1 | 80.4 |
| [Nature Reviews Disease Primers](https://www.nature.com/nrdp/content) | Springer Nature · Nature Portfolio | Medicine, General & Internal (SCIE) | Medicine, General & Internal: Q1 | 79.8 |
| [World Psychiatry](https://onlinelibrary.wiley.com/page/journal/20515545/homepage/forauthors.html) | World Psychiatric Association · Wiley | Psychiatry (SCIE, SSCI) | Psychiatry: Q1 | 79.5 |
| [JAMA](https://jamanetwork.com/journals/jama/pages/instructions-for-authors) | American Medical Association | Medicine, General & Internal (SCIE) | Medicine, General & Internal: Q1 | 65.4 |
| [Nature Reviews Cancer](https://www.nature.com/nrc/content) | Springer Nature · Nature Portfolio | Oncology (SCIE) | Oncology: Q1 | 60.7 |
| [Cancer Cell](https://www.cell.com/cancer-cell/home) | Elsevier · Cell Press | Cell Biology (SCIE)<br>Oncology (SCIE) | Cell Biology: Q1<br>Oncology: Q1 | 56.1 |
| [Nature](https://www.nature.com/nature/for-authors/formatting-guide) | Springer Nature · Nature Portfolio | Multidisciplinary Sciences (SCIE) | Multidisciplinary Sciences: Q1 | 56.1 |
| [The BMJ](https://www.bmj.com/about-bmj/resources-authors/article-types) | BMJ Group | Medicine, General & Internal (SCIE) | Medicine, General & Internal: Q1 | 55.1 |
| [The Lancet Neurology](https://www.thelancet.com/journals/laneur/home) | Elsevier · The Lancet Group | Clinical Neurology (SCIE) | Clinical Neurology: Q1 | 54.6 |
| [Nature Medicine](https://www.nature.com/nm/content) | Springer Nature · Nature Portfolio | Biochemistry & Molecular Biology (SCIE)<br>Cell Biology (SCIE)<br>Medicine, Research & Experimental (SCIE) | Biochemistry & Molecular Biology: Q1<br>Cell Biology: Q1<br>Medicine, Research & Experimental: Q1 | 52.5 |
| [Nature Reviews Genetics](https://www.nature.com/nrg/content) | Springer Nature · Nature Portfolio | Genetics & Heredity (SCIE) | Genetics & Heredity: Q1 | 51.4 |
| [Nature Reviews Cardiology](https://www.nature.com/nrcardio/content) | Springer Nature · Nature Portfolio | Cardiac & Cardiovascular Systems (SCIE) | Cardiac & Cardiovascular Systems: Q1 | 50.2 |
| [Science](https://www.science.org/content/page/science-information-authors) | AAAS | Multidisciplinary Sciences (SCIE) | Multidisciplinary Sciences: Q1 | 47.3 |
| [Nature Reviews Immunology](https://www.nature.com/nri/content) | Springer Nature · Nature Portfolio | Immunology (SCIE) | Immunology: Q1 | 47.1 |
| [European Heart Journal](https://academic.oup.com/eurheartj/pages/General_Instructions) | European Society of Cardiology · Oxford University Press | Cardiac & Cardiovascular Systems (SCIE) | Cardiac & Cardiovascular Systems: Q1 | 45.3 |
| [Cell](https://www.cell.com/cell/home) | Elsevier · Cell Press | Biochemistry & Molecular Biology (SCIE)<br>Cell Biology (SCIE) | Biochemistry & Molecular Biology: Q1<br>Cell Biology: Q1 | 45.1 |
| [Journal of Clinical Oncology](https://ascopubs.org/jco/authors/manuscript-guidelines) | American Society of Clinical Oncology | Oncology (SCIE) | Oncology: Q1 | 44.7 |
| [Nature Biotechnology](https://www.nature.com/nbt/content) | Springer Nature · Nature Portfolio | Biotechnology & Applied Microbiology (SCIE) | Biotechnology & Applied Microbiology: Q1 | 44.5 |
| [Nature Reviews Bioengineering](https://www.nature.com/natrevbioeng/content) | Springer Nature | Engineering, Biomedical (SCIE)<br>Materials Science, Biomaterials (SCIE) | Engineering, Biomedical: Q1<br>Materials Science, Biomaterials: Q1 | 42.7 |
| [Molecular Cancer](https://molecular-cancer.biomedcentral.com/submission-guidelines) | Springer Nature · BMC | Biochemistry & Molecular Biology (SCIE)<br>Oncology (SCIE) | Biochemistry & Molecular Biology: Q1<br>Oncology: Q1 | 42.2 |
| [Circulation](https://www.ahajournals.org/circ/author-instructions) | American Heart Association · Wolters Kluwer | Cardiac & Cardiovascular Systems (SCIE)<br>Peripheral Vascular Disease (SCIE) | Cardiac & Cardiovascular Systems: Q1<br>Peripheral Vascular Disease: Q1 | 41.3 |
| [Journal of Hepatology](https://www.journal-of-hepatology.eu/content/authorinfo) | European Association for the Study of the Liver · Elsevier | Gastroenterology & Hepatology (SCIE) | Gastroenterology & Hepatology: Q1 | 40.1 |
| [Nature Reviews Endocrinology](https://www.nature.com/nrendo/content) | Springer Nature · Nature Portfolio | Endocrinology & Metabolism (SCIE) | Endocrinology & Metabolism: Q1 | 39.1 |
| [The Lancet Gastroenterology & Hepatology](https://www.thelancet.com/journals/langas/home) | Elsevier · The Lancet Group | Gastroenterology & Hepatology (SCIE) | Gastroenterology & Hepatology: Q1 | 39.1 |
| [Nature Nanotechnology](https://www.nature.com/nnano/content) | Springer Nature · Nature Portfolio | Materials Science, Multidisciplinary (SCIE)<br>Nanoscience & Nanotechnology (SCIE) | Materials Science, Multidisciplinary: Q1<br>Nanoscience & Nanotechnology: Q1 | 37.5 |
| [Cell Metabolism](https://www.cell.com/cell-metabolism/home) | Elsevier · Cell Press | Cell Biology (SCIE)<br>Endocrinology & Metabolism (SCIE) | Cell Biology: Q1<br>Endocrinology & Metabolism: Q1 | 37.0 |
| [The Lancet Diabetes & Endocrinology](https://www.thelancet.com/journals/landia/home) | Elsevier · The Lancet Group | Endocrinology & Metabolism (SCIE) | Endocrinology & Metabolism: Q1 | 36.3 |
| [Physiological Reviews](https://journals.physiology.org/author-info.physrev) | American Physiological Society | Physiology (SCIE) | Physiology: Q1 | 35.7 |
| [The Lancet Respiratory Medicine](https://www.thelancet.com/journals/lanres/home) | Elsevier · The Lancet Group | Critical Care Medicine (SCIE)<br>Respiratory System (SCIE) | Critical Care Medicine: Q1<br>Respiratory System: Q1 | 34.7 |
| [Nature Reviews Rheumatology](https://www.nature.com/nrrheum/content) | Springer Nature · Nature Portfolio | Rheumatology (SCIE) | Rheumatology: Q1 | 33.7 |
| [The Lancet Oncology](https://www.thelancet.com/journals/lanonc/home) | Elsevier · The Lancet Group | Oncology (SCIE) | Oncology: Q1 | 33.7 |
| [Molecular Plant](https://www.cell.com/molecular-plant/home) | Elsevier · Cell Press | Biochemistry & Molecular Biology (SCIE)<br>Plant Sciences (SCIE) | Biochemistry & Molecular Biology: Q1<br>Plant Sciences: Q1 | 32.7 |
| [Nature Reviews Neurology](https://www.nature.com/nrneurol/content) | Springer Nature · Nature Portfolio | Clinical Neurology (SCIE) | Clinical Neurology: Q1 | 31.2 |
| [Cell Research](https://www.nature.com/cr/authors-and-referees) | Springer Nature | Cell Biology (SCIE) | Cell Biology: Q1 | 31.1 |
| [Immunity](https://www.cell.com/immunity/home) | Elsevier · Cell Press | Immunology (SCIE) | Immunology: Q1 | 30.6 |
| [Gastroenterology](https://www.gastrojournal.org/content/authorinfo) | American Gastroenterological Association · Elsevier | Gastroenterology & Hepatology (SCIE) | Gastroenterology & Hepatology: Q1 | 29.7 |
| [Cancer Discovery](https://aacrjournals.org/cancerdiscovery/pages/instructions-for-authors) | American Association for Cancer Research | Oncology (SCIE) | Oncology: Q1 | 29.5 |
| [The Lancet Infectious Diseases](https://www.thelancet.com/journals/laninf/home) | Elsevier · The Lancet Group | Infectious Diseases (SCIE) | Infectious Diseases: Q1 | 29.4 |
| [European Urology](https://www.europeanurology.com/content/authorinfo) | European Association of Urology · Elsevier | Urology & Nephrology (SCIE) | Urology & Nephrology: Q1 | 29.1 |
| [Nature Reviews Neuroscience](https://www.nature.com/nrn/content) | Springer Nature · Nature Portfolio | Neurosciences (SCIE) | Neurosciences: Q1 | 29.0 |
| [Cancer Communications](https://onlinelibrary.wiley.com/page/journal/25233548/homepage/forauthors.html) | AAAS | Oncology (SCIE) | Oncology: Q1 | 28.4 |
| [Nature Methods](https://www.nature.com/nmeth/content) | Springer Nature · Nature Portfolio | Biochemical Research Methods (SCIE) | Biochemical Research Methods: Q1 | 28.3 |
| [Nature Cancer](https://www.nature.com/natcancer/content) | Springer Nature · Nature Portfolio | Oncology (SCIE) | Oncology: Q1 | 28.0 |
| [Nature Metabolism](https://www.nature.com/natmetab/content) | Springer Nature · Nature Portfolio | Endocrinology & Metabolism (SCIE) | Endocrinology & Metabolism: Q1 | 27.5 |
| [Nature Immunology](https://www.nature.com/ni/content) | Springer Nature · Nature Portfolio | Immunology (SCIE) | Immunology: Q1 | 26.5 |
| [The Lancet Public Health](https://www.thelancet.com/journals/lanpub/home) | Elsevier · The Lancet Group | Public, Environmental & Occupational Health (SCIE, SSCI) | Public, Environmental & Occupational Health: Q1 | 26.5 |
| [JAMA Internal Medicine](https://jamanetwork.com/journals/jamainternalmedicine/pages/instructions-for-authors) | American Medical Association | Medicine, General & Internal (SCIE) | Medicine, General & Internal: Q1 | 26.3 |
| [Nature Biomedical Engineering](https://www.nature.com/natbiomedeng/submission-guidelines/aip-and-formatting) | Springer Nature · Nature Portfolio | Engineering, Biomedical (SCIE) | Engineering, Biomedical: Q1 | 26.3 |
| [Nature Genetics](https://www.nature.com/ng/content) | Springer Nature · Nature Portfolio | Genetics & Heredity (SCIE) | Genetics & Heredity: Q1 | 25.5 |
| [The Lancet Digital Health](https://www.thelancet.com/journals/landig/home) | Elsevier · The Lancet Group | Medical Informatics (SCIE)<br>Medicine, General & Internal (SCIE) | Medical Informatics: Q1<br>Medicine, General & Internal: Q1 | 25.5 |
| [Trends in Cell Biology](https://www.cell.com/trends/cell-biology/home) | Elsevier · Cell Press | Cell Biology (SCIE) | Cell Biology: Q1 | 25.3 |
| [Nature Aging](https://www.nature.com/nataging/content) | Springer Nature | Cell Biology (SCIE)<br>Geriatrics & Gerontology (SCIE)<br>Neurosciences (SCIE) | Cell Biology: Q1<br>Geriatrics & Gerontology: Q1<br>Neurosciences: Q1 | 25.0 |
| [Blood](https://ashpublications.org/blood/pages/manuscript_types) | American Society of Hematology | Hematology (SCIE) | Hematology: Q1 | 23.9 |
| [Cellular & Molecular Immunology](https://www.nature.com/cmi/authors-and-referees) | Chinese Society for Immunology · Springer Nature | Immunology (SCIE) | Immunology: Q1 | 23.9 |
| [JAMA Oncology](https://jamanetwork.com/journals/jamaoncology/pages/instructions-for-authors) | American Medical Association | Oncology (SCIE) | Oncology: Q1 | 23.9 |
| [JAMA Neurology](https://jamanetwork.com/journals/jamaneurology/pages/instructions-for-authors) | American Medical Association | Clinical Neurology (SCIE) | Clinical Neurology: Q1 | 23.6 |
| [Cell Stem Cell](https://www.cell.com/cell-stem-cell/home) | Elsevier · Cell Press | Cell & Tissue Engineering (SCIE)<br>Cell Biology (SCIE) | Cell & Tissue Engineering: Q1<br>Cell Biology: Q1 | 23.3 |
| [Cell Host & Microbe](https://www.cell.com/cell-host-microbe/home) | Elsevier · Cell Press | Microbiology (SCIE)<br>Parasitology (SCIE)<br>Virology (SCIE) | Microbiology: Q1<br>Parasitology: Q1<br>Virology: Q1 | 23.2 |
| [Nature Cell Biology](https://www.nature.com/ncb/content) | Springer Nature · Nature Portfolio | Cell Biology (SCIE) | Cell Biology: Q1 | 22.7 |
| [Cancer Research](https://aacrjournals.org/cancerres/pages/instructions-for-authors) | American Association for Cancer Research | Oncology (SCIE) | Oncology: Q1 | 22.6 |
| [The Lancet Global Health](https://www.thelancet.com/journals/langlo/home) | Elsevier · The Lancet Group | Public, Environmental & Occupational Health (SCIE, SSCI) | Public, Environmental & Occupational Health: Q1 | 22.5 |
| [Journal of the American College of Cardiology](https://www.jacc.org/author-center) | American College of Cardiology · Elsevier | Cardiac & Cardiovascular Systems (SCIE) | Cardiac & Cardiovascular Systems: Q1 | 22.3 |
| [The Lancet Microbe](https://www.thelancet.com/journals/lanmic/home) | Elsevier · The Lancet Group | Infectious Diseases (SCIE)<br>Microbiology (SCIE) | Infectious Diseases: Q1<br>Microbiology: Q1 | 21.9 |
| [Trends in Cancer](https://www.cell.com/trends/cancer/home) | Elsevier · Cell Press | Oncology (SCIE) | Oncology: Q1 | 21.6 |
| [The Lancet Psychiatry](https://www.thelancet.com/journals/lanpsy/home) | Elsevier · The Lancet Group | Psychiatry (SCIE, SSCI) | Psychiatry: Q1 | 21.1 |
| [The Lancet Planetary Health](https://www.thelancet.com/journals/lanplh/home) | Elsevier · The Lancet Group | Environmental Sciences (SCIE)<br>Public, Environmental & Occupational Health (SCIE, SSCI) | Environmental Sciences: Q1<br>Public, Environmental & Occupational Health: Q1 | 20.5 |
| [The Lancet Haematology](https://www.thelancet.com/journals/lanhae/home) | Elsevier · The Lancet Group | Hematology (SCIE) | Hematology: Q1 | 20.4 |
| [Nature Neuroscience](https://www.nature.com/neuro/content) | Springer Nature · Nature Portfolio | Neurosciences (SCIE) | Neurosciences: Q1 | 20.3 |
| [Nature Microbiology](https://www.nature.com/nmicrobiol/content) | Springer Nature · Nature Portfolio | Microbiology (SCIE) | Microbiology: Q1 | 18.7 |
| [Nature Communications](https://www.nature.com/ncomms/submit/article) | Springer Nature · Nature Portfolio | Multidisciplinary Sciences (SCIE) | Multidisciplinary Sciences: Q1 | 18.1 |
| [npj Digital Medicine](https://www.nature.com/npjdigitalmed/submission-guidelines) | Springer Nature · Nature Portfolio | Health Care Sciences & Services (SCIE)<br>Medical Informatics (SCIE) | Health Care Sciences & Services: Q1<br>Medical Informatics: Q1 | 18.0 |
| [Neuron](https://www.cell.com/neuron/home) | Elsevier · Cell Press | Neurosciences (SCIE) | Neurosciences: Q1 | 16.9 |
| [Science Immunology](https://www.science.org/journal/sciimmunol/information-for-authors) | AAAS | Immunology (SCIE) | Immunology: Q1 | 16.4 |
| [Molecular Cell](https://www.cell.com/molecular-cell/home) | Elsevier · Cell Press | Biochemistry & Molecular Biology (SCIE)<br>Cell Biology (SCIE) | Biochemistry & Molecular Biology: Q1<br>Cell Biology: Q1 | 16.0 |
| [Science Translational Medicine](https://www.science.org/journal/stm/information-for-authors) | AAAS | Cell Biology (SCIE)<br>Medicine, Research & Experimental (SCIE) | Cell Biology: Q1<br>Medicine, Research & Experimental: Q1 | 15.6 |
| [Nucleic Acids Research](https://academic.oup.com/nar/pages/author-guidelines) | Oxford University Press | Biochemistry & Molecular Biology (SCIE) | Biochemistry & Molecular Biology: Q1 | 15.0 |
| [Cell Reports Medicine](https://www.cell.com/cell-reports-medicine/home) | Elsevier · Cell Press | Cell Biology (SCIE)<br>Medicine, Research & Experimental (SCIE) | Cell Biology: Q1<br>Medicine, Research & Experimental: Q1 | 14.0 |
| [Science Advances](https://www.science.org/journal/sciadv/information-for-authors) | AAAS | Multidisciplinary Sciences (SCIE) | Multidisciplinary Sciences: Q1 | 13.9 |
| [Nature Structural & Molecular Biology](https://www.nature.com/nsmb/content) | Springer Nature · Nature Portfolio | Biochemistry & Molecular Biology (SCIE)<br>Biophysics (SCIE)<br>Cell Biology (SCIE) | Biochemistry & Molecular Biology: Q1<br>Biophysics: Q1<br>Cell Biology: Q1 | 10.1 |
| [Proceedings of the National Academy of Sciences](https://www.pnas.org/author-center/submitting-your-manuscript) | National Academy of Sciences | Multidisciplinary Sciences (SCIE) | Multidisciplinary Sciences: Q1 | 9.5 |
| [Developmental Cell](https://www.cell.com/developmental-cell/home) | Elsevier · Cell Press | Cell Biology (SCIE)<br>Developmental Biology (SCIE) | Cell Biology: Q1<br>Developmental Biology: Q1 | 9.2 |
| [Genome Biology](https://genomebiology.biomedcentral.com/submission-guidelines) | Springer Nature · BMC | Biotechnology & Applied Microbiology (SCIE)<br>Genetics & Heredity (SCIE) | Biotechnology & Applied Microbiology: Q1<br>Genetics & Heredity: Q1 | 9.2 |
| [The EMBO Journal](https://www.embopress.org/page/journal/14602075/authorguide) | Springer Nature | Biochemistry & Molecular Biology (SCIE)<br>Cell Biology (SCIE) | Biochemistry & Molecular Biology: Q1<br>Cell Biology: Q1 | 8.4 |
| [Current Biology](https://www.cell.com/current-biology/home) | Elsevier · Cell Press | Biochemistry & Molecular Biology (SCIE)<br>Biology (SCIE)<br>Cell Biology (SCIE) | Biochemistry & Molecular Biology: Q1<br>Biology: Q1<br>Cell Biology: Q1 | 7.7 |
| [Scientific Data](https://www.nature.com/sdata/publish/submission-guidelines) | Springer Nature · Nature Portfolio | Multidisciplinary Sciences (SCIE) | Multidisciplinary Sciences: Q1 | 7.2 |
| [Science Signaling](https://www.science.org/journal/signaling/information-for-authors) | AAAS | Biochemistry & Molecular Biology (SCIE)<br>Cell Biology (SCIE) | Biochemistry & Molecular Biology: Q1<br>Cell Biology: Q1 | 7.0 |
| [PLOS Biology](https://journals.plos.org/plosbiology/s/submission-guidelines) | Public Library of Science | Biochemistry & Molecular Biology (SCIE)<br>Biology (SCIE) | Biochemistry & Molecular Biology: Q1<br>Biology: Q1 | 6.9 |
| [Molecular Systems Biology](https://www.embopress.org/page/journal/17444292/authorguide) | Springer Nature | Biochemistry & Molecular Biology (SCIE) | Biochemistry & Molecular Biology: Q1 | 6.7 |
| [Genome Research](https://genome.cshlp.org/site/misc/ifora.xhtml) | Cold Spring Harbor Laboratory Press | Biochemistry & Molecular Biology (SCIE)<br>Biotechnology & Applied Microbiology (SCIE)<br>Genetics & Heredity (SCIE) | Biochemistry & Molecular Biology: Q1<br>Biotechnology & Applied Microbiology: Q1<br>Genetics & Heredity: Q1 | 6.3 |
| [Communications Biology](https://www.nature.com/commsbio/submission-guidelines) | Springer Nature · Nature Portfolio | Biology (SCIE) | Biology: Q1 | 5.8 |
| [Bioinformatics](https://academic.oup.com/bioinformatics/pages/author-guidelines) | Oxford University Press | Biochemical Research Methods (SCIE)<br>Biotechnology & Applied Microbiology (SCIE)<br>Mathematical & Computational Biology (SCIE) | Biochemical Research Methods: Q1<br>Biotechnology & Applied Microbiology: Q1<br>Mathematical & Computational Biology: Q1 | 5.5 |
| [eLife](https://elifesciences.org/articles/research-article) | eLife Sciences Publications | Biology (ESCI) | Biology: Not ranked | Not assigned |
<!-- journal-coverage-table:end -->

Impact factors and quartiles are descriptive context for human comparison only. They are not recommendation features and are never used to predict acceptance.

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

A newly added journal must provide the same complete structured record; a name and URL alone are insufficient. Manuscript work remains bound to the selected standard version so later instruction changes do not silently alter an earlier review.
