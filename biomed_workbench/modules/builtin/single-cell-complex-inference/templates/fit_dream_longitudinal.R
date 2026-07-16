#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(BiocParallel)
  library(digest)
  library(edgeR)
  library(jsonlite)
  library(lme4)
  library(limma)
  library(splines)
  library(variancePartition)
})

parse_args <- function(values) {
  if (!length(values) || length(values) %% 2 != 0) stop("arguments must be --name value pairs", call. = FALSE)
  keys <- sub("^--", "", values[seq(1, length(values), 2)])
  if (any(keys == values[seq(1, length(values), 2)]) || anyDuplicated(keys)) stop("arguments are invalid or duplicated", call. = FALSE)
  setNames(as.list(values[seq(2, length(values), 2)]), keys)
}

required_arg <- function(args, name) {
  value <- args[[name]]
  if (is.null(value) || !nzchar(value)) stop("missing --", name, call. = FALSE)
  value
}

numeric_arg <- function(args, name, lower, upper = Inf, integer = FALSE) {
  value <- suppressWarnings(as.numeric(required_arg(args, name)))
  if (length(value) != 1 || !is.finite(value) || value < lower || value > upper || (integer && value != floor(value))) stop("invalid --", name, call. = FALSE)
  value
}

sha256 <- function(path) digest(path, algo = "sha256", file = TRUE, serialize = FALSE)

package_version_or_absent <- function(name) {
  if (!requireNamespace(name, quietly = TRUE)) return("not-installed")
  as.character(packageVersion(name))
}

validate_formula <- function(text, metadata_names) {
  formula_environment <- new.env(parent = environment())
  formula <- tryCatch(as.formula(text, env = formula_environment), error = function(error) stop("model formula cannot be parsed: ", conditionMessage(error), call. = FALSE))
  allowed_calls <- c("~", "+", "-", "*", ":", "/", "^", "|", "(", "ns", "bs", "poly", "factor", "scale", "I")
  symbols <- all.names(formula, functions = TRUE, unique = TRUE)
  unknown <- setdiff(symbols, c(metadata_names, allowed_calls))
  if (length(unknown)) stop("model formula contains unsupported names: ", paste(unknown, collapse = ", "), call. = FALSE)
  if (!length(lme4::findbars(formula))) stop("dream formula must declare at least one random effect", call. = FALSE)
  formula
}

standardize_top_table <- function(table, genes, cell_type, test_type, coefficient) {
  column <- function(name, fallback = NA_real_) if (name %in% names(table)) table[[name]] else rep(fallback, nrow(table))
  data.frame(
    gene_id = genes,
    cell_type = cell_type,
    test_type = test_type,
    coefficient = coefficient,
    log2_effect = column("logFC"),
    standard_error = if ("t" %in% names(table) && "logFC" %in% names(table)) abs(table$logFC / table$t) else rep(NA_real_, nrow(table)),
    average_expression = column("AveExpr"),
    statistic = if ("t" %in% names(table)) table$t else column("F"),
    statistic_kind = if ("t" %in% names(table)) "t" else "F",
    degrees_of_freedom = column("df.total"),
    p_value = column("P.Value"),
    fdr = column("adj.P.Val"),
    z_standardized = column("z.std"),
    stringsAsFactors = FALSE,
    check.names = FALSE
  )
}

extract_messages <- function(fit, name) {
  value <- fit[[name]]
  if (is.null(value)) value <- attr(fit, name)
  if (is.null(value)) return(character())
  unique(as.character(unlist(value)))
}

