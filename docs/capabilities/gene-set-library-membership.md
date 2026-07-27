# Gene-Set Library Membership

`gene-set-library-membership` retrieves a bounded Enrichr JSON snapshot for one explicitly selected library. It preserves the requested library identity, returned terms, term members, truncation policy and HTTPS transport metadata without sending project gene lists to Enrichr.

The snapshot is an input to local `enrichment-analysis`, not a result. Before analysis, reconcile its identifier namespace and species with the project, freeze the retrieval provenance, declare the measured-gene background and retain multiple-testing correction. Library membership does not demonstrate pathway activity or mechanism.
