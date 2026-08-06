---
name: biomed-workbench
description: Use when a biomedical research task involves scientific databases, evidence synthesis, omics, molecular design, imaging, clinical analysis, experimental planning, publication, or patents, especially when several dependent or independent analyses belong in one coherent investigation.
---

# Biomed Workbench

This is the workbench's single research entry. The user states a scientific objective in ordinary language; the host agent resolves project context, compiles the scientific dependency graph, and coordinates registered capabilities without exposing internal module selection as user work. Codex is the primary reference host and the only host currently covered by the complete release path. Registered modules contribute bounded methods, data access, artifact contracts, and quality gates; the host reasoning layer remains responsible for cross-method reasoning, scientific review, and the final decision narrative. Another host may assume those responsibilities only through its own validated file, permission, runtime, artifact-reload, and evidence-delivery implementation; reading this Skill alone is not equivalent product certification. `access: codex_native` operations remain Codex-owned unless that host provides an independently validated equivalent.

## Research Loop

Complete every applicable stage. Routing and tool output are intermediate state, never the deliverable.

1. **Frame**: establish the biological question, entities, comparison, available data, desired artifact, and decision criterion. Inspect supplied files before asking for information that can be discovered locally. State assumptions when ambiguity does not block safe progress.
2. **Plan**: route the full objective, then select the smallest scientifically sufficient set of capabilities. Classify sequencing work by research scale, measurement family, assay, biological target, controls, and normalization strategy before choosing tools. Use `single` for one bounded analysis, `serial` when an output becomes a later input, `parallel` for independent branches, and `mixed` for parallel investigation followed by dependent synthesis.
3. **Investigate**: execute selected capabilities with validated inputs. Preserve identifiers, database provenance, parameters, warnings, and artifacts. In serial work, validate each result before using it downstream; in parallel work, keep branches isolated until synthesis.
4. **Design**: when the objective asks what to test next, translate findings into controls, perturbations, readouts, replication, quality thresholds, and falsifying outcomes. Separate proposed validation from completed evidence.
5. **Interpret**: have the host reasoning layer integrate the outputs using domain knowledge. Distinguish observation, calculation, inference, and hypothesis; do not inflate association into mechanism or statistical significance into biological importance.
6. **Deliver**: return the scientific result or requested artifact, not capability IDs, routing scores, or command transcripts. Make the conclusion, supporting evidence, practical next decision, and limitations easy to find.
7. **Map**: register each data, table, model, figure and panel in the scientific evidence map. Bind prerequisite conclusions, producing scripts, renderers, final files, captions, narrative sources, DOI records, paths and checksums before report generation.
8. **Audit**: confirm every material claim is traceable to supplied data, a reviewed capability result, or an identified source; report failed or skipped steps, unresolved uncertainty, decision history, and reproducibility details.

## Project State

For a continuing investigation, inspect and reuse the validated project state rather than rebuilding conclusions from chat history. Initialize explicit project context, typed artifacts, falsifiable hypotheses, disconfirming observations, alternative explanations, evidence requirements, and requested deliverables. Never infer a missing tool version, format version, orientation, index, coordinate system, genome build, experimental unit, or denominator from a filename.

Build the capability graph and DAG from registered module contracts. Explain which branches are independent, which outputs feed later nodes, which compatibility row is required, and what evidence each node is expected to contribute. After execution, preserve quality findings, failed nodes, conflicting evidence, refuted hypotheses, plan revisions, and completed upstream artifacts in the event ledger. Continue or revise the project from replay-validated state; do not silently restart it.

Treat classification dimensions as orthogonal rather than a single flat menu:

- `bulk`, `single-cell`, `spatial`, and `universal` describe the primary research scale;
- RNA abundance, chromatin occupancy, protein-RNA binding, translation, nascent transcription, accessibility, methylation, genome organization, and RNA modification describe measurement families;
- RNA-seq, CUT&Tag, RIP-seq, LACE-seq, Ribo-seq, GRO-seq and other named protocols are assays or assay families;
- S9.6 and other antibodies, proteins, epitopes, marks or molecular entities are targets;
- spike-in or other internal-reference scaling is a normalization strategy;
- RNase H treatment, matched input and IgG are specificity or background controls.

