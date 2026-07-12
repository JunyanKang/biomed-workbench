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

Route the objective:

```bash
python3 "$WORKBENCH_ROOT/tools/route_task.py" "USER OBJECTIVE"
```

Inspect an exact capability contract or refine a broad route:

```bash
python3 "$WORKBENCH_ROOT/tools/search_tools.py" --id CAPABILITY_ID
python3 "$WORKBENCH_ROOT/tools/search_tools.py" --workflow WORKFLOW "SEARCH TERMS"
```

Execute a bounded capability with a JSON object. Prefer `--input-file` when payloads are large or contain multiline scientific data.

```bash
python3 "$WORKBENCH_ROOT/tools/run_tool.py" CAPABILITY_ID --input '{"field":"value"}'
python3 "$WORKBENCH_ROOT/tools/run_tool.py" CAPABILITY_ID --input-file INPUT.json
```

Treat router candidates as recommendations. Verify the selected input schema, units, organism/build, identifiers, dependency readiness, and scientific compatibility before execution. Do not substitute a merely available capability for the analysis the question requires.

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

## Guardrails

- Do not expose, echo, persist, or serialize credentials. Pass optional credentials only through their documented environment variables.
- Require explicit permission for any capability whose contract is not `read_only`; preserve the exact approved scope.
- De-identify clinical data before downstream analysis and treat re-identification risk as a limitation, not a formatting issue.
- Validate sequence alphabet and orientation, genome assembly, species, units, group labels, missingness, sample independence, image dimensions, and clinical endpoint definitions as applicable.
- Never claim that a plan was executed, a job was submitted, a model was run, or an artifact was created unless the corresponding result was observed and checked.
