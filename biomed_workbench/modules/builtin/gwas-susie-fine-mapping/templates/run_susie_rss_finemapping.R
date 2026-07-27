#!/usr/bin/env Rscript
# Strict SuSiE-RSS fine-mapping template for already harmonized locus inputs.

require_runtime <- function() {
  packages <- c("susieR", "jsonlite", "digest")
  missing <- packages[!vapply(packages, requireNamespace, logical(1), quietly = TRUE)]
  if (length(missing)) stop(paste("missing required R packages:", paste(missing, collapse = ", ")), call. = FALSE)
  versions <- vapply(packages, function(package) as.character(utils::packageVersion(package)), character(1))
  list(R = R.version.string, packages = as.list(versions))
}

read_summary_statistics <- function(path) {
  sumstats <- read.delim(path, check.names = FALSE, stringsAsFactors = FALSE)
  required <- c("variant_id", "effect_allele", "other_allele", "beta", "se", "pvalue")
  if (!all(required %in% names(sumstats)) || anyDuplicated(sumstats$variant_id)) stop("summary statistics require unique variant_id plus effect_allele, other_allele, beta, se, pvalue", call. = FALSE)
  if (any(!is.finite(sumstats$beta)) || any(!is.finite(sumstats$se)) || any(sumstats$se <= 0) || any(!is.finite(sumstats$pvalue)) || any(sumstats$pvalue <= 0 | sumstats$pvalue > 1)) stop("summary statistics contain invalid beta, se, or pvalue", call. = FALSE)
  if (any(!grepl("^[ACGT]$", sumstats$effect_allele)) || any(!grepl("^[ACGT]$", sumstats$other_allele)) || any(sumstats$effect_allele == sumstats$other_allele)) stop("alleles must be distinct single A/C/G/T bases after harmonization", call. = FALSE)
  sumstats
}

read_and_validate_ld <- function(path, variant_ids) {
  ld <- as.matrix(read.delim(path, row.names = 1, check.names = FALSE))
  storage.mode(ld) <- "double"
  if (!identical(rownames(ld), variant_ids) || !identical(colnames(ld), variant_ids)) stop("LD row and column order must exactly equal summary variant_id order", call. = FALSE)
  if (any(!is.finite(ld)) || nrow(ld) != ncol(ld) || max(abs(ld - t(ld))) > 1e-8 || max(abs(diag(ld) - 1)) > 1e-6) stop("LD must be finite, symmetric, square, and correlation-scaled", call. = FALSE)
  eigenvalues <- eigen(ld, symmetric = TRUE, only.values = TRUE)$values
  if (min(eigenvalues) < -1e-8) stop("LD is not positive semidefinite; resolve ancestry, allele, variant, or reference-panel mismatch", call. = FALSE)
  list(matrix = ld, eigenvalues = eigenvalues)
}

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 6) stop("usage: summary.tsv ld.tsv sample_size L coverage report.json", call. = FALSE)
summary_path <- args[[1]]; ld_path <- args[[2]]; n <- as.integer(args[[3]])
L <- as.integer(args[[4]]); coverage <- as.numeric(args[[5]]); report_path <- args[[6]]
runtime <- require_runtime()
if (!is.finite(n) || n < 100 || !is.finite(L) || L < 1 || !is.finite(coverage) || coverage <= 0 || coverage >= 1) stop("invalid sample size, L, or credible-set coverage", call. = FALSE)
if (file.exists(report_path)) stop("report path must be new", call. = FALSE)

sha256 <- function(path) digest::digest(file = path, algo = "sha256")
sumstats <- read_summary_statistics(summary_path)
ld_evidence <- read_and_validate_ld(ld_path, sumstats$variant_id)
ld <- ld_evidence$matrix
eig <- ld_evidence$eigenvalues
z <- sumstats$beta / sumstats$se
if (any(!is.finite(z))) stop("nonfinite z scores", call. = FALSE)

fit <- susieR::susie_rss(z = z, R = ld, n = n, L = min(L, nrow(ld)), estimate_residual_variance = FALSE, refine = TRUE, max_iter = 100, tol = 1e-4)
if (!isTRUE(fit$converged)) stop("SuSiE failed to converge; do not interpret PIPs or credible sets", call. = FALSE)
cs <- susieR::susie_get_cs(fit, Xcorr = ld, coverage = coverage, min_abs_corr = 0.5)
pip <- as.numeric(fit$pip)
result <- data.frame(variant_id = sumstats$variant_id, effect_allele = sumstats$effect_allele, other_allele = sumstats$other_allele, beta = sumstats$beta, se = sumstats$se, pvalue = sumstats$pvalue, z = z, pip = pip)
result <- result[order(-result$pip, result$variant_id), ]
credible_sets <- lapply(seq_along(cs$cs), function(index) list(signal = index, variant_ids = sumstats$variant_id[cs$cs[[index]]], coverage = unname(cs$coverage[[index]]), min_abs_corr = if (!is.null(cs$purity)) unname(cs$purity[[index, "min.abs.corr"]]) else NULL))
report <- list(module_id = "gwas-susie-fine-mapping", module_version = "0.1.0", passed = TRUE, runtime = runtime, inputs = list(summary_sha256 = sha256(summary_path), ld_sha256 = sha256(ld_path), variant_count = nrow(sumstats), sample_size = n), parameters = list(L = L, coverage = coverage, estimate_residual_variance = FALSE, refine = TRUE, max_iter = 100), diagnostics = list(converged = fit$converged, ld_min_eigenvalue = min(eig), ld_max_eigenvalue = max(eig)), results = list(top_variants = utils::head(result, 100), credible_sets = credible_sets), quality_gate_ids = c("finemap-harmonization", "finemap-ld-validity", "finemap-convergence-and-credible-set", "finemap-claim-boundary"), limitations = c("Fine-mapping PIPs and credible sets are model- and LD-reference-dependent, not causal proof.", "This template does not impute variants, harmonize alleles, select loci, perform colocalization, establish a causal gene, or replace functional validation."))
dir.create(dirname(report_path), recursive = TRUE, showWarnings = FALSE)
jsonlite::write_json(report, report_path, auto_unbox = TRUE, pretty = TRUE, na = "null")
