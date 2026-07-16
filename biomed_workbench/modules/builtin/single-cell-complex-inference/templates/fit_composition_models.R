#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(BiocParallel)
  library(digest)
  library(jsonlite)
  library(lme4)
  library(limma)
  library(speckle)
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

comma_list <- function(value) {
  items <- trimws(strsplit(value, ",", fixed = TRUE)[[1]])
  if (!length(items) || any(!nzchar(items)) || anyDuplicated(items)) stop("reference-cell-types must be a unique comma-separated list", call. = FALSE)
  items
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
  unknown <- setdiff(all.names(formula, functions = TRUE, unique = TRUE), c(metadata_names, allowed_calls))
  if (length(unknown)) stop("model formula contains unsupported names: ", paste(unknown, collapse = ", "), call. = FALSE)
  random_variables <- unique(unlist(lapply(lme4::findbars(formula), function(term) all.vars(term[[3]]))))
  if (!length(random_variables) || !"subject" %in% random_variables) stop("composition formula must include a subject random effect", call. = FALSE)
  formula
}

standard_table <- function(table, cell_types, model, coefficient, reference = NA_character_) {
  column <- function(name, fallback = NA_real_) if (name %in% names(table)) table[[name]] else rep(fallback, nrow(table))
  data.frame(
    cell_type = cell_types, model = model, reference_cell_type = reference, coefficient = coefficient,
    transformed_effect = column("logFC"), statistic = if ("t" %in% names(table)) table$t else column("F"),
    statistic_kind = if ("t" %in% names(table)) "t" else "F", p_value = column("P.Value"), fdr = column("adj.P.Val"),
    z_standardized = column("z.std"), stringsAsFactors = FALSE, check.names = FALSE
  )
}

