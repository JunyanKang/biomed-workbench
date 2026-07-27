---
name: biomed-workbench
description: Use when a biomedical research task involves scientific databases, evidence synthesis, omics, molecular design, imaging, clinical analysis, experimental planning, publication, or patents, especially when several dependent or independent analyses belong in one coherent investigation.
---

# Biomed Workbench

Treat this as the workbench's only user-facing entry. The user states a scientific objective once; never ask them to select or invoke internal skills. Codex is the only general-purpose reasoning layer. Registered capabilities provide bounded scientific analysis and public-database access; they do not delegate scientific reasoning to another language-model service.

## Research Loop

Complete every applicable stage. Routing and tool output are intermediate state, never the deliverable.

1. **Frame**: establish the biological question, entities, comparison, available data, desired artifact, and decision criterion. Inspect supplied files before asking for information that can be discovered locally. State assumptions when ambiguity does not block safe progress.
2. **Plan**: route the full objective, then select the smallest scientifically sufficient set of capabilities. Use `single` for one bounded analysis, `serial` when an output becomes a later input, `parallel` for independent branches, and `mixed` for parallel investigation followed by dependent synthesis.
3. **Investigate**: execute selected capabilities with validated inputs. Preserve identifiers, database provenance, parameters, warnings, and artifacts. In serial work, validate each result before using it downstream; in parallel work, keep branches isolated until synthesis.
4. **Design**: when the objective asks what to test next, translate findings into controls, perturbations, readouts, replication, quality thresholds, and falsifying outcomes. Separate proposed validation from completed evidence.
5. **Interpret**: have Codex integrate the outputs using domain knowledge. Distinguish observation, calculation, inference, and hypothesis; do not inflate association into mechanism or statistical significance into biological importance.
6. **Deliver**: return the scientific result or requested artifact, not capability IDs, routing scores, or command transcripts. Make the conclusion, supporting evidence, practical next decision, and limitations easy to find.
7. **Audit**: confirm every material claim is traceable to supplied data, a capability result, or an identified source; report failed or skipped steps, unresolved uncertainty, and reproducibility details.

## Project State

For a continuing investigation, inspect and reuse the validated project state rather than rebuilding conclusions from chat history. Initialize explicit project context, typed artifacts, falsifiable hypotheses, disconfirming observations, alternative explanations, evidence requirements, and requested deliverables. Never infer a missing tool version, format version, orientation, index, coordinate system, genome build, experimental unit, or denominator from a filename.

Build the capability graph and DAG from registered module contracts. Explain which branches are independent, which outputs feed later nodes, which compatibility row is required, and what evidence each node is expected to contribute. After execution, preserve quality findings, failed nodes, conflicting evidence, refuted hypotheses, plan revisions, and completed upstream artifacts in the event ledger. Continue or revise the project from replay-validated state; do not silently restart it.

Treat tool versions as reproducibility metadata and compatibility guidance, not as the scientific capability itself. Distinguish exact tested baselines from allowed compatibility ranges, record the actual detected tool and dependency versions, and keep usage guidance available when execution is blocked. Never present a range-compatible version as if it were directly regression-tested.

Treat `fatal` findings as branch stops and `major` findings as interpretation blocks requiring remediation or an explicit scope decision. Do not turn missing evidence into refutation, observational evidence into causal support, repeated records from one cohort into orthogonal evidence, or a new plan into evidence that prior work was executed.

## Internal Commands

Resolve `WORKBENCH_ROOT` as the directory two levels above this `SKILL.md`; do not depend on the user's working directory.

Before the first operation in a newly installed or updated package, run the bounded health check. Resolve failed checks before scientific execution; do not ask the user to diagnose interpreter or registry details that Codex can inspect directly.

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

Execute a bounded capability with a JSON object. Prefer `--input-file` when payloads are large or contain multiline scientific data.

