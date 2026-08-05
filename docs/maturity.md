# Capability Maturity And Evidence

Biomed Workbench separates module maturity from the strength of evidence
available for a particular scientific use. A module marked `validated` has a
valid package, executable contract, compatibility row, regression case, and
representative end-to-end evidence. It is not automatically validated for every
organism, assay, cohort, chemistry, endpoint, or user dataset.

## Evidence Levels

| Level | What has been demonstrated | What remains unproven |
| --- | --- | --- |
| Contract | Manifest, schemas, artifacts, quality gates, entrypoint, and extension rules are structurally valid | Scientific runtime and outputs |
| Compatibility | A declared tool/dependency/input/output combination passes regression and representative execution | Other versions, platforms, formats, and study designs |
| Live acceptance | A current external tool, database, or stable public dataset passes the recorded quality gates | Generalization beyond the recorded source and parameters |
| Project validation | The user's actual inputs execute, reload, reconcile, and pass project-specific scientific gates | Claims beyond the sampled units, design, and observed evidence |

These levels are cumulative for a specific compatibility row. Evidence from one
row must not be transferred to another row merely because its version appears
inside an allowed range.

Eight independent axes are reported for every released capability: contract validity, static adapter reachability, fixture declaration, receipt-bound controlled fixture execution and reload, process-JSON round trip, serialized artifact-payload reload, representative or public-case acceptance, and current-project review. They are never collapsed into one maturity count. A case file proves only declaration. An isolated execution receipt records module/version/compatibility identity, case digest, complete normalized output digest, validated projection digest, actual runtime versions, reload method, and round-trip kind. The checked cross-host readiness catalog derives a separate portable identity from the case, module, compatibility row, validated projection, reload method, and round-trip kind; host-specific full-output and runtime digests remain in the observed run receipt and never become deterministic release metadata. A process result decoded from JSON is reported separately from a serialized scientific artifact that was independently reopened. Reachable code is not proof of execution, and a representative case is not proof that the current project produced and reviewed a result. Generic entry surfaces therefore never declare scientific completion before the project review and decision events exist.

Externally returned outputs are admitted through 18 explicitly implemented semantic families rather than one generated profile per port. Each family has a closed media-type dispatch, at least one positive fixture, and an adversarial negative fixture. Unknown artifact families and undeclared media types fail closed. The plugin reloads primary bytes, archives, matrices, HDF5 objects, coordinates, tables, figures, reports, or model bundles as appropriate; reconciles record and input accounting; and computes the admission metric itself. Caller-supplied quality booleans are not part of the accepted metadata schema. This admission establishes that the returned artifact satisfies its frozen structural and family-level scientific invariants; it releases the artifact to project review and does not replace that review.

For an externally executed workflow, runtime evidence is a structured object containing the observed workflow, the complete tool set, the complete dependency set, a tested-or-compatible policy, and the digest of the selected compatibility contract. Every identity must exactly cover the frozen row, every version must satisfy its rule, and a `tested` claim must equal a declared tested baseline. The handoff and return must carry the same compatibility-contract digest. Missing dependencies, substitute workflow names, out-of-range versions, and unbound runtime objects are rejected.

## Operational Labels

- `validated`: the checked package and its declared compatibility evidence pass.
- `experimental`: the module contract and templates are usable, but the
  scientific surface still needs broader backend, public-data, or project
  acceptance before routine use.
- `agent_generated`: Codex binds project artifacts and reviewed parameters to
  packaged command-line adapters, executes them without editing source code,
  inspects every output, and records observed versions and gates. A prepared
  execution plan is not evidence; only an observed, reloaded run can contribute
  evidence. Any module whose adapter still requires source editing is
  `scaffolded` and is blocked from the released capability surface.
- `offline`, `public_api`, and `codex_native`: these describe access and
  execution boundaries, not scientific maturity.

## Release Evidence

The release validator binds the registry to compatibility execution evidence,
live tool and database reports, public-data cases, template coverage, and the
research-state engine. The [public-data acceptance
case index](cases/README.md) shows the strongest current live examples. The
generated [experimental-module evidence matrix](../reports/experimental-module-maturity.json)
separately records contract, template, compatibility, representative execution,
public-data acceptance, and project-validation status for every experimental
module. A deterministic fixture can therefore never silently promote itself to
public-data evidence.

The deterministic readiness file remains portable across supported hosts. Every
CI run additionally uploads a timestamped, run-specific receipt archive that
retains the full controlled-fixture output digests, observed runtime versions,
executor identity, and an archive digest for 30 days. This operational archive
is intentionally separate from the checked registry and cannot change module
maturity by itself.

For a user project, the final maturity decision is always made at project
validation level. Project validation requires an approved analysis admission,
observed execution, content-addressed output import, result reload, scientific
review, an explicit decision, and evidence-map registration. Failed or unrun
gates remain visible, experimental modules are not promoted by prose, and a
successful process exit is never sufficient.
