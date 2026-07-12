# Privacy

Biomed Workbench processes supplied scientific data locally unless a registered public-database capability is selected. The current networked capabilities access NCBI E-utilities.

The plugin does not operate an independent data-collection service. It does not intentionally transmit project files, prompts, clinical records, or credentials to the plugin author. Requests sent to an external scientific database are governed by that database's privacy policy and terms.

`NCBI_API_KEY` is optional. It is read from the process environment, excluded from structured results and reports, and must not be stored in the repository or capability input payloads.

Users must de-identify sensitive human data and confirm that any external-database use is permitted by their institution, consent framework, and applicable law.
