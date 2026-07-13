#!/usr/bin/env Rscript

# Project template for biological-replicate single-cell pseudobulk inference.
# Codex must inspect and adapt the design to the actual project before execution.

suppressPackageStartupMessages({
  library(jsonlite)
  library(digest)
})

parse_args <- function(values) {
  if (length(values) == 0 || length(values) %% 2 != 0 || any(substr(values[seq(1, length(values), 2)], 1, 2) != "--")) {
    stop("arguments must be supplied as --name value pairs")
  }
  keys <- sub("^--", "", values[seq(1, length(values), 2)])
  if (anyDuplicated(keys)) stop("arguments must be unique")
  setNames(as.list(values[seq(2, length(values), 2)]), keys)
}

required_arg <- function(args, name) {
  value <- args[[name]]
  if (is.null(value) || !nzchar(value)) stop(sprintf("missing required argument: --%s", name))
  value
}

comma_list <- function(value) {
  if (identical(value, "none")) return(character())
  result <- trimws(strsplit(value, ",", fixed = TRUE)[[1]])
  if (!length(result) || any(!nzchar(result)) || anyDuplicated(result)) stop("covariates must be unique or none")
  result
}

sha256 <- function(path) digest(file = path, algo = "sha256", serialize = FALSE)

package_version_or_absent <- function(name) {
  if (!requireNamespace(name, quietly = TRUE)) return("not-installed")
  as.character(packageVersion(name))
}

validate_numeric <- function(value, name, lower, inclusive = TRUE) {
  parsed <- suppressWarnings(as.numeric(value))
  valid <- length(parsed) == 1 && is.finite(parsed) && if (inclusive) parsed >= lower else parsed > lower
  if (!valid) stop(sprintf("%s is invalid", name))
  parsed
}

standard_result <- function(table, genes, cell_type, engine) {
  table$gene_id <- genes
  table$cell_type <- cell_type
  table$engine <- engine
  table[, c("gene_id", "cell_type", "engine", "log2_fold_change", "standard_error", "mean_expression", "statistic", "p_value", "fdr")]
}

run_edger <- function(counts, metadata, design, coefficient, min_count, min_samples) {
  suppressPackageStartupMessages(library(edgeR))
  y <- DGEList(counts = counts)
  keep <- rowSums(counts >= min_count) >= min_samples & filterByExpr(y, design = design)
  if (sum(keep) < 2) stop("fewer than two genes remain after edgeR expression filtering")
  y <- calcNormFactors(y[keep, , keep.lib.sizes = FALSE])
  y <- estimateDisp(y, design, robust = TRUE)
  fit <- glmQLFit(y, design, robust = TRUE)
  tested <- glmQLFTest(fit, coef = coefficient)
  tab <- topTags(tested, n = Inf, sort.by = "none")$table
  result <- data.frame(
    log2_fold_change = tab$logFC,
    standard_error = NA_real_,
    mean_expression = tab$logCPM,
    statistic = tab$F,
    p_value = tab$PValue,
    fdr = tab$FDR,
    row.names = rownames(tab), check.names = FALSE
  )
  list(result = result, retained_genes = sum(keep), normalization = "TMM", dispersion = "edgeR robust empirical Bayes")
}

run_deseq2 <- function(counts, metadata, formula, condition_column, reference, contrast, min_count, min_samples) {
  suppressPackageStartupMessages(library(DESeq2))
  keep <- rowSums(counts >= min_count) >= min_samples
  if (sum(keep) < 2) stop("fewer than two genes remain after DESeq2 expression filtering")
  dds <- DESeqDataSetFromMatrix(countData = round(counts[keep, , drop = FALSE]), colData = metadata, design = formula)
  dds <- DESeq(dds, quiet = TRUE)
  tested <- results(dds, contrast = c(condition_column, contrast, reference), independentFiltering = FALSE)
  tab <- as.data.frame(tested)
  result <- data.frame(
    log2_fold_change = tab$log2FoldChange,
    standard_error = tab$lfcSE,
    mean_expression = tab$baseMean,
    statistic = tab$stat,
    p_value = tab$pvalue,
    fdr = tab$padj,
    row.names = rownames(tab), check.names = FALSE
  )
  list(result = result, retained_genes = sum(keep), normalization = "DESeq2 median ratio", dispersion = "DESeq2 empirical Bayes")
}

