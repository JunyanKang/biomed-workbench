# Journal targeting and manuscript standards

Biomed Workbench uses a machine-readable standards library rather than asking an agent to recall submission rules. Catalog version `2026.07.31` covers 54 high-level life-science and biomedical journals across Nature Portfolio, Science/AAAS, Cell Press, The Lancet, NEJM, JAMA, The BMJ, PNAS, EMBO Press, Genome Biology, Genome Research, Nucleic Acids Research, Bioinformatics, PLOS Biology, and related titles.

Authoritative files:

- active snapshot: `biomed_workbench/knowledge/journal_standards/v2026.07.31.json`
- active-version index: `biomed_workbench/knowledge/journal_standards/index.json`
- reproducible builder: `tools/build_journal_standards.py`

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
