#!/usr/bin/env Rscript
# DEqMS workflow following the installed package vignette: limma fit,
# coefficient-bound spectraCounteBayes, outputResult, and official diagnostics.

suppressPackageStartupMessages({
  library(DEqMS)
  library(limma)
  library(jsonlite)
  library(digest)
})

parse_args <- function(x) {
  if (length(x) %% 2 != 0 || any(!startsWith(x[seq(1, length(x), 2)], "--"))) stop("arguments must be --key value pairs")
  structure(as.list(x[seq(2, length(x), 2)]), names = sub("^--", "", x[seq(1, length(x), 2)]))
}

args <- parse_args(commandArgs(trailingOnly = TRUE))
required <- c("abundance", "support-counts", "design", "formula", "output-dir")
if (!all(required %in% names(args))) stop(paste("missing arguments:", paste(setdiff(required, names(args)), collapse = ", ")))
if (!("contrast" %in% names(args)) && !("coefficient" %in% names(args))) stop("supply --contrast or a simple --coefficient")
inputs <- unlist(args[c("abundance", "support-counts", "design")])
if (any(!file.exists(inputs))) stop("one or more input files are missing")
if (dir.exists(args$`output-dir`) && length(list.files(args$`output-dir`, all.files = TRUE, no.. = TRUE))) stop("output directory is not empty")
dir.create(args$`output-dir`, recursive = TRUE, showWarnings = FALSE)

abundance <- read.delim(args$abundance, check.names = FALSE, stringsAsFactors = FALSE)
support <- read.delim(args$`support-counts`, check.names = FALSE, stringsAsFactors = FALSE)
design <- read.delim(args$design, check.names = FALSE, stringsAsFactors = FALSE)
if (!identical(names(abundance)[1], "protein_id") || !identical(names(support), c("protein_id", "count")) ||
    !("sample_id" %in% names(design))) stop("required columns are protein_id; protein_id/count; and sample_id")
if (anyDuplicated(abundance$protein_id) || anyDuplicated(support$protein_id) || anyDuplicated(design$sample_id)) stop("identifiers must be unique")
sample_ids <- names(abundance)[-1]
if (!identical(sample_ids, design$sample_id)) stop("abundance columns must exactly match ordered design sample_id")
if (!setequal(abundance$protein_id, support$protein_id)) stop("support counts must contain exactly the abundance proteins")
support <- support[match(abundance$protein_id, support$protein_id), ]

matrix <- as.matrix(abundance[, -1, drop = FALSE])
storage.mode(matrix) <- "double"
rownames(matrix) <- abundance$protein_id
if (any(is.infinite(matrix)) || any(!is.finite(support$count)) || any(support$count < 1) ||
    any(abs(support$count - round(support$count)) > 1e-8)) stop("abundance may contain NA but not infinity; support count must be positive integer-like")
if (any(rowSums(is.finite(matrix)) < 3)) stop("each retained protein requires at least three finite sample values")

factor_columns <- if ("factor-columns" %in% names(args) && nzchar(args$`factor-columns`)) strsplit(args$`factor-columns`, ",", fixed = TRUE)[[1]] else character()
if (any(!factor_columns %in% names(design))) stop("factor-columns contains an unknown design field")
for (field in factor_columns) design[[field]] <- factor(design[[field]])
formula <- as.formula(args$formula)
model <- model.matrix(formula, data = design)
if (qr(model)$rank != ncol(model)) stop("design matrix is rank deficient")
contrast_expression <- if ("contrast" %in% names(args)) args$contrast else args$coefficient
if (!("contrast" %in% names(args)) && !(contrast_expression %in% colnames(model))) {
  stop(paste("coefficient is not in design matrix:", paste(colnames(model), collapse = ", ")))
}
coefficient_index <- if (contrast_expression %in% colnames(model)) match(contrast_expression, colnames(model)) else NA_integer_
if (nrow(model) - qr(model)$rank < 1) stop("design has no residual degrees of freedom")

fit <- lmFit(matrix, model)
contrast_vector <- makeContrasts(contrasts = contrast_expression, levels = model)
fit <- contrasts.fit(fit, contrast_vector)
fit <- eBayes(fit)
fit$count <- as.numeric(support$count)
fit <- spectraCounteBayes(fit, coef_col = 1)
result <- outputResult(fit, coef_col = 1)
result$protein_id <- rownames(result)
result <- result[, c("protein_id", setdiff(names(result), "protein_id")), drop = FALSE]
result_path <- file.path(args$`output-dir`, "deqms_results.tsv")
write.table(result, result_path, sep = "\t", quote = FALSE, row.names = FALSE)