main <- function() {
  args <- parse_args(commandArgs(trailingOnly = TRUE))
  counts_path <- normalizePath(required_arg(args, "counts"), mustWork = TRUE)
  metadata_path <- normalizePath(required_arg(args, "metadata"), mustWork = TRUE)
  results_path <- required_arg(args, "results")
  variance_path <- required_arg(args, "variance-results")
  diagnostics_path <- required_arg(args, "diagnostics")
  if (any(file.exists(c(results_path, variance_path, diagnostics_path)))) stop("refusing to overwrite declared outputs", call. = FALSE)
  lapply(c(results_path, variance_path, diagnostics_path), function(path) dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE))

  formula_text <- required_arg(args, "formula")
  variance_formula_text <- required_arg(args, "variance-formula")
  coefficient_pattern <- required_arg(args, "coefficient-pattern")
  ddf <- required_arg(args, "ddf")
  if (!ddf %in% c("adaptive", "Satterthwaite", "Kenward-Roger")) stop("unsupported dream degrees-of-freedom method", call. = FALSE)
  min_count <- numeric_arg(args, "min-count", 0)
  min_samples <- numeric_arg(args, "min-samples-expressed", 2, integer = TRUE)
  min_subjects <- numeric_arg(args, "min-subjects", 2, integer = TRUE)
  min_repeated_subjects <- numeric_arg(args, "min-repeated-subjects", 2, integer = TRUE)
  fdr_threshold <- numeric_arg(args, "fdr-threshold", .Machine$double.eps, 1 - .Machine$double.eps)

  count_table <- read.delim(counts_path, check.names = FALSE, stringsAsFactors = FALSE)
  if (!"gene_id" %in% names(count_table) || anyDuplicated(count_table$gene_id) || any(!nzchar(trimws(count_table$gene_id)))) stop("count table requires unique nonempty gene_id values", call. = FALSE)
  genes <- as.character(count_table$gene_id)
  counts <- as.matrix(count_table[, setdiff(names(count_table), "gene_id"), drop = FALSE])
  storage.mode(counts) <- "numeric"
  rownames(counts) <- genes
  if (!nrow(counts) || ncol(counts) < 4 || any(!is.finite(counts)) || any(counts < 0) || any(abs(counts - round(counts)) > 1e-8)) stop("counts must be a finite nonnegative integer-like gene-by-pseudobulk matrix", call. = FALSE)

  metadata <- read.delim(metadata_path, check.names = FALSE, stringsAsFactors = FALSE)
  required <- c("pseudobulk_id", "biological_sample", "subject", "cell_type", "condition", "time", "n_cells", "library_size", "eligible", "exclusion_reason")
  missing <- setdiff(required, names(metadata))
  if (length(missing)) stop("pseudobulk metadata is missing: ", paste(missing, collapse = ", "), call. = FALSE)
  if (anyDuplicated(metadata$pseudobulk_id) || !setequal(colnames(counts), metadata$pseudobulk_id)) stop("count columns and pseudobulk metadata do not align exactly", call. = FALSE)
  metadata <- metadata[match(colnames(counts), metadata$pseudobulk_id), , drop = FALSE]
  if (any(is.na(metadata)) || any(!is.finite(metadata$time))) stop("model metadata contains missing or nonfinite values", call. = FALSE)
  metadata$subject <- factor(metadata$subject)
  metadata$condition <- factor(metadata$condition)
  metadata$cell_type <- factor(metadata$cell_type)
  for (name in names(metadata)) if (is.character(metadata[[name]]) && !name %in% c("pseudobulk_id", "biological_sample", "exclusion_reason")) metadata[[name]] <- factor(metadata[[name]])

  formula <- validate_formula(formula_text, names(metadata))
  variance_formula <- validate_formula(variance_formula_text, names(metadata))
  random_variables <- unique(unlist(lapply(lme4::findbars(formula), function(term) all.vars(term[[3]]))))
  if (!length(random_variables) || any(!random_variables %in% names(metadata))) stop("random-effect variables are absent from metadata", call. = FALSE)
  if (!"subject" %in% random_variables) stop("longitudinal dream models must include subject as a random effect", call. = FALSE)

  all_results <- list()
  all_variance <- list()
  analyses <- list()
  for (cell_type in levels(droplevels(metadata$cell_type))) {
    selected <- metadata$cell_type == cell_type & as.logical(metadata$eligible)
    design_data <- droplevels(metadata[selected, , drop = FALSE])
    cell_counts <- counts[, selected, drop = FALSE]
    rownames(design_data) <- design_data$pseudobulk_id
    if (!identical(colnames(cell_counts), rownames(design_data))) stop("pseudobulk count columns and model metadata row names differ", call. = FALSE)
    if (ncol(cell_counts) < 4) stop("cell type has too few eligible pseudobulks: ", cell_type, call. = FALSE)
    subject_table <- table(design_data$subject)
    repeated_subjects <- names(subject_table)[subject_table >= 2]
    if (length(subject_table) < min_subjects || length(repeated_subjects) < min_repeated_subjects) stop("cell type lacks required subjects or repeated measurements: ", cell_type, call. = FALSE)
    for (variable in random_variables) {
      levels_with_repeats <- sum(table(design_data[[variable]]) >= 2)
      if (levels_with_repeats < 2) stop("random effect lacks repeated levels in cell type ", cell_type, ": ", variable, call. = FALSE)
    }

    fixed_formula <- lme4::nobars(formula)
    fixed_design <- model.matrix(fixed_formula, data = design_data)
    if (qr(fixed_design)$rank != ncol(fixed_design)) stop("fixed-effect design is rank deficient for cell type: ", cell_type, call. = FALSE)
    y <- edgeR::DGEList(counts = cell_counts)
    keep <- rowSums(cell_counts >= min_count) >= min_samples & edgeR::filterByExpr(y, design = fixed_design)
    if (sum(keep) < 2) stop("too few genes pass expression filtering for cell type: ", cell_type, call. = FALSE)
    y <- edgeR::calcNormFactors(y[keep, , keep.lib.sizes = FALSE], method = "TMM")
    parameter <- BiocParallel::SerialParam(progressbar = FALSE)
    voomed <- variancePartition::voomWithDreamWeights(y, formula, design_data, normalize.method = "none", plot = FALSE, BPPARAM = parameter)
    fit <- variancePartition::dream(voomed, formula, design_data, ddf = ddf, BPPARAM = parameter)
    fit <- variancePartition::eBayes(fit)
    available <- colnames(fit$coefficients)
    coefficients <- grep(coefficient_pattern, available, value = TRUE, perl = TRUE)
    if (!length(coefficients)) stop("coefficient pattern matched no fitted coefficients for cell type ", cell_type, "; available: ", paste(available, collapse = ", "), call. = FALSE)
    for (coefficient in coefficients) {
      table <- variancePartition::topTable(fit, coef = coefficient, number = Inf, sort.by = "none")
      all_results[[length(all_results) + 1]] <- standardize_top_table(table, rownames(table), cell_type, "coefficient", coefficient)
    }
    if (length(coefficients) > 1) {
      table <- variancePartition::topTable(fit, coef = coefficients, number = Inf, sort.by = "none")
      all_results[[length(all_results) + 1]] <- standardize_top_table(table, rownames(table), cell_type, "joint", paste(coefficients, collapse = ";"))
    }

    variance <- variancePartition::fitExtractVarPartModel(voomed$E, variance_formula, design_data, BPPARAM = parameter)
    variance$gene_id <- rownames(variance)
    variance_long <- reshape(
      as.data.frame(variance, check.names = FALSE), varying = setdiff(names(variance), "gene_id"),
      v.names = "variance_fraction", timevar = "variance_component", times = setdiff(names(variance), "gene_id"),
      idvar = "gene_id", direction = "long"
    )
    rownames(variance_long) <- NULL
    variance_long$cell_type <- cell_type
    all_variance[[length(all_variance) + 1]] <- variance_long[, c("gene_id", "cell_type", "variance_component", "variance_fraction")]
    analyses[[cell_type]] <- list(
      pseudobulks = ncol(cell_counts), subjects = length(subject_table), repeated_subjects = length(repeated_subjects),
      retained_genes = sum(keep), fixed_design_columns = colnames(fixed_design), fixed_design_rank = qr(fixed_design)$rank,
      random_variables = random_variables, tested_coefficients = coefficients,
      dream_errors = extract_messages(fit, "errors"), dream_warnings = extract_messages(fit, "warnings")
    )
  }

  results <- do.call(rbind, all_results)
  results$global_fdr <- p.adjust(results$p_value, method = "BH")
  results$significant <- !is.na(results$fdr) & results$fdr <= fdr_threshold
  results <- results[order(results$cell_type, results$test_type, results$p_value, results$gene_id), , drop = FALSE]
  variances <- do.call(rbind, all_variance)
  variances <- variances[order(variances$cell_type, variances$gene_id, variances$variance_component), , drop = FALSE]
  write.table(results, results_path, sep = "\t", quote = FALSE, row.names = FALSE, na = "NA")
  write.table(variances, variance_path, sep = "\t", quote = FALSE, row.names = FALSE, na = "NA")

  reloaded_results <- read.delim(results_path, check.names = FALSE, stringsAsFactors = FALSE)
  reloaded_variance <- read.delim(variance_path, check.names = FALSE, stringsAsFactors = FALSE)
  if (nrow(reloaded_results) != nrow(results) || nrow(reloaded_variance) != nrow(variances) || anyDuplicated(reloaded_results[, c("gene_id", "cell_type", "test_type", "coefficient")]) || any(!is.finite(reloaded_results$p_value))) stop("dream result reload validation failed", call. = FALSE)
  if (any(reloaded_variance$variance_fraction < -1e-8 | reloaded_variance$variance_fraction > 1 + 1e-8, na.rm = TRUE)) stop("variance fractions are outside the expected range", call. = FALSE)

  diagnostics <- list(
    schema_version = 1, engine = "variancePartition-dream", formula = formula_text, variance_formula = variance_formula_text, coefficient_pattern = coefficient_pattern,
    degrees_of_freedom_method = ddf, thresholds = list(min_count = min_count, min_samples_expressed = min_samples, min_subjects = min_subjects, min_repeated_subjects = min_repeated_subjects, fdr = fdr_threshold),
    input = list(counts_filename = basename(counts_path), counts_sha256 = sha256(counts_path), metadata_filename = basename(metadata_path), metadata_sha256 = sha256(metadata_path)),
    analyses = analyses,
    output = list(results_filename = basename(results_path), results_sha256 = sha256(results_path), variance_filename = basename(variance_path), variance_sha256 = sha256(variance_path), result_rows = nrow(results), variance_rows = nrow(variances)),
    quality = list(cells_used_as_replicates = FALSE, biological_samples_are_model_rows = TRUE, subject_random_effect_required = TRUE, all_fixed_designs_full_rank = all(vapply(analyses, function(item) item$fixed_design_rank == length(item$fixed_design_columns), logical(1))), all_outputs_reloaded = TRUE),
    versions = list(R = as.character(getRversion()), variancePartition = package_version_or_absent("variancePartition"), edgeR = package_version_or_absent("edgeR"), limma = package_version_or_absent("limma"), lme4 = package_version_or_absent("lme4"), lmerTest = package_version_or_absent("lmerTest"), BiocParallel = package_version_or_absent("BiocParallel"), jsonlite = package_version_or_absent("jsonlite"), digest = package_version_or_absent("digest"))
  )
  write_json(diagnostics, diagnostics_path, pretty = TRUE, auto_unbox = TRUE, null = "null", na = "string")
}

main()