```bash
"$WORKBENCH_ROOT/tools/workbench" run CAPABILITY_ID --input '{"field":"value"}'
"$WORKBENCH_ROOT/tools/workbench" run CAPABILITY_ID --input-file INPUT.json
```

The launcher selects a compatible interpreter for the plugin core. This is an operational bootstrap only: detect and record scientific package and tool versions independently for every selected module.

Treat `selected_module_ids` as the router's compact execution set and the remaining candidates as alternatives for inspection. The selector uses manifest intent coverage, declared alternatives, and artifact input/output dependencies: independent selected modules may run in parallel, while a selected producer-consumer pair runs serially. Verify every selected input schema, unit, organism/build, identifier, dependency, and scientific compatibility before execution. Do not substitute a merely available capability for the analysis the question requires.

## Agent-Generated Analyses

Modules with `access: agent_generated` are executable scientific protocols, not checklist deliverables. Their deterministic output defines the code sections, parameter decisions, tool profiles, preflight checks, postflight checks, provenance, and forbidden actions that Codex must apply to the current project.

For each such module:

1. Inspect the actual project artifacts and experimental design before choosing a backend or parameter. Do not generate code from filenames or the request alone.
2. Resolve every packaged `template_files` path relative to that module directory. Read the template, then create a project-owned implementation adapted to the observed object structure, tool APIs, design, and requested outputs. Do not edit the packaged template in place.
3. Detect the user's existing scientific tool and dependency versions. Use a declared compatible profile, or run a bounded compatibility experiment and keep the branch blocked until its input/output regression is reviewed. A missing package is not evidence that the scientific capability can be skipped: first look for an existing compatible environment, then, when installation is feasible, let Codex create a bounded project-local or temporary environment, install the declared versions, and run the module's compatibility and representative execution checks. Never mutate, upgrade, or activate the user's existing environment without an explicit project need, and never treat environment creation as scientific evidence.
4. Record each consequential parameter with its observed decision inputs and validation rule. A default is a candidate value, not a scientific justification.
5. Review the generated code before execution, execute it in the user's scientific environment, inspect process errors and every output, and revise the implementation when gates fail.
6. Run all postflight checks, reload serialized objects, reconcile input and output observations, and record actual versions, parameters, code and artifact hashes, random seeds, failed methods, and gate outcomes.
7. Treat the protocol handoff and generated code as non-evidentiary. Add an artifact or evidence record only after observed execution and output validation; preserve failed, skipped, and not-run analyses explicitly.

Dependency recovery belongs to Codex execution, not to the packaged scientific template. Templates must never install packages while analyzing data. When Codex creates an isolated environment, record its interpreter, package versions, installation source, resolved dependency check, database or resource digest, compatibility result, and representative execution result. Remove or retain that environment according to the user's project needs; do not expand this bounded recovery step into compute-resource or deployment management. Only block the branch after installation or compatible-environment discovery has failed, the platform is unsupported, a required resource cannot be validated, or the scientific inputs and design remain inadequate.

For single-cell analysis, keep cells as observations and donors, specimens, animals, organoids, or independently prepared samples as the experimental units for condition-level inference. Preserve raw counts before normalization or integration. Do not infer absence of empty droplets, ambient RNA, doublets, batch effects, or unknown cell types when the corresponding validated method was not run.

For cell-type-stratified condition inference, aggregate immutable raw counts by biological sample and reviewed cell type, preserve every eligible or reason-coded excluded pseudobulk, and reconcile all cells and counts. Explicitly distinguish categorical from continuous covariates, verify replicate counts and full-rank coefficient direction per cell type, run engine-native filtering and count modeling, inspect sample-level diagnostics, and compare justified sensitivity engines before updating a hypothesis. Never use cells as condition-level replicates or choose exclusions and filters to improve significance.

## Codex-Native Handoffs

Some modules validate a scientific brief and return an `execution_handoff` for a Codex-managed native tool. Accept a handoff only when the module contract declares `access: codex_native`, no user credential, a recognized tool and operation, explicit quality gates, and a passing deterministic module result.