run_limma <- function(counts, metadata, design, coefficient, min_count, min_samples) {
  suppressPackageStartupMessages({library(edgeR); library(limma)})
  y <- DGEList(counts = counts)
  keep <- rowSums(counts >= min_count) >= min_samples & filterByExpr(y, design = design)
  if (sum(keep) < 2) stop("fewer than two genes remain after limma-voom expression filtering")
  y <- calcNormFactors(y[keep, , keep.lib.sizes = FALSE])
  voomed <- voom(y, design, plot = FALSE)
  fit <- eBayes(lmFit(voomed, design), robust = TRUE)
  tab <- topTable(fit, coef = coefficient, number = Inf, sort.by = "none")
  result <- data.frame(
    log2_fold_change = tab$logFC,
    standard_error = if ("t" %in% names(tab)) abs(tab$logFC / tab$t) else NA_real_,
    mean_expression = tab$AveExpr,
    statistic = tab$t,
    p_value = tab$P.Value,
    fdr = tab$adj.P.Val,
    row.names = rownames(tab), check.names = FALSE
  )
  list(result = result, retained_genes = sum(keep), normalization = "TMM plus voom", dispersion = "limma empirical Bayes")
}

sample_diagnostics <- function(counts, metadata) {
  library_sizes <- colSums(counts)
  log_cpm <- log2(t(t(counts + 0.5) / (library_sizes + 1)) * 1e6)
  variable <- apply(log_cpm, 1, var) > 0
  if (sum(variable) >= 2 && ncol(counts) >= 3) {
    pca <- prcomp(t(log_cpm[variable, , drop = FALSE]), center = TRUE, scale. = FALSE)
    dimensions <- min(3, ncol(pca$x))
    distance <- sqrt(rowSums(pca$x[, seq_len(dimensions), drop = FALSE]^2))
    threshold <- median(distance) + 3 * mad(distance, constant = 1)
    outliers <- names(distance)[distance > threshold & distance > median(distance)]
    variance <- (pca$sdev^2) / sum(pca$sdev^2)
    pca_variance <- as.list(round(variance[seq_len(min(5, length(variance)))], 8))
  } else {
    outliers <- character()
    pca_variance <- list()
  }
  list(
    library_sizes = setNames(as.list(as.numeric(library_sizes)), names(library_sizes)),
    library_size_ratio = as.numeric(max(library_sizes) / min(library_sizes)),
    pca_variance_fraction = pca_variance,
    pca_outlier_pseudobulks = unname(outliers),
    biological_samples = unname(as.character(metadata$biological_sample))
  )
}

