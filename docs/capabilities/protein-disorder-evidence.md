# Protein Disorder Tendency Evidence

`protein-disorder-evidence` retrieves a residue-aligned IUPred2A score profile
for one to twenty declared UniProt accessions. It uses the public,
accession-based JSON endpoint and records the observed service contract and
each request transport.

## What It Delivers

- A separate found or not-found record for every requested accession.
- The selected prediction mode (`long`, `short`, or `glob`), protein length,
  and one score from zero to one for every returned residue.
- Explicit contiguous spans computed from a user-declared score threshold and
  minimum length, with no hidden smoothing or segmentation model.
- Service and retrieval provenance required for later reuse of the profile.

## Appropriate Use

Use it after protein identity has been resolved, typically alongside
`uniprot-protein-evidence`, predicted or experimental structure evidence, and
sequence conservation. Ask an interpretable question, such as whether an
accession-bound sequence contains a high-scoring region that warrants a
construct, mutagenesis, or orthogonal structural follow-up.

## Boundaries

The scores are sequence-based disorder tendencies. A threshold span is neither
an experimentally demonstrated disordered region nor a protein domain, binding
site, functional element, or mechanism. The module deliberately does not send
arbitrary user sequences to a third-party service, install or redistribute the
upstream software, or infer a biological conclusion from the prediction alone.

The server and method are described by the [IUPred2A documentation](https://iupred2a.elte.hu/help_new).
