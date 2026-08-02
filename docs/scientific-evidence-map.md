# Scientific Evidence Map, Scientific Review, Versioning, And Bilingual Reporting

Biomed Workbench represents a project as an append-only scientific argument,
not as a folder of successful outputs. The project-level scientific evidence
map complements the module capability graph:

- the capability graph answers which registered tools can consume and produce
  artifact types;
- the evidence map answers why an analysis was admitted, which exact artifacts
  it used and produced, how each result was reviewed, whether the result became
  active evidence, and what decision it triggered.

The design specializes the W3C PROV entity/activity/derivation model and its
explicit revision and invalidation semantics. It follows FAIR requirements for
rich metadata and provenance, and the Nature Methods reproducibility principle
that complete automation and retained intermediate outputs are stronger than a
written recipe alone.

## Two Readable Layers

Layer 1 is a global cross-panel story DAG. It contains panel nodes and explicit
panel-to-panel dependencies only. Scripts, files, captions, and databases do not
clutter the top-level scientific story.

Layer 2 expands every data or Figure group into evidence mind maps. Each unit
records and links:

1. prerequisite data/panel and its prerequisite conclusion;
2. current registered data or panel;
3. plot-ready data;
4. analysis script;
5. layout or plotting renderer;
6. final data, PDF, or PNG;
7. caption;
8. narrative source and canonical original-study DOI.

Every file uses a normalized workspace-relative clickable path, media type, and
SHA-256. Reports re-read every path and checksum immediately before rendering;
a changed or missing file blocks report generation.

The same edge set is written as `scientific-evidence-map.edges.tsv`. Its digest
is embedded in the map and both reports. Modifying an edge without rebuilding
the map breaks the report gate.

## Admission Before Execution

Every planned analysis node requires one `AnalysisAdmission`. Approval requires:

1. a target hypothesis and scientific rationale in Chinese and English;
2. the method and official API or primary-method sources;
3. alternatives considered and why the selected method fits the design;
4. explicit assumptions and parameter-by-parameter justification;
5. expected artifact types;
6. acceptance criteria and observations that would falsify or block the branch.

Missing fields do not receive an inferred default. An unapproved node may remain
in the audit graph but cannot be treated as an authorized scientific analysis.

## Review Every Result

Every registered artifact, including negative, excluded, intermediate, data,
table, model, report, and figure artifacts, requires one bilingual
`ArtifactReview`. The review separates:

- technical validity;
- statistical validity and experimental-unit correctness;
- biological validity and claim scope;
- robustness, sensitivity, and conflicts;
- limitations and source support.

Figures require explicit panel records. An artifact-declared `panel_ids` set and
the review panel set must match exactly. A montage-level paragraph cannot stand
in for panel-level interpretation.

## Decide Without Deleting History

Every review requires one `ScientificDecision`. Supported actions are:

- retain as evidence;
- retain with caveat;
- exclude as invalid or noninformative;
- rerun the same method or adjusted parameters;
- switch method;
- acquire more data;
- revise the hypothesis or project scope;
- stop the branch.

Only the two retain actions enter the active evidence set, and major, fatal, or
unassessed reviews cannot be retained. Exclusion removes an artifact from active
claim support but never deletes it, its review, or the decision from the audit
chain. Revised hypotheses and plans receive new identities rather than mutating
the historical node.

## Two Separate Bilingual Deliverables

`write_bilingual_reports` accepts only a validated `ScientificEvidenceMap` and
the workspace root. It emits:

- `scientific-evidence-report.zh-CN.md`;
- `scientific-evidence-report.en.md`;
- `scientific-evidence-map.json`;
- `scientific-evidence-map.edges.tsv`;
- `scientific-evidence-map.md`, with a global Mermaid story DAG and grouped
  evidence mind maps.

Both language reports cover every project artifact and contain:

- Scientific rationale and hypothesis | 科学依据与假设;
- Methods | 分析方法;
- Results and scientific conclusion | 结果与科学结论;
- panel-level interpretation for figures;
- objective technical, statistical, biological, and robustness review;
- limitations, graph lineage, decision, and impact on the next analysis.

The English and Chinese documents are rendered from the same versioned evidence
map, preventing one language from silently omitting an artifact, panel,
limitation, file, checksum, caption, DOI, or decision. The report generator does
not independently reconstruct source relationships. The map also freezes the
complete hypothesis snapshot and the explicitly linked analysis-admission
records, including alternatives, assumptions, adjustable-parameter
justifications, acceptance criteria, falsification criteria, and official
method sources. Reports read these records directly from the map.

## Append-Only Version Management

Every map contains:

- semantic version;
- monotonically increasing revision;
- parent-map SHA-256;
- `initial`, `major`, `minor`, or `patch` change type;
- Chinese and English change summaries.

`publish_evidence_map_version` writes immutable releases under
`versions/v<semver>/`. It refuses to overwrite a version directory, requires
revision increments of exactly one, verifies the parent digest against the
latest version, and checks that semantic-version movement matches the declared
change type. The append-only `evidence-map-version-index.json` records map,
edge-table, and deliverable checksums. A compact
`scientific-evidence-map.current.json` pointer records only the current version
and digests. `verify_evidence_map_version_index` rechecks the complete parent
chain, project identity, semantic-version transitions, every published file,
the map digest recalculated from map content, and the edge-table digest
recalculated from the machine-readable edges. Updating an index checksum cannot
hide a scientifically altered map. Publication is serialized by a
project-scoped exclusive lock. An immutable version directory that is missing
from the append-only index, or an indexed directory that is missing from disk,
is treated as an interrupted/corrupt publication and blocks the next release
until it is audited.

Recommended classification:

- `patch`: caption, link, or metadata clarification without changing evidence
  state or scientific interpretation;
- `minor`: new data, panel, analysis branch, or non-breaking evidence addition;
- `major`: hypothesis/story restructuring, removal or reversal of active
  evidence, or a change that invalidates downstream interpretation.

## Sources

- [W3C PROV-O Recommendation](https://www.w3.org/TR/prov-o/)
- [FAIR Guiding Principles, Scientific Data](https://www.nature.com/articles/sdata201618)
- [RO-Crate specification](https://www.researchobject.org/ro-crate/1.1/)
- [Reproducibility standards for machine learning in the life sciences, Nature Methods](https://www.nature.com/articles/s41592-021-01256-7)
- [AiiDA automated provenance, Scientific Data](https://www.nature.com/articles/s41597-020-00638-4)
- [Nature Portfolio reporting summary](https://www.nature.com/documents/nr-reporting-summary-flat.pdf)