main <- function() {
  args <- parse_args(commandArgs(trailingOnly = TRUE))
  counts_path <- normalizePath(required_arg(args, "counts"), mustWork = TRUE)
  metadata_path <- normalizePath(required_arg(args, "metadata"), mustWork = TRUE)
  results_path <- required_arg(args, "results")
  diagnostics_path <- required_arg(args, "diagnostics")
  if (file.exists(results_path) || file.exists(diagnostics_path)) stop("refusing to overwrite an output file")
  dir.create(dirname(results_path), recursive = TRUE, showWarnings = FALSE)
  dir.create(dirname(diagnostics_path), recursive = TRUE, showWarnings = FALSE)

  engine <- required_arg(args, "engine")
  if (!engine %in% c("edger", "deseq2", "limma-voom")) stop("engine must be edger, deseq2, or limma-voom")
  reference <- required_arg(args, "reference-level")
  contrast <- required_arg(args, "contrast-level")
  if (identical(reference, contrast)) stop("reference and contrast levels must differ")
  condition_column <- required_arg(args, "condition-column")
  cell_type_column <- required_arg(args, "cell-type-column")
  sample_column <- required_arg(args, "sample-column")
  subject_column <- required_arg(args, "subject-column")
  categorical_covariates <- comma_list(required_arg(args, "categorical-covariates"))
  continuous_covariates <- comma_list(required_arg(args, "continuous-covariates"))
  covariates <- c(categorical_covariates, continuous_covariates)
  if (anyDuplicated(covariates)) stop("categorical and continuous covariates must be disjoint")
  min_replicates <- as.integer(validate_numeric(required_arg(args, "min-replicates-per-group"), "min-replicates-per-group", 2))
  min_count <- validate_numeric(required_arg(args, "min-count"), "min-count", 0)
  min_samples <- as.integer(validate_numeric(required_arg(args, "min-samples-expressed"), "min-samples-expressed", 1))
  fdr_threshold <- validate_numeric(required_arg(args, "fdr-threshold"), "fdr-threshold", 0, inclusive = FALSE)
  if (fdr_threshold >= 1) stop("fdr-threshold must be below one")

  count_table <- read.delim(counts_path, check.names = FALSE, stringsAsFactors = FALSE)
  if (!"gene_id" %in% names(count_table) || anyDuplicated(count_table$gene_id) || any(!nzchar(trimws(count_table$gene_id)))) {
    stop("count matrix requires unique nonempty gene_id values")
  }
  genes <- as.character(count_table$gene_id)
  counts <- as.matrix(count_table[, setdiff(names(count_table), "gene_id"), drop = FALSE])
  storage.mode(counts) <- "numeric"
  rownames(counts) <- genes
  if (!nrow(counts) || ncol(counts) < 2 || any(!is.finite(counts)) || any(counts < 0) || any(abs(counts - round(counts)) > 1e-8)) {
    stop("counts must be a nonempty finite nonnegative integer-like gene-by-pseudobulk matrix")
  }

  metadata <- read.delim(metadata_path, check.names = FALSE, stringsAsFactors = FALSE)
  required <- unique(c("pseudobulk_id", "eligible", sample_column, cell_type_column, condition_column, covariates,
                       if (subject_column == "none") character() else subject_column))
  missing <- setdiff(required, names(metadata))
  if (length(missing)) stop(sprintf("metadata columns are missing: %s", paste(missing, collapse = ", ")))
  if (anyDuplicated(metadata$pseudobulk_id) || any(!nzchar(trimws(metadata$pseudobulk_id)))) stop("pseudobulk identifiers must be unique")
  if (!setequal(colnames(counts), metadata$pseudobulk_id)) stop("count columns and metadata pseudobulk identifiers differ")
  metadata <- metadata[match(colnames(counts), metadata$pseudobulk_id), , drop = FALSE]
  eligible <- tolower(as.character(metadata$eligible)) %in% c("true", "t", "1")
  if (!any(eligible)) stop("no pseudobulk passes the declared aggregation gates")
  if (anyNA(metadata[, setdiff(required, "eligible"), drop = FALSE])) stop("design metadata contains missing values")
  for (field in setdiff(required, "eligible")) {
    metadata[[field]] <- trimws(as.character(metadata[[field]]))
    if (any(!nzchar(metadata[[field]]))) stop(sprintf("design metadata contains empty values: %s", field))
  }
  for (field in continuous_covariates) {
    parsed <- suppressWarnings(as.numeric(metadata[[field]]))
    if (any(!is.finite(parsed))) stop(sprintf("continuous covariate is not entirely finite numeric data: %s", field))
    metadata[[field]] <- parsed
  }
  if (anyDuplicated(c(condition_column, cell_type_column, sample_column, covariates,
                      if (subject_column == "none") character() else subject_column))) stop("design field names must be distinct")

  metadata <- metadata[eligible, , drop = FALSE]
  counts <- counts[, metadata$pseudobulk_id, drop = FALSE]
  cell_types <- sort(unique(metadata[[cell_type_column]]))
  analyses <- list()
  all_results <- list()
  for (cell_type in cell_types) {
    selected <- metadata[[cell_type_column]] == cell_type & metadata[[condition_column]] %in% c(reference, contrast)
    cell_metadata <- droplevels(metadata[selected, , drop = FALSE])
    cell_counts <- counts[, cell_metadata$pseudobulk_id, drop = FALSE]
    if (anyDuplicated(cell_metadata[[sample_column]])) stop(sprintf("cell type %s contains duplicate biological samples", cell_type))
    group_counts <- table(cell_metadata[[condition_column]])
    if (!all(c(reference, contrast) %in% names(group_counts)) || any(group_counts[c(reference, contrast)] < min_replicates)) {
      analyses[[length(analyses) + 1]] <- list(cell_type = cell_type, status = "skipped", reason = "insufficient_biological_replicates", group_counts = as.list(group_counts))
      next
    }
    cell_metadata[[condition_column]] <- factor(cell_metadata[[condition_column]], levels = c(reference, contrast))
    terms <- c(if (subject_column == "none") character() else subject_column, covariates, condition_column)
    factor_terms <- c(if (subject_column == "none") character() else subject_column, categorical_covariates, condition_column)
    for (term in factor_terms) cell_metadata[[term]] <- factor(cell_metadata[[term]])
    for (term in continuous_covariates) {
      if (length(unique(cell_metadata[[term]])) < 2) stop(sprintf("continuous covariate is constant within cell type %s: %s", cell_type, term))
    }
    formula <- reformulate(terms)
    design <- model.matrix(formula, data = cell_metadata)
    if (qr(design)$rank != ncol(design)) stop(sprintf("cell type %s has a rank-deficient or confounded design", cell_type))
    condition_columns <- grep(paste0("^", condition_column), colnames(design))
    if (length(condition_columns) != 1) stop(sprintf("cell type %s does not have one estimable condition coefficient", cell_type))
    coefficient <- condition_columns[[1]]
    rownames(cell_metadata) <- cell_metadata$pseudobulk_id

    diagnostics <- sample_diagnostics(cell_counts, cell_metadata)
    fitted <- switch(
      engine,
      "edger" = run_edger(cell_counts, cell_metadata, design, coefficient, min_count, min_samples),
      "deseq2" = run_deseq2(cell_counts, cell_metadata, formula, condition_column, reference, contrast, min_count, min_samples),
      "limma-voom" = run_limma(cell_counts, cell_metadata, design, coefficient, min_count, min_samples)
    )
    result <- standard_result(fitted$result, rownames(fitted$result), cell_type, engine)
    result$significant <- !is.na(result$fdr) & result$fdr <= fdr_threshold
    all_results[[length(all_results) + 1]] <- result
    subject_summary <- if (subject_column == "none") list(mode = "unpaired", subjects = 0, complete_pairs = 0) else {
      subject_table <- table(cell_metadata[[subject_column]], cell_metadata[[condition_column]])
      list(mode = "subject-fixed-effect", subjects = nrow(subject_table), complete_pairs = sum(rowSums(subject_table > 0) == 2))
    }
    analyses[[length(analyses) + 1]] <- c(list(
      cell_type = cell_type,
      status = "completed",
      samples = nrow(cell_metadata),
      group_counts = as.list(group_counts[c(reference, contrast)]),
      design_formula = paste(deparse(formula), collapse = ""),
      design_columns = unname(colnames(design)),
      design_rank = qr(design)$rank,
      condition_coefficient = colnames(design)[coefficient],
      retained_genes = fitted$retained_genes,
      significant_genes = sum(result$significant),
      normalization = fitted$normalization,
      dispersion = fitted$dispersion,
      subject_design = subject_summary
    ), diagnostics)
  }
  if (!length(all_results)) stop("no cell type had an estimable contrast with sufficient biological replicates")
  combined <- do.call(rbind, all_results)
  combined$global_fdr <- p.adjust(combined$p_value, method = "BH")
  combined <- combined[order(combined$cell_type, combined$p_value, combined$gene_id), , drop = FALSE]
  write.table(combined, results_path, sep = "\t", quote = FALSE, row.names = FALSE, na = "NA")

  report <- list(
    schema_version = 1,
    engine = engine,
    contrast = list(condition_column = condition_column, reference = reference, contrast = contrast),
    design = list(sample_column = sample_column, cell_type_column = cell_type_column, subject_column = subject_column, categorical_covariates = categorical_covariates, continuous_covariates = continuous_covariates),
    thresholds = list(min_replicates_per_group = min_replicates, min_count = min_count, min_samples_expressed = min_samples, fdr = fdr_threshold),
    input = list(counts_filename = basename(counts_path), counts_sha256 = sha256(counts_path), metadata_filename = basename(metadata_path), metadata_sha256 = sha256(metadata_path)),
    analyses = analyses,
    output = list(results_filename = basename(results_path), results_sha256 = sha256(results_path), rows = nrow(combined), completed_cell_types = length(all_results)),
    quality = list(cells_used_as_replicates = FALSE, biological_sample_ids_unique_within_cell_type = TRUE, all_completed_designs_full_rank = TRUE, bh_adjustment_recorded = TRUE, result_reload_pending = TRUE),
    versions = list(R = paste(R.version$major, R.version$minor, sep = "."), edgeR = package_version_or_absent("edgeR"), DESeq2 = package_version_or_absent("DESeq2"), limma = package_version_or_absent("limma"), jsonlite = package_version_or_absent("jsonlite"), digest = package_version_or_absent("digest"))
  )
  write_json(report, diagnostics_path, pretty = TRUE, auto_unbox = TRUE, null = "null", na = "string")

  reloaded <- read.delim(results_path, check.names = FALSE, stringsAsFactors = FALSE)
  expected_columns <- c("gene_id", "cell_type", "engine", "log2_fold_change", "standard_error", "mean_expression", "statistic", "p_value", "fdr", "significant", "global_fdr")
  if (nrow(reloaded) != nrow(combined) || !identical(names(reloaded), expected_columns) || anyDuplicated(reloaded[, c("gene_id", "cell_type")])) {
    stop("differential result reload validation failed")
  }
  report$quality$result_reload_pending <- FALSE
  report$quality$result_reload_validated <- TRUE
  report$output$diagnostics_filename <- basename(diagnostics_path)
  write_json(report, diagnostics_path, pretty = TRUE, auto_unbox = TRUE, null = "null", na = "string")
  cat(toJSON(list(engine = engine, rows = nrow(combined), cell_types = length(all_results)), auto_unbox = TRUE), "\n")
}

main()