Never route a target, normalization method or specificity control as a peer assay. A universal tool belongs in the universal layer only when its scientific contract genuinely spans scales; an assay-specific tool remains attached to the assay even if its implementation library is reusable.

Use one approved `AnalysisAdmission` for every planned analysis. It must bind a falsifiable hypothesis, bilingual rationale, official API or primary-method sources, alternatives, assumptions, adjustable-parameter justifications, expected artifacts, acceptance criteria, and branch-blocking observations. Execution may begin only after these fields describe the actual project rather than a generic method.

Before reviewing a handoff-produced artifact, resolve every returned gate marked `requires_review` or `not_evaluable` through an exact manual `ScientificGateAdjudication` bound to the observed receipt, output port, gate-result digest and evidence-payload digest. A registered evaluator that returns `failed` must still produce a reloaded negative artifact; accept only the plugin-created automatic rejection whose evaluator identity, contract version, and packaged source digest exactly match the observed gate result. Never convert `requires_review` or `not_evaluable` into an automatic acceptance. Review every produced artifact through one bilingual `ArtifactReview`, including intermediate, negative, excluded, table, model and figure artifacts, and bind the review to the complete adjudication set. Rejected or unresolved gates require a major or fatal review and a non-retain action; they remain in the audit map but can never become active evidence. A not-evaluable gate can be retained only through `accepted-with-caveat` plus `retain-with-caveat`. Figure reviews must match the declared panel set exactly. Follow each review with an explicit `ScientificDecision` whose identity includes the adjudication-set digest: retain, retain with caveat, exclude, rerun, switch method, acquire data, revise the hypothesis or scope, or stop the branch. When review selects rerun or method switch, first prepare a child plan revision through the live registry and only then record the decision. The prepared node-level contract binds the source and target nodes, action, source and target module manifests, typed input and output mappings, observed and planned request identities, the complete mapped target-parameter object, scientific equivalence class, claim-scope transition, and rationale. Every output of one source execution must use the same contract, action, target, and request identity. Same-method reruns preserve the observed request identity and adjusted reruns freeze a different identity. A method switch is permitted only by a typed `revision_alternatives` relation; ordinary `alternatives` remain routing or recommendation relationships and are not executable substitutes. A `contract-equivalent` relation must retain the same quality-gate set. A `decision-role-alternative-with-method-specific-evidence` relation resets all source-specific gate conclusions and requires the target method's own execution, adjudication, review, and admission; `scope-downgrade` narrows the permitted claim. Obtain a new approved analysis admission for every replacement before execution.

Generate Chinese and English interpretation reports only from a validated `ScientificEvidenceMap`. A `project-snapshot` may describe qualified inputs, pending branches, failures and exclusions, but it never releases a publication-delivery node. Before one delivery node runs, publish a `delivery-authorization` map for that exact node: every transitive ancestor must be completed; every bound input must be retained under its exact identity; and all covered execution, reload, review, decision and plan-binding records must match the frozen upstream-slice digest. After the delivery output is reloaded, reviewed and retained, use `validated-delivery` for the terminal full-plan archive; it still requires every active-plan node to be completed and every exact leaf identity to carry the complete receipt chain. One completed output cannot cover an unfinished sibling merely because both share an artifact type. Recheck every path, SHA-256 and machine-readable edge table before rendering. Publish accepted map states through the append-only semantic-version mechanism; preserve the parent digest and classify interpretation changes as patch, minor or major.

Treat tool versions as reproducibility metadata and compatibility guidance, not as the scientific capability itself. Distinguish exact tested baselines from allowed compatibility ranges, record the actual detected tool and dependency versions, and keep usage guidance available when execution is blocked. For an external return, require a structured runtime object whose tool and dependency keys exactly cover the selected compatibility row, whose versions pass every frozen rule, and whose compatibility-contract digest matches the prepared handoff. A `tested` policy requires exact declared tested versions; a `compatible` policy permits only the recorded ranges. Never present a range-compatible version as if it were directly regression-tested.

