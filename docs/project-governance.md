# Project Locks, Analysis Selection, And Result Status

Languages: [English](project-governance.md) · [中文](project-governance.zh-CN.md)

Biomed Workbench organises long-running projects around scientific questions and decisions. An available method is not automatically added to a project, and a successful process is not automatically eligible for a formal manuscript figure.

## Interpret The Question Before Selecting Methods

The workbench resolves assay, measurement target, controls, normalisation, and the biological relation being tested as separate dimensions. Negation and ambiguous terms remain explicit. For example, a secondary transcriptional effect is a downstream expression consequence rather than RNA secondary structure; in an S9.6 experiment, spike-in supports normalisation but does not replace RNase H specificity evidence.

A complex objective becomes independently reviewable scientific branches followed by one integration decision. Each scientific question receives, by default:

- one primary analysis that directly answers the question;
- one orthogonal validation with a distinct assumption, data layer, or error structure.

A third method enters execution only when it replaces a named analysis or supplies decision information that the approved pair does not provide. This limits repeated method switching and prevents several closely related analyses from being presented as independent support.

## The Project Lock

Before formal analysis, the project freezes the sample sheet, genome and annotation releases, cell annotation, biological replicate unit, thresholds, colour meanings, formal result directory, and manuscript-panel registry. Each file carries a version and content fingerprint.

Changing a locked item creates a new lock revision linked to its parent. Older results are not silently adapted by editing captions, moving folders, or renaming files; affected analyses and figures return to review.

## Four Result States

| Status | Meaning | Eligible for a formal manuscript figure? |
| --- | --- | --- |
| `CANDIDATE` | A result exists but still awaits sufficient review or comparison | No |
| `SENSITIVITY` | A result tests dependence on parameters, assumptions, or methods | No, unless later promoted |
| `FORMAL` | Observed execution, output reload, scientific review, retention decision, and project-lock checks are complete | Yes |
| `DEPRECATED` | The result has been replaced, excluded, or removed from the current claim | No |

Promotion from candidate or sensitivity status is not a label edit. The workbench checks the observed execution and reload chain, method-validation scope, bilingual scientific review, retained-evidence decision, experimental unit, project lock, and figure contract. A formal result still supports only the claims allowed by its design and observed evidence.

## Three Different Validation Questions

| Label | Question answered |
| --- | --- |
| `engineering_validated` | Did the registered implementation execute a controlled case and reload its declared outputs? |
| `method_validated` | Is there also a current representative or public scientific case for the method slice? |
| `project_promoted` | Has this exact current-project result passed formal promotion? |

These labels are not interchangeable. Engineering checks do not establish universal method fit, public cases do not complete a current project, and the historical manifest label `validated` describes a registry contract class rather than scientific completion.

## Results-First Project View

Routine interaction shows the scientific conclusion, key result, evidence boundary, current status, and next decision. Versions, content fingerprints, execution records, review chains, and full history remain available in the background and are expanded for reproducibility or when a blocking issue needs attention.

Figures, captions, Results prose, and bilingual reports continue to read the same version of the [Scientific Evidence Map](scientific-evidence-map.md), keeping project status, figure identities, and narrative sources aligned.
