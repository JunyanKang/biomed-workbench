# Capability Maturity And Project Evidence

Languages: [English](maturity.md) · [中文](maturity.zh-CN.md)

A registered contract, an executed implementation, a representative method case, and a current-project result are different things. Biomed Workbench no longer compresses them into one broad “validated” claim.

## Three Explicit Validation Labels

| Label | What has been confirmed | What cannot be inferred |
| --- | --- | --- |
| `engineering_validated` | The registered implementation executed a controlled case and reloaded its declared outputs | Suitability for every organism, platform, or study design |
| `method_validated` | Engineering validation is supplemented by a current representative or public scientific case | Completion of the current user project |
| `project_promoted` | One exact current-project result completed observed execution, reload, scientific review, retention, and project-lock checks | Claims beyond that project's design and observed evidence |

The module contract separately records inputs, outputs, parameters, compatible software, and quality gates. A complete contract is required before engineering validation, but is not itself one of the three labels above.

## How To Read Capability Labels

- **Historical manifest label `validated`:** a release registry contract class, not a user-facing conclusion about scientific completion; read it together with the three labels above.
- **Experimental:** the workflow and parameter interface are usable, but coverage of public data, external software, or real projects is not yet broad enough for a default workflow.
- **Plannable:** the workbench can explain the method's role and prepare an analysis plan, but it cannot describe the analysis as completed.

Access method, browser interaction, or agent-managed execution does not determine scientific maturity.

## Maturity Of Writing And Research Delivery

A validated writing capability means that its registered structure, input checks, and review rules can be executed. It does not mean that arbitrary prose has become a suitable manuscript. A paper, proposal, reviewer response, presentation, or patent-related technical package receives a project-level delivery judgment only after its research facts and citations are traceable, numbers agree with figures, claims remain within the evidence, statistical and data-availability reporting fits the study design, current journal or funder requirements have been checked, and the final files have been reopened.

Passing a content-preservation review means that the revision contains no detected undeclared change to numbers, results, equations, citations, terminology, or structure. It does not establish the correctness of the science or replace author confirmation. Mock review, journal recommendation, and generic manuscript checks are likewise decision support and cannot independently establish submission readiness or acceptance likelihood. See [Academic Writing, Publication, And Translation](capabilities/publication-and-translation.md) for the detailed capability area.

## What Counts For A User Project

For a user project, the decisive evidence is the observed run and result status, not the module name or release label. The workbench checks the actual inputs, software versions, parameters, output files, and quality results, then reopens the outputs for statistical and biological review.

Results are classified as `CANDIDATE`, `SENSITIVITY`, `FORMAL`, or `DEPRECATED`. Only `FORMAL` sets `project_promoted` and becomes eligible for a formal manuscript figure. See [Project Locks, Analysis Selection, And Result Status](project-governance.md) for the promotion rules. Failed, unrun, and indeterminate checks remain visible.

See [public-data cases](cases/README.md) for representative acceptance examples and [release notes](releases/README.md) for capability changes between versions.