write_plot <- function(stem, draw) {
  for (extension in c("pdf", "svg")) {
    path <- file.path(args$`output-dir`, paste0(stem, ".", extension))
    if (extension == "pdf") pdf(path, width = 7.2047, height = 3.5, family = "Helvetica", pointsize = 7, useDingbats = FALSE)
    else svg(path, width = 7.2047, height = 3.5, family = "Arial", pointsize = 7)
    par(mar = c(3.2, 3.2, 0.8, 0.8), mgp = c(1.8, 0.45, 0), tcl = -0.2, lwd = 0.5, cex = 0.8)
    draw()
    dev.off()
  }
}
write_plot("variance_count_trend", function() VarianceScatterplot(fit))
write_plot("variance_count_boxplot", function() VarianceBoxplot(fit))
write_plot("residual_diagnostic", function() Residualplot(fit))
write_plot("volcano", function() volcanoplot(fit, coef = 1))
write_plot("missingness_and_intensity_qc", function() {
  par(mfrow = c(1, 2))
  boxplot(matrix, outline = FALSE, las = 2, ylab = "Normalized abundance", names = sample_ids)
  barplot(colMeans(!is.finite(matrix)), names.arg = sample_ids, las = 2, ylab = "Missing fraction", ylim = c(0, 1))
})
write_plot("sample_correlation_heatmap", function() {
  correlation <- cor(matrix, use = "pairwise.complete.obs")
  heatmap(correlation, symm = TRUE, scale = "none", col = colorRampPalette(c("#3B4CC0", "#F7F7F7", "#B40426"))(50),
    margins = c(5, 5), xlab = "Sample", ylab = "Sample")
})
plot_matrix <- matrix
for (i in seq_len(nrow(plot_matrix))) plot_matrix[i, !is.finite(plot_matrix[i, ])] <- median(plot_matrix[i, ], na.rm = TRUE)
pca <- prcomp(t(plot_matrix), center = TRUE, scale. = TRUE)
write_plot("pca", function() {
  group <- if (length(factor_columns)) as.integer(design[[factor_columns[1]]]) else rep(1L, nrow(design))
  palette <- c("#0072B2", "#E69F00", "#009E73", "#CC79A7", "#D55E00")
  plot(pca$x[, 1], pca$x[, 2], pch = 16, col = palette[(group - 1L) %% length(palette) + 1L],
    xlab = sprintf("PC1 (%.1f%%)", 100 * summary(pca)$importance[2, 1]),
    ylab = sprintf("PC2 (%.1f%%)", 100 * summary(pca)$importance[2, 2]))
  text(pca$x[, 1], pca$x[, 2], labels = sample_ids, pos = 3, cex = 0.65)
})
write_plot("psm_count_distribution", function() {
  hist(support$count, breaks = "FD", col = "#56B4E9", border = "white", xlab = "Protein support count", main = "")
})
write_plot("ma", function() {
  significant <- result$sca.adj.pval < 0.05
  plot(result$AveExpr, result$logFC, pch = 16, cex = 0.45, col = ifelse(significant, "#D55E00", "#B0B0B0"),
    xlab = "Mean normalized abundance", ylab = "Contrast effect")
  abline(h = 0, lty = 2, col = "black")
})
write_plot("significant_protein_heatmap", function() {
  selected <- head(order(result$sca.adj.pval, -abs(result$logFC), na.last = NA), 50)
  selected_ids <- result$protein_id[selected]
  z <- t(scale(t(plot_matrix[selected_ids, , drop = FALSE])))
  z[!is.finite(z)] <- 0
  heatmap(z, scale = "none", col = colorRampPalette(c("#3B4CC0", "#F7F7F7", "#B40426"))(50),
    margins = c(5, 4), labRow = if (nrow(z) <= 30) rownames(z) else NA, xlab = "Sample", ylab = "Protein")
})

reload <- read.delim(result_path, check.names = FALSE, stringsAsFactors = FALSE)
p_candidates <- intersect(c("sca.P.Value", "P.Value", "sca.adj.pval", "adj.P.Val"), names(reload))
if (nrow(reload) != nrow(matrix) || !setequal(reload$protein_id, rownames(matrix)) || anyDuplicated(reload$protein_id) || !length(p_candidates)) stop("DEqMS result failed reload")
for (field in p_candidates) if (any(!is.na(reload[[field]]) & (reload[[field]] < 0 | reload[[field]] > 1))) stop("p-value field is out of bounds")

file_sha <- function(path) digest(file = path, algo = "sha256", serialize = FALSE)
report <- list(
  schema_version = 1,
  passed = TRUE,
  method = "limma plus DEqMS spectraCounteBayes",
  formula = args$formula,
  contrast = contrast_expression,
  coefficient_index = coefficient_index,
  factor_columns = factor_columns,
  proteins = nrow(matrix),
  samples = ncol(matrix),
  residual_degrees_of_freedom = nrow(model) - qr(model)$rank,
  support_count_semantics = "precomputed positive peptide-or-PSM support declared by the upstream quantification workflow",
  inputs = setNames(lapply(inputs, file_sha), names(inputs)),
  output_sha256 = file_sha(result_path),
  figures = c("missingness_and_intensity_qc", "sample_correlation_heatmap", "pca", "psm_count_distribution",
    "variance_count_trend", "variance_count_boxplot", "residual_diagnostic", "ma", "volcano", "significant_protein_heatmap"),
  versions = list(R = as.character(getRversion()), DEqMS = as.character(packageVersion("DEqMS")), limma = as.character(packageVersion("limma"))),
  plot_standard_version = "1.1.0",
  quality_gates = list(
    ordered_sample_identity = TRUE,
    full_rank_design = TRUE,
    coefficient_bound_to_both_deqms_steps = TRUE,
    positive_integer_support = TRUE,
    result_reloaded = TRUE
  ),
  limitations = c(
    "The support-count vector must be constructed upstream according to the quantification design; this script does not guess peptide or PSM semantics.",
    "Missingness, normalization, and imputation choices are upstream scientific decisions and must be recorded with the abundance artifact."
  )
)
write(toJSON(report, auto_unbox = TRUE, pretty = TRUE, digits = NA), file.path(args$`output-dir`, "deqms_report.json"))
cat(toJSON(list(passed = TRUE, proteins = nrow(matrix), contrast = contrast_expression), auto_unbox = TRUE), "\n")
