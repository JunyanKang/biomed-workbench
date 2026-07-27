# ARCHS4 Public Expression Context

`archs4-expression-evidence` retrieves a bounded public expression overview
for one declared human or mouse gene from ARCHS4. It is a quick, reproducible
way to place a candidate gene in broad tissue or cell-line context before
forming a project-specific analysis plan.

## What It Returns

Select `tissue` or `cellline`, a species, and a gene symbol or stable identifier
token. The module retrieves the current public ARCHS4 CSV response and retains
only labelled rows with five valid, ordered numeric statistics: minimum, first
quartile, median, third quartile, and maximum. It ranks retained observations by
median expression and records the response URL, status, observed content type,
contract version, hierarchy-row count, malformed-row count, and truncation.

ARCHS4 includes hierarchy labels in the same CSV response. Those labels do not
have expression statistics and are counted but never presented as observations.
Likewise, a row with an invalid statistic order is rejected rather than silently
corrected.

## Scientific Use

Use the result to frame a question, prioritize follow-up tissue contexts, or
check whether a proposed mechanism is broadly plausible. Pair it with stable
identifier resolution when the gene token is uncertain, and use project data
with a declared design for differential expression, tissue specificity, disease
association, or cell-state claims.

ARCHS4 is a cross-study public resource. Its summaries do not establish that a
gene is differentially expressed in a disease, specific to a tissue or cell
type, causal for a phenotype, or active in a user's samples. Public context is
not a substitute for biological replication, covariate handling, or validation.

## Compatibility

The observed public contract is `expression-tissue-v1-observed-2026-07-23`.
The endpoint currently delivers CSV content with an observed `text/html` media
type, so the workbench validates the CSV schema and statistic order rather than
trusting the MIME label. Any missing required field, malformed response, or
invalid numeric summary blocks use of the evidence.