Treat `fatal` findings as branch stops and `major` findings as interpretation blocks requiring remediation or an explicit scope decision. Do not turn missing evidence into refutation, observational evidence into causal support, repeated records from one cohort into orthogonal evidence, or a new plan into evidence that prior work was executed.

## Internal Commands

Resolve `WORKBENCH_ROOT` as the directory two levels above this `SKILL.md`; do not depend on the user's working directory.

Before the first operation in a newly installed or updated package, run the bounded health check. Resolve failed checks before scientific execution; do not ask the user to diagnose interpreter or registry details that the host agent can inspect directly.

```bash
"$WORKBENCH_ROOT/tools/workbench" doctor --strict
```

Compile the objective into one agent-ready research plan. This is the default entry after the health check; it exposes dependency layers, input/output contracts, parameter schema, packaged execution templates, quality gates, and unresolved project inputs without claiming that any analysis has run:

```bash
"$WORKBENCH_ROOT/tools/workbench" route "USER OBJECTIVE"
"$WORKBENCH_ROOT/tools/workbench" plan "USER OBJECTIVE"
```

Inspect an exact capability contract or refine a broad route:

```bash
"$WORKBENCH_ROOT/tools/workbench" search --id CAPABILITY_ID
"$WORKBENCH_ROOT/tools/workbench" search --workflow WORKFLOW "SEARCH TERMS"
```

Execute a bounded capability only after binding its project context, typed input artifacts, approved admission and exact compatibility row. The command persists a new, non-overwriting project state inside the project root; its `execution_status` is distinct from the later `scientific_status`. Prefer `--input-file` when parameters are large or multiline.

```bash
"$WORKBENCH_ROOT/tools/workbench" run CAPABILITY_ID --input-file PARAMETERS.json --project-root PROJECT_DIR --artifact-bindings PROJECT_BINDINGS.json --compatibility-row EXACT_ROW
```

For a continuing project, use the persisted state rather than reconstructing it from chat. `init` registers an initial state; `admit`, `adjudicate`, `review`, and `decide` append the required scientific judgements in that order; `prepare-revision` is inserted between review and a rerun or switch decision; `resume` advances only released nodes. Project-state schema v2 records migration provenance; a v1 state may migrate only after its original digest and event chain pass and every added adjudication field is recovered exactly from the bound receipt. For a map-bound v1 state, use the non-overwriting `migrate-state-v1` path with its immutable publication root. It verifies the version index, stored files, map bytes and publication identities, then reports the exact missing reviews, decisions, admissions, unresolved gates, required next revision, and parent digest. A schema-v2 file carrying migration contract `1.1.0` must not be loaded or edited in place: use `upgrade-state-migration-1-1` with the same immutable map root. The upgrade verifies the prior state and record digests, event chain, stored map entries, plan-node contract and map coverage, then writes a distinct `1.2.0` successor carrying the prior state and migration digests. If the old schema did not serialize prior admission, the migration records `historical-unavailable` rather than inventing approval. That record permits a project snapshot only: delivery authorization and validated delivery remain unavailable. A delivery-prerequisite result is `not-assessed` unless one or more exact `--delivery-node` values were supplied and processed by the normal delivery validator. Review and decide every migrated artifact explicitly, then publish a new project-snapshot map revision that continues the verified old parent. When a packaged external workflow returns from its recorded handoff, `ingest-execution` verifies the frozen observed-output contract digest, each port's closed result schema, exact output identity and provenance, required payload roles and media types, complete runtime compatibility, exit status, a format-specific container reload, and an explicitly registered scientific-family semantic profile. It imports payloads transactionally so a failed container or family admission cannot leave newly created orphan objects. Every returned output must carry JSON semantic metadata bound to the primary payload digest, module version, port, result schema, exact input artifact identities and digests, handoff request, compatibility contract, input/result accounting, limitations and empty-result reason. The metadata schema accepts neither caller-computed quality booleans nor a pass/fail verdict. The plugin reloads the primary bytes and applies the family and media-specific validator; this establishes file-family admission only. Every manifest gate remains independently traceable, and no gate is inferred from its name or promoted by family admission. Unknown families or media types fail closed. A filename, claimed media type, or self-reported quality label is never sufficient, and successful semantic admission releases an artifact only to gate-specific adjudication and bilingual project review. `map` publishes a project snapshot, an exact upstream delivery authorization, or a terminal validated-delivery archive according to the version contract. Inspect an interrupted map transaction first; use `map-recovery --complete` only for verified files-published/state-pending transactions, and `map-recovery --abort-prepared` only when the project state is unchanged and no staged, indexed, pointed-to, or immutable version exists.

