#!/usr/bin/env Rscript
# Group-held-out RR-BLUP genomic prediction for predeclared project data.

require_runtime <- function() {
  packages <- c("rrBLUP", "digest", "jsonlite")
  missing <- packages[!vapply(packages, requireNamespace, logical(1), quietly = TRUE)]
  if (length(missing)) stop(paste("missing required R packages:", paste(missing, collapse = ", ")), call. = FALSE)
  as.list(vapply(packages, function(package) as.character(utils::packageVersion(package)), character(1)))
}

sha256 <- function(path) digest::digest(file = path, algo = "sha256")

read_genotypes <- function(path) {
  table <- read.delim(path, check.names = FALSE, stringsAsFactors = FALSE)
  if (ncol(table) < 3 || names(table)[1] != "individual_id" || anyDuplicated(table$individual_id)) stop("genotype TSV requires unique individual_id plus at least two marker columns", call. = FALSE)
  markers <- as.matrix(table[-1])
  storage.mode(markers) <- "double"
  if (any(!is.finite(markers)) || any(markers < 0 | markers > 2) || any(abs(markers - round(markers)) > 1e-8)) stop("genotypes must be finite diploid 0/1/2 dosages after imputation", call. = FALSE)
  if (any(apply(markers, 2, function(column) length(unique(column)) < 2))) stop("monomorphic markers must be removed before prediction", call. = FALSE)
  list(ids = table$individual_id, markers = markers, marker_names = colnames(markers))
}

read_phenotypes <- function(path) {
  table <- read.delim(path, check.names = FALSE, stringsAsFactors = FALSE)
  if (!identical(names(table), c("individual_id", "phenotype")) || anyDuplicated(table$individual_id) || any(!is.finite(table$phenotype))) stop("phenotype TSV requires unique individual_id and finite phenotype columns", call. = FALSE)
  table
}

read_folds <- function(path, ids) {
  table <- read.delim(path, check.names = FALSE, stringsAsFactors = FALSE)
  if (!identical(names(table), c("individual_id", "fold")) || anyDuplicated(table$individual_id) || !setequal(table$individual_id, ids)) stop("fold TSV must map every analyzed individual exactly once to a declared fold", call. = FALSE)
  table$fold <- as.character(table$fold)
  if (length(unique(table$fold)) < 2 || any(!nzchar(table$fold))) stop("at least two nonempty declared folds are required", call. = FALSE)
  table
}

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 5) stop("usage: genotype.tsv phenotype.tsv folds.tsv trait_name report.json", call. = FALSE)
genotype_path <- args[[1]]; phenotype_path <- args[[2]]; folds_path <- args[[3]]; trait <- args[[4]]; report_path <- args[[5]]
if (!nzchar(trait) || file.exists(report_path)) stop("trait must be nonempty and report path must be new", call. = FALSE)
versions <- require_runtime()
genotype <- read_genotypes(genotype_path)
phenotype <- read_phenotypes(phenotype_path)
shared_ids <- intersect(genotype$ids, phenotype$individual_id)
if (length(shared_ids) < 20) stop("at least 20 phenotype-linked individuals are required", call. = FALSE)
geno_rows <- match(shared_ids, genotype$ids); phenotype <- phenotype[match(shared_ids, phenotype$individual_id), ]
folds <- read_folds(folds_path, shared_ids)
folds <- folds[match(shared_ids, folds$individual_id), ]
markers <- genotype$markers[geno_rows, , drop = FALSE]
predictions <- data.frame(individual_id = shared_ids, fold = folds$fold, observed = phenotype$phenotype, predicted = NA_real_)
fold_reports <- list()
for (fold in unique(folds$fold)) {
  test <- folds$fold == fold; train <- !test
  if (sum(train) < 15 || sum(test) < 3) stop("each declared fold requires at least 15 training and 3 held-out individuals", call. = FALSE)
  fit <- rrBLUP::mixed.solve(y = phenotype$phenotype[train], Z = markers[train, , drop = FALSE], method = "REML")
  predictions$predicted[test] <- as.numeric(fit$beta) + as.numeric(markers[test, , drop = FALSE] %*% fit$u)
  fold_reports[[fold]] <- list(training_n = sum(train), held_out_n = sum(test), Vg = fit$Vu, Ve = fit$Ve, held_out_rmse = sqrt(mean((predictions$observed[test] - predictions$predicted[test])^2)), held_out_correlation = cor(predictions$observed[test], predictions$predicted[test]))
}
if (any(!is.finite(predictions$predicted))) stop("prediction failed for one or more held-out individuals", call. = FALSE)
overall <- list(rmse = sqrt(mean((predictions$observed - predictions$predicted)^2)), correlation = cor(predictions$observed, predictions$predicted), bias_intercept = unname(coef(lm(observed ~ predicted, data = predictions))[1]), bias_slope = unname(coef(lm(observed ~ predicted, data = predictions))[2]))
report <- list(module_id = "rrblup-genomic-prediction", module_version = "0.1.0", passed = TRUE, runtime = versions, inputs = list(genotype_sha256 = sha256(genotype_path), phenotype_sha256 = sha256(phenotype_path), fold_sha256 = sha256(folds_path), individual_count = length(shared_ids), marker_count = ncol(markers), trait = trait), design = list(external_group_folds = unique(folds$fold), training_test_overlap = 0L), fold_results = fold_reports, overall_held_out_performance = overall, predictions = predictions, quality_gate_ids = c("genomic-prediction-input-contract", "genomic-prediction-fold-isolation", "genomic-prediction-fit-reload", "genomic-prediction-claim-boundary"), limitations = c("Held-out performance is conditional on the declared folds, trait definition, population structure and genotype processing.", "This template does not impute genotypes, infer ancestry, create folds, tune models, establish heritability, select parents, or establish causal marker effects."))
dir.create(dirname(report_path), recursive = TRUE, showWarnings = FALSE)
jsonlite::write_json(report, report_path, auto_unbox = TRUE, pretty = TRUE, na = "null")
