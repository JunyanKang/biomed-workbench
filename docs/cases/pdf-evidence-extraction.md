# PDF Evidence Extraction Case

The executable module case contains a minimal one-page PDF represented as transport-safe base64. It verifies local parsing, page accounting, SHA-256 provenance, bounded extraction, and the mandatory untrusted-content label without depending on a remote document or a developer-machine path.

The unit tests additionally create a text-bearing PDF with a table of contents and a document containing directive-like text. They verify page text, outline destination validation, truncation accounting, and the content-boundary behavior.