```bash
"$WORKBENCH_ROOT/tools/workbench" project init --context CONTEXT.json --hypotheses HYPOTHESES.json --artifacts ARTIFACTS.json --plan PLAN.json --state PROJECT_STATE.json
"$WORKBENCH_ROOT/tools/workbench" project ingest-execution --state PROJECT_STATE.json --input OBSERVED_EXECUTION.json --project-root PROJECT_DIR
"$WORKBENCH_ROOT/tools/workbench" project adjudicate --state PROJECT_STATE.json --input GATE_ADJUDICATION.json
"$WORKBENCH_ROOT/tools/workbench" project review --state PROJECT_STATE.json --input ARTIFACT_REVIEW.json
"$WORKBENCH_ROOT/tools/workbench" project prepare-revision --state PROJECT_STATE.json --input REVISION_REQUEST.json
"$WORKBENCH_ROOT/tools/workbench" project decide --state PROJECT_STATE.json --input SCIENTIFIC_DECISION.json
"$WORKBENCH_ROOT/tools/workbench" project resume --state PROJECT_STATE.json --project-root PROJECT_DIR --evidence-map-root EVIDENCE_MAP_DIR
"$WORKBENCH_ROOT/tools/workbench" project map --state PROJECT_STATE.json --workspace PROJECT_DIR --specs EVIDENCE_UNITS.json --version MAP_VERSION.json --publish-root EVIDENCE_MAP_DIR
"$WORKBENCH_ROOT/tools/workbench" project map-recovery --state PROJECT_STATE.json --publish-root EVIDENCE_MAP_DIR
"$WORKBENCH_ROOT/tools/workbench" project map-recovery --complete --state PROJECT_STATE.json --publish-root EVIDENCE_MAP_DIR
"$WORKBENCH_ROOT/tools/workbench" project map-recovery --abort-prepared --state PROJECT_STATE.json --publish-root EVIDENCE_MAP_DIR
"$WORKBENCH_ROOT/tools/workbench" project migrate-state-v1 --legacy-state LEGACY_STATE.json --state PROJECT_STATE_V2.json --evidence-map-root EVIDENCE_MAP_DIR
"$WORKBENCH_ROOT/tools/workbench" project upgrade-state-migration-1-1 --prior-state PROJECT_STATE_CONTRACT_1_1.json --state PROJECT_STATE_CONTRACT_1_2.json --evidence-map-root EVIDENCE_MAP_DIR
```

The minimal revision request is a closed object. Use `target_module_id: null` for same-method reruns; method switches must name a typed revision-compatible target. `target_input_bindings` supplies only additional registered artifacts required by that relation.

```json
{
  "source_artifact_id": "artifact-reviewed-result",
  "action": "rerun-adjusted-parameters",
  "target_module_id": null,
  "target_input_bindings": {},
  "parameter_overrides": {"threads": 2},
  "rationale": "Repeat the reviewed analysis with the registered parameter adjustment."
}
```

Migration writes a new state file and returns a blocker summary such as:

```json
{
  "migration_status": "awaiting-scientific-dependency-recovery",
  "missing_analysis_admission_node_ids": [],
  "legacy_admission_recovery_node_ids": ["node-historical-analysis"],
  "missing_artifact_review_ids": ["artifact-historical-result"],
  "missing_scientific_decision_artifact_ids": ["artifact-historical-result"],
  "unresolved_gate_ids": [],
  "required_next_map_revision": 2,
  "required_parent_map_digest": "<verified SHA-256>",
  "delivery_permanently_blocked_by_legacy_recovery": true,
  "delivery_prerequisite_assessment_status": "not-assessed",
  "delivery_prerequisites_currently_satisfied": null,
  "delivery_prerequisite_checks": []
}
```

