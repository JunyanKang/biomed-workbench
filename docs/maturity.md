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

Eight independent axes are reported for every released capability: contract validity, static adapter reachability, fixture declaration, receipt-bound controlled fixture execution and reload, process-JSON round trip, serialized artifact-payload reload, representative or public-case acceptance, and current-project review. They are never collapsed into one maturity count. A case file proves only declaration. An isolated execution receipt records module/version/compatibility identity, case digest, complete normalized output digest, validated projection digest, actual runtime versions, reload method, and round-trip kind. A process result decoded from JSON is reported separately from a serialized scientific artifact that was independently reopened. Reachable code is not proof of execution, and a representative case is not proof that the current project produced and reviewed a result. Generic entry surfaces therefore never declare scientific completion before the project review and decision events exist.

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

For a user project, the final maturity decision is always made at project
validation level. Project validation requires an approved analysis admission,
observed execution, content-addressed output import, result reload, scientific
review, an explicit decision, and evidence-map registration. Failed or unrun
gates remain visible, experimental modules are not promoted by prose, and a
successful process exit is never sufficient.
