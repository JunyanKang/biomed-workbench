# Chromatin Contact Evidence

`cool-contact-evidence` reads a single-resolution project `.cool` file and a BED table in which every regulatory element is explicitly labeled `enhancer` or `promoter`. It identifies same-chromosome enhancer-promoter bin pairs and reports the observed pixel count together with the median count for all available cis pixels at the same bin distance. Input and output digests, contact assay, genome build, replicate identity, and exact parameter policy are retained.

The implementation is intentionally strict: it refuses a non-Cooler HDF5 layout, inconsistent bin or pixel arrays, ambiguous element-to-bin mapping, missing element types, mutable source files, or an existing report path. It never guesses whether a feature is an enhancer or promoter and does not silently substitute a matrix or add synthetic contacts.

The resulting values are descriptive contact evidence, not loop calls, p values, TADs, balanced contact scores, enhancer-promoter assignments, or functional regulation. Coverage, copy-number effects, normalization selection, replicate concordance, loop calling, and orthogonal perturbation evidence must be handled in separately declared analyses before a biological claim is made.