Inspect optional scientific-service credentials without exposing their values. Determine credential need from the exact implemented endpoint, not from the database name. Current public Crossref, Europe PMC, ClinicalTrials.gov, UniProt, Ensembl, Reactome, Open Targets, public cBioPortal and PubChem endpoints do not require a user API key. `NCBI_API_KEY` is optional for the implemented E-utilities and Datasets requests and increases service capacity. Private cBioPortal deployments, paid Crossref services, institutional proxies and future restricted endpoints require their own separately declared authentication contracts. When the user wants higher NCBI request capacity, offer the guided hidden-input flow and obtain permission before saving a credential:

```bash
"$WORKBENCH_ROOT/tools/workbench" credentials
"$WORKBENCH_ROOT/tools/workbench" credentials set NCBI_API_KEY
```

Treat AlphaFold Server as interactive browser access, not as an API-key credential. Check its recorded state before preparing a job. If it is unconfigured, authentication failed, the session expired, access was denied, quota is exhausted, or terms remain unreviewed, explain the exact next action and direct the user to the official page. Never request that a Google password be pasted into chat or write a password, OAuth token, cookie, or browser session into the workbench. Generate the official Server v1 import package, require user review and manual submission, and tag downloaded outputs as Server-origin. Never route Server outputs or derivatives to automated ligand/peptide docking or interaction prediction. Local AlphaFold 3 execution requires a passing live half-headroom resource gate and explicit user permission; do not download weights or databases, install a runtime, submit a job, or infer locally before both conditions hold.

The launcher selects a compatible interpreter for the plugin core. This is an operational bootstrap only: detect and record scientific package and tool versions independently for every selected module.

Treat `selected_module_ids` as the router's compact execution set and the remaining candidates as alternatives for inspection. The selector uses manifest intent coverage, declared alternatives, and artifact input/output dependencies: independent selected modules may run in parallel, while a selected producer-consumer pair runs serially. Verify every selected input schema, unit, organism/build, identifier, dependency, and scientific compatibility before execution. Do not substitute a merely available capability for the analysis the question requires.

## Packaged Parameterized Analyses

Modules with the historical registry value `access: agent_generated` are released as packaged, parameterized scientific workflows. The field identifies a Codex-controlled execution context; it does not authorize routine source generation or manual template adaptation. Their deterministic output defines the supported parameter surface, tool profiles, preflight and postflight checks, provenance, and blocked actions for the current project.

For each such module:

1. Inspect the actual project artifacts and experimental design before choosing a backend or parameter. Do not generate code from filenames or the request alone.
2. Resolve every packaged `template_files` path relative to the module directory and treat it as an immutable release asset. Bind project files and decisions through the declared CLI, request schema, configuration object, or other packaged parameter surface. Routine execution must not fork, rewrite, or patch the template.
3. Detect the user's existing scientific tool and dependency versions. Use a declared compatible profile, or run a bounded compatibility experiment and keep the branch blocked until its input/output regression is reviewed. A missing package is not evidence that the scientific capability can be skipped: first look for an existing compatible environment, then, when installation is feasible, let Codex create a bounded project-local or temporary environment, install the declared versions, and run the module's compatibility and representative execution checks. Never mutate, upgrade, or activate the user's existing environment without an explicit project need, and never treat environment creation as scientific evidence.
4. Record each consequential parameter with its observed decision inputs and validation rule. A default is a candidate value, not a scientific justification.
5. Inspect the packaged command and resolved configuration before execution, run it in the compatible project environment, and review process diagnostics and every declared output. Adjust supported parameters when gates fail; preserve the unsuccessful attempt and its reason.
6. Run all postflight checks, reload serialized objects, reconcile input and output observations, and record actual versions, parameters, code and artifact hashes, random seeds, failed methods, and gate outcomes.
7. Treat a protocol or configuration handoff as non-evidentiary. Before execution, freeze the per-port observed-result contract digest. On return, require closed content, declared payload roles and media types, every required manifest gate, its complete structured result, predeclared threshold, and a gate-evidence digest matching an imported payload. Resolve every pending gate through exact scientific adjudication before the artifact review; bind the retain decision to the adjudication-set digest. Add an artifact or evidence record only after admission, observed execution, reload validation, gate adjudication, bilingual review, and an explicit retain decision; preserve failed, skipped, and not-run analyses explicitly.