main <- function() {
  args <- parse_args(commandArgs(trailingOnly = TRUE))
  composition_path <- normalizePath(required_arg(args, "composition"), mustWork = TRUE)
  results_path <- required_arg(args, "results")
  alr_path <- required_arg(args, "alr-results")
  diagnostics_path <- required_arg(args, "diagnostics")
  if (any(file.exists(c(results_path, alr_path, diagnostics_path)))) stop("refusing to overwrite declared outputs", call. = FALSE)
  lapply(c(results_path, alr_path, diagnostics_path), function(path) dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE))

  formula_text <- required_arg(args, "formula")
  coefficient_pattern <- required_arg(args, "coefficient-pattern")
  ddf <- required_arg(args, "ddf")
  if (!ddf %in% c("adaptive", "Satterthwaite", "Kenward-Roger")) stop("unsupported dream degrees-of-freedom method", call. = FALSE)
  reference_types <- comma_list(required_arg(args, "reference-cell-types"))
  min_total_cells <- numeric_arg(args, "min-total-cells", 1, integer = TRUE)
  min_samples <- numeric_arg(args, "min-samples", 4, integer = TRUE)
  min_subjects <- numeric_arg(args, "min-subjects", 2, integer = TRUE)
  min_repeated_subjects <- numeric_arg(args, "min-repeated-subjects", 2, integer = TRUE)
  min_reference_support <- numeric_arg(args, "min-reference-support", 1, integer = TRUE)
  fdr_threshold <- numeric_arg(args, "fdr-threshold", .Machine$double.eps, 1 - .Machine$double.eps)

  data <- read.delim(composition_path, check.names = FALSE, stringsAsFactors = FALSE)
  required <- c("biological_sample", "subject", "condition", "time", "cell_type", "cell_count", "total_cells", "proportion")
  missing <- setdiff(required, names(data))
  if (length(missing)) stop("composition input is missing: ", paste(missing, collapse = ", "), call. = FALSE)
  if (any(is.na(data[, required])) || any(!is.finite(data$cell_count)) || any(!is.finite(data$total_cells)) || any(data$cell_count < 0) || any(data$total_cells < 1) || any(abs(data$cell_count - round(data$cell_count)) > 1e-8) || any(data$cell_count > data$total_cells)) stop("composition counts or metadata are invalid", call. = FALSE)
  key <- paste(data$biological_sample, data$cell_type, sep = "\r")
  if (anyDuplicated(key)) stop("composition input contains duplicate sample-cell-type rows", call. = FALSE)
  samples <- sort(unique(data$biological_sample))
  cell_types <- sort(unique(data$cell_type))
  if (length(samples) < min_samples || length(cell_types) < 3 || !all(reference_types %in% cell_types) || length(reference_types) < 2) stop("composition design lacks samples, cell types, or declared references", call. = FALSE)
  if (nrow(data) != length(samples) * length(cell_types)) stop("composition input is not a complete sample-by-cell-type grid", call. = FALSE)

  sample_fields <- setdiff(names(data), c("cell_type", "cell_count", "proportion"))
  inconsistent <- lapply(sample_fields, function(field) {
    samples_with_conflict <- names(which(tapply(data[[field]], data$biological_sample, function(x) length(unique(x))) != 1))
    if (!length(samples_with_conflict)) return(NULL)
    data.frame(field = rep(field, length(samples_with_conflict)), sample = samples_with_conflict, stringsAsFactors = FALSE)
  })
  inconsistent <- do.call(rbind, Filter(Negate(is.null), inconsistent))
  if (is.null(inconsistent)) inconsistent <- data.frame(field = character(), sample = character())
  if (nrow(inconsistent)) stop("sample metadata is inconsistent across composition rows", call. = FALSE)
  sample_metadata <- data[match(samples, data$biological_sample), sample_fields, drop = FALSE]
  rownames(sample_metadata) <- sample_metadata$biological_sample
  sample_metadata$subject <- factor(sample_metadata$subject)
  sample_metadata$condition <- factor(sample_metadata$condition)
  for (name in names(sample_metadata)) if (is.character(sample_metadata[[name]]) && !name %in% "biological_sample") sample_metadata[[name]] <- factor(sample_metadata[[name]])
  if (any(!is.finite(sample_metadata$time))) stop("time must be numeric and finite", call. = FALSE)
  subject_table <- table(sample_metadata$subject)
  if (length(subject_table) < min_subjects || sum(subject_table >= 2) < min_repeated_subjects) stop("composition design lacks required subjects or repeated measurements", call. = FALSE)

  count_matrix <- xtabs(cell_count ~ cell_type + biological_sample, data = data)
  count_matrix <- count_matrix[cell_types, samples, drop = FALSE]
  total_by_sample <- tapply(data$total_cells, data$biological_sample, unique)
  total_by_sample <- as.numeric(total_by_sample[samples])
  if (any(colSums(count_matrix) != total_by_sample)) stop("composition counts do not sum to declared sample totals", call. = FALSE)
  retained_samples <- total_by_sample >= min_total_cells
  if (sum(retained_samples) < min_samples) stop("too few samples pass minimum total-cell threshold", call. = FALSE)
  count_matrix <- count_matrix[, retained_samples, drop = FALSE]
  sample_metadata <- droplevels(sample_metadata[retained_samples, , drop = FALSE])
  total_by_sample <- total_by_sample[retained_samples]

  proportions <- sweep(count_matrix, 2, colSums(count_matrix), "/")
  pseudocount_proportions <- sweep(count_matrix + 0.5, 2, colSums(count_matrix + 0.5), "/")
  transformed <- log(pseudocount_proportions / (1 - pseudocount_proportions))
  propeller_input <- list(Counts = count_matrix, Proportions = proportions, TransformedProps = transformed)
  formula <- validate_formula(formula_text, names(sample_metadata))
  fixed_formula <- lme4::nobars(formula)
  fixed_design <- model.matrix(fixed_formula, data = sample_metadata)
  if (qr(fixed_design)$rank != ncol(fixed_design)) stop("composition fixed-effect design is rank deficient", call. = FALSE)
  parameter <- BiocParallel::SerialParam(progressbar = FALSE)

  dream_fit <- variancePartition::dream(transformed, formula, sample_metadata, ddf = ddf, useWeights = FALSE, BPPARAM = parameter)
  dream_fit <- variancePartition::eBayes(dream_fit)
  available <- colnames(dream_fit$coefficients)
  coefficients <- grep(coefficient_pattern, available, value = TRUE, perl = TRUE)
  if (!length(coefficients)) stop("coefficient pattern matched no composition coefficients; available: ", paste(available, collapse = ", "), call. = FALSE)
  primary <- list()
  for (coefficient in coefficients) {
    table <- variancePartition::topTable(dream_fit, coef = coefficient, number = Inf, sort.by = "none")
    primary[[length(primary) + 1]] <- standard_table(table, rownames(table), "dream-logit-proportion", coefficient)
  }
  if (length(coefficients) > 1) {
    table <- variancePartition::topTable(dream_fit, coef = coefficients, number = Inf, sort.by = "none")
    primary[[length(primary) + 1]] <- standard_table(table, rownames(table), "dream-logit-joint", paste(coefficients, collapse = ";"))
  }

  matched_columns <- match(coefficients, colnames(fixed_design))
  if (any(is.na(matched_columns))) stop("dream and fixed-effect coefficient names do not reconcile", call. = FALSE)
  intercept_column <- match("(Intercept)", colnames(fixed_design))
  if (is.na(intercept_column)) stop("propeller fixed-effect sensitivity requires an explicit intercept", call. = FALSE)
  fixed_result <- speckle::propeller.anova(propeller_input, fixed_design, c(intercept_column, matched_columns), robust = TRUE, trend = FALSE, sort = FALSE)
  fixed_table <- data.frame(cell_type = rownames(fixed_result), model = "propeller-fixed-joint-sensitivity", reference_cell_type = NA_character_, coefficient = paste(coefficients, collapse = ";"), transformed_effect = NA_real_, statistic = fixed_result$Fstatistic, statistic_kind = "F", p_value = fixed_result$P.Value, fdr = fixed_result$FDR, z_standardized = NA_real_, stringsAsFactors = FALSE)
  results <- rbind(do.call(rbind, primary), fixed_table)
  results$mean_proportion <- rowMeans(proportions[results$cell_type, , drop = FALSE])
  results$global_fdr <- p.adjust(results$p_value, method = "BH")
  results <- results[order(results$model, results$p_value, results$cell_type), , drop = FALSE]

  alr_results <- list()
  for (reference in reference_types) {
    targets <- setdiff(cell_types, reference)
    alr <- log((count_matrix[targets, , drop = FALSE] + 0.5) / rep(count_matrix[reference, ] + 0.5, each = length(targets)))
    rownames(alr) <- targets
    fit <- variancePartition::dream(alr, formula, sample_metadata, ddf = ddf, useWeights = FALSE, BPPARAM = parameter)
    fit <- variancePartition::eBayes(fit)
    fit_coefficients <- grep(coefficient_pattern, colnames(fit$coefficients), value = TRUE, perl = TRUE)
    if (!identical(fit_coefficients, coefficients)) stop("ALR and primary coefficient sets differ", call. = FALSE)
    for (coefficient in coefficients) {
      table <- variancePartition::topTable(fit, coef = coefficient, number = Inf, sort.by = "none")
      alr_results[[length(alr_results) + 1]] <- standard_table(table, rownames(table), "dream-additive-log-ratio", coefficient, reference)
    }
  }
  alr_results <- do.call(rbind, alr_results)
  alr_results$global_fdr <- p.adjust(alr_results$p_value, method = "BH")
  alr_results <- alr_results[order(alr_results$coefficient, alr_results$cell_type, alr_results$reference_cell_type), , drop = FALSE]

  support_rows <- list()
  for (coefficient in coefficients) {
    for (cell_type in cell_types) {
      subset <- alr_results[alr_results$coefficient == coefficient & alr_results$cell_type == cell_type, , drop = FALSE]
      if (!nrow(subset)) next
      positive <- sum(subset$transformed_effect > 0)
      negative <- sum(subset$transformed_effect < 0)
      direction <- if (positive == nrow(subset)) "positive" else if (negative == nrow(subset)) "negative" else "discordant"
      support_rows[[length(support_rows) + 1]] <- data.frame(
        cell_type = cell_type, coefficient = coefficient, references_tested = nrow(subset), direction = direction,
        median_alr_effect = median(subset$transformed_effect), significant_references = sum(subset$fdr <= fdr_threshold, na.rm = TRUE),
        admitted_reference_stable = direction != "discordant" && nrow(subset) >= min_reference_support,
        stringsAsFactors = FALSE
      )
    }
  }
  reference_support <- do.call(rbind, support_rows)

  write.table(results, results_path, sep = "\t", quote = FALSE, row.names = FALSE, na = "NA")
  write.table(alr_results, alr_path, sep = "\t", quote = FALSE, row.names = FALSE, na = "NA")
  reloaded <- read.delim(results_path, check.names = FALSE, stringsAsFactors = FALSE)
  reloaded_alr <- read.delim(alr_path, check.names = FALSE, stringsAsFactors = FALSE)
  if (nrow(reloaded) != nrow(results) || nrow(reloaded_alr) != nrow(alr_results) || any(!is.finite(reloaded$p_value)) || any(!is.finite(reloaded_alr$p_value))) stop("composition outputs failed reload validation", call. = FALSE)

  diagnostics <- list(
    schema_version = 1, engines = c("speckle-propeller", "variancePartition-dream", "additive-log-ratio-sensitivity"),
    formula = formula_text, coefficient_pattern = coefficient_pattern, tested_coefficients = coefficients, degrees_of_freedom_method = ddf,
    thresholds = list(min_total_cells = min_total_cells, min_samples = min_samples, min_subjects = min_subjects, min_repeated_subjects = min_repeated_subjects, min_reference_support = min_reference_support, fdr = fdr_threshold),
    input = list(composition_filename = basename(composition_path), composition_sha256 = sha256(composition_path), samples = ncol(count_matrix), subjects = length(unique(sample_metadata$subject)), cell_types = nrow(count_matrix), reference_cell_types = reference_types),
    design = list(fixed_design_columns = colnames(fixed_design), fixed_design_rank = qr(fixed_design)$rank, repeated_subjects = sum(table(sample_metadata$subject) >= 2)),
    reference_stability = split(reference_support, seq_len(nrow(reference_support))),
    output = list(results_filename = basename(results_path), results_sha256 = sha256(results_path), alr_filename = basename(alr_path), alr_sha256 = sha256(alr_path), result_rows = nrow(results), alr_rows = nrow(alr_results)),
    quality = list(cells_used_as_replicates = FALSE, biological_samples_are_model_rows = TRUE, subject_random_effect_required = TRUE, complete_composition_grid = TRUE, closure_checked = all(abs(colSums(proportions) - 1) < 1e-8), fixed_only_propeller_is_sensitivity = TRUE, alr_reference_sensitivity_completed = TRUE, outputs_reloaded = TRUE),
    versions = list(R = as.character(getRversion()), speckle = package_version_or_absent("speckle"), variancePartition = package_version_or_absent("variancePartition"), limma = package_version_or_absent("limma"), lme4 = package_version_or_absent("lme4"), lmerTest = package_version_or_absent("lmerTest"), BiocParallel = package_version_or_absent("BiocParallel"), jsonlite = package_version_or_absent("jsonlite"), digest = package_version_or_absent("digest"))
  )
  write_json(diagnostics, diagnostics_path, pretty = TRUE, auto_unbox = TRUE, null = "null", na = "string")
}

main()