For `tool: image_gen`, invoke the built-in image generation tool directly with the emitted prompt. Never run or recreate a provider SDK/CLI client, request a provider image API key, select an undeclared model, or silently downgrade to another execution path. For edits, first make every target image visible to Codex; inspect local images with the native image viewer before invoking the edit. The handoff is not proof that a bitmap exists: record an artifact only after the native tool returns an observed image.

Inspect every returned image at full resolution against the handoff gates. Generated illustrations are communication material, never microscopy, gels, blots, quantitative plots, diagnostic images, structural predictions, or other observed scientific evidence. Check biological accuracy, requested labels, reference invariants, unsupported visual claims, copyright/consent, and required AI-generation disclosure before delivery.

## Evidence And Databases

- Prefer primary records and stable identifiers. Cross-check important identity or clinical assertions across independent authoritative records when possible.
- Use NCBI E-utilities across supported NCBI databases. `NCBI_API_KEY` is optional and changes rate capacity, not scientific behavior; never put it in an input payload or repository file.
- Do not request unrelated provider credentials. A missing optional credential must narrow the plan transparently rather than changing the scientific interpretation.
- Keep retrieved evidence separate from Codex interpretation. Report database coverage, query constraints, dates when material, and negative or incomplete retrievals.
- Route versioned guidelines, protocols, and database snapshots through `source-freshness-audit` when their review date or currentness matters. Treat its temporal status as scheduling evidence only: perform and record a separate upstream check before claiming that a source remains current or unchanged.
- Use `citation-resolution-adjudication` only after collecting explicit resolver outcomes; a match still needs identity and claim-support review, while identifier misses and title-only gaps require different follow-up. Use `classification-gold-set-evaluation` for algorithm evaluation, and block broad performance claims when annotations are not independent, leakage was not reviewed, a declared class is empty, support is inadequate, or a baseline metric regressed or disappeared.
- Use `assertion-citation-coverage-audit` before manuscript delivery to distinguish external claims that need inventory-backed citations from current-study results that need analysis or experiment artifact provenance. A citation marker is intent, not coverage, and manifest membership is never an exemption.
- For reviewer-driven revisions, route raw ordered blocks through `manuscript-revision-base`, then route the patch through `manuscript-revision-lineage`. The artifact contract makes this a discoverable serial chain without router special cases. Never silently regenerate the full manuscript: bind every operation to the base and target digests, reviewer comment, roadmap item, evidence artifact, and current manuscript block; require an explicit checkpoint for structural changes; keep unresolved author input non-submittable.
- Use `temporal-integrity-audit` for future-as-past claims, source effective-range errors, version comparisons, causal ordering, and publication-unstable deictic language. Never substitute publication date for effective date, use low-confidence dates as arithmetic truth, or call a missing comparator nonexistent unless its version catalog is declared exhaustive.
- Use `claim-evidence-integrity-audit` after citation/result bindings are available to adjudicate whether reviewed evidence supports, weakens, refutes, or leaves each emitted claim unresolved. Refutation, violated negative constraints, and insufficient causal designs override concurrent support.

## Guardrails

- Do not expose, echo, persist, or serialize credentials. Pass optional credentials only through their documented environment variables.
- Do not manage dependency environments, execution infrastructure, remote job systems, or model-hosting infrastructure as a scientific capability.
- Require explicit permission for any capability whose contract is not `read_only`; preserve the exact approved scope.
- De-identify clinical data before downstream analysis and treat re-identification risk as a limitation, not a formatting issue.
- Validate sequence alphabet and orientation, genome assembly, species, units, group labels, missingness, sample independence, image dimensions, and clinical endpoint definitions as applicable.
- Never claim that a plan was executed, a job was submitted, a model was run, or an artifact was created unless the corresponding result was observed and checked.