If a real project cannot be represented through the declared parameter surface, stop the branch and identify the missing contract. That module must return to plugin development for an official API-aligned adapter, schema, regression case, and release validation; an ad hoc project patch cannot be presented as a fully landed capability.

Dependency recovery belongs to Codex execution, not to the packaged scientific workflow. Templates must never install packages while analyzing data. When Codex creates an isolated environment, record its interpreter, package versions, installation source, resolved dependency check, database or resource digest, compatibility result, and representative execution result. Retain or remove that environment according to project needs. Only block the branch after installation or compatible-environment discovery has failed, the platform is unsupported, a required resource cannot be validated, or the scientific inputs and design remain inadequate.

For single-cell analysis, keep cells as observations and donors, specimens, animals, organoids, or independently prepared samples as the experimental units for condition-level inference. Preserve raw counts before normalization or integration. Do not infer absence of empty droplets, ambient RNA, doublets, batch effects, or unknown cell types when the corresponding validated method was not run.

For cell-type-stratified condition inference, aggregate immutable raw counts by biological sample and reviewed cell type, preserve every eligible or reason-coded excluded pseudobulk, and reconcile all cells and counts. Explicitly distinguish categorical from continuous covariates, verify replicate counts and full-rank coefficient direction per cell type, run engine-native filtering and count modeling, inspect sample-level diagnostics, and compare justified sensitivity engines before updating a hypothesis. Never use cells as condition-level replicates or choose exclusions and filters to improve significance.

For bulk sequencing, select assay-native evidence and quality gates. CUT&Tag requires a declared target or antibody and a separately declared control and normalization strategy. R-loop is a measurement family, not an assay: distinguish DRIP/DRIPc/sDRIP/qDRIP, R-ChIP, MapR and CUT&Tag by sensor, ex vivo or in situ context, fragmentation, sequenced moiety, strandedness, internal reference and RNase H control; preserve cross-method disagreement. Ribo-seq requires frame periodicity, P-site assignment and translated-ORF evidence; compare compatible callers such as Ribo-TISH and Ribotricer when discovery claims depend on caller behavior, and preserve disagreements. Protein-RNA binding assays require crosslinking, control and cluster-calling context; LACE-seq must not be presented as a complete official FASTQ-to-result pipeline when the cited authors' repository contains only paper-specific downstream scripts. Nascent-transcription assays require library-type-aware strand, end and pause interpretation. Experimental bulk modules remain non-validated until representative observed-data execution passes their promotion gates.

## Journal Targeting And Manuscript Compliance

Before recommending a journal or drafting to its format, run `journal-targeting-and-compliance` against the versioned catalog. Bind the project scope, audience, evidence maturity, article type and manuscript facts to one catalog version and record the selected profile version and official sources.

- Use audience, scientific remit, article family and evidentiary fit for recommendations; do not rank by invented acceptance probabilities or unsupported prestige scores.
- Enforce exact numeric constraints only when the selected official source publishes an exact value for that article type.
- Convert missing, conditional or article-type-dependent official values into explicit manual checks that block submission-ready status.
- Audit required sections, language style, figure/reporting expectations and policy fields individually; keep scope fit separate from format compliance.
- When instructions change, publish a new catalog version and retain the prior profile and fingerprint so an earlier drafting decision remains reproducible.
- Generate manuscript text from the project's validated evidence map; journal standards control form and audience calibration, not scientific facts.

## Codex-Native Handoffs

Some modules validate a scientific brief and return an `execution_handoff` for a Codex-managed native tool. Accept a handoff only when the module contract declares `access: codex_native`, no user credential, a recognized tool and operation, explicit quality gates, and a passing deterministic module result.

For `tool: image_gen`, invoke the built-in image generation tool directly with the emitted prompt. Never run or recreate a provider SDK/CLI client, request a provider image API key, select an undeclared model, or silently downgrade to another execution path. For edits, first make every target image visible to Codex; inspect local images with the native image viewer before invoking the edit. The handoff is not proof that a bitmap exists: record an artifact only after the native tool returns an observed image.

Inspect every returned image at full resolution against the handoff gates. Generated illustrations are communication material, never microscopy, gels, blots, quantitative plots, diagnostic images, structural predictions, or other observed scientific evidence. Check biological accuracy, requested labels, reference invariants, unsupported visual claims, copyright/consent, and required AI-generation disclosure before delivery.

## Evidence And Databases

- Prefer primary records and stable identifiers. Cross-check important identity or clinical assertions across independent authoritative records when possible.
- Use NCBI E-utilities and Datasets across supported NCBI endpoints. `NCBI_API_KEY` is optional and changes rate capacity, not scientific behavior. Read it through the credential service so the value remains outside requests, reports, project state and repository files; record only whether a key was used.
- Do not request unrelated provider credentials. A missing optional credential must narrow the plan transparently rather than changing the scientific interpretation.
- Keep retrieved evidence separate from Codex interpretation. Report database coverage, query constraints, dates when material, and negative or incomplete retrievals.
- Route versioned guidelines, protocols, and database snapshots through `source-freshness-audit` when their review date or currentness matters. Treat its temporal status as scheduling evidence only: perform and record a separate upstream check before claiming that a source remains current or unchanged.
- Use `citation-resolution-adjudication` only after collecting explicit resolver outcomes; a match still needs identity and claim-support review, while identifier misses and title-only gaps require different follow-up. Use `classification-gold-set-evaluation` for algorithm evaluation, and block broad performance claims when annotations are not independent, leakage was not reviewed, a declared class is empty, support is inadequate, or a baseline metric regressed or disappeared.
- Use `assertion-citation-coverage-audit` before manuscript delivery to distinguish external claims that need inventory-backed citations from current-study results that need analysis or experiment artifact provenance. A citation marker is intent, not coverage, and manifest membership is never an exemption.
- For reviewer-driven revisions, route raw ordered blocks through `manuscript-revision-base`, then route the patch through `manuscript-revision-lineage`. The artifact contract makes this a discoverable serial chain without router special cases. Never silently regenerate the full manuscript: bind every operation to the base and target digests, reviewer comment, roadmap item, evidence artifact, and current manuscript block; require an explicit checkpoint for structural changes; keep unresolved author input non-submittable.
- Use `temporal-integrity-audit` for future-as-past claims, source effective-range errors, version comparisons, causal ordering, and publication-unstable deictic language. Never substitute publication date for effective date, use low-confidence dates as arithmetic truth, or call a missing comparator nonexistent unless its version catalog is declared exhaustive.
- Use `claim-evidence-integrity-audit` after citation/result bindings are available to adjudicate whether reviewed evidence supports, weakens, refutes, or leaves each emitted claim unresolved. Refutation, violated negative constraints, and insufficient causal designs override concurrent support.

## Guardrails

- Keep credentials within the allowlisted credential service. Status output reports only configuration source; values remain absent from command arguments, logs, reports, artifacts and scientific state.
- Do not manage dependency environments, execution infrastructure, remote job systems, or model-hosting infrastructure as a scientific capability.
- Require explicit permission for any capability whose contract is not `read_only`; preserve the exact approved scope.
- De-identify clinical data before downstream analysis and treat re-identification risk as a limitation, not a formatting issue.
- Validate sequence alphabet and orientation, genome assembly, species, units, group labels, missingness, sample independence, image dimensions, and clinical endpoint definitions as applicable.
- Never claim that a plan was executed, a job was submitted, a model was run, or an artifact was created unless the corresponding result was observed and checked.
