#!/usr/bin/env Rscript

# Official SecAct adapter. It calls the package API and never substitutes a
# custom response score for SecAct activity or communication inference.
suppressPackageStartupMessages({
  library(jsonlite)
  library(SecAct)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 3L) stop("expected: configuration.json input-seurat.rds new-output-directory")
config_path <- normalizePath(args[[1L]], mustWork = TRUE)
input_path <- normalizePath(args[[2L]], mustWork = TRUE)
output_directory <- normalizePath(args[[3L]], mustWork = FALSE)
if (file.exists(output_directory)) stop("refusing to overwrite an existing SecAct output directory")
dir.create(output_directory, recursive = TRUE, showWarnings = FALSE)
config <- fromJSON(config_path, simplifyVector = TRUE)

required <- c("analysis", "cell_type_key", "sample_key", "condition_key", "minimum_cells", "nrand", "seed")
missing <- setdiff(required, names(config))
if (length(missing)) stop(paste("configuration omits:", paste(missing, collapse = ", ")))
if (!config$analysis %in% c("sample-celltype-activity", "pooled-condition-communication-descriptive")) {
  stop("analysis must be sample-celltype-activity or pooled-condition-communication-descriptive")
}
if (config$minimum_cells < 20L || config$nrand < 100L) stop("minimum_cells must be >=20 and nrand >=100")
set.seed(as.integer(config$seed))
object <- readRDS(input_path)
if (!inherits(object, "Seurat")) stop("the official single-cell SecAct API requires a Seurat object")
meta <- object@meta.data
for (field in c(config$cell_type_key, config$sample_key, config$condition_key)) {
  if (!field %in% colnames(meta)) stop(paste("Seurat metadata lacks", field))
  if (anyNA(meta[[field]]) || any(trimws(as.character(meta[[field]])) == "")) stop(paste("metadata is incomplete:", field))
}
sample_condition_count <- tapply(meta[[config$condition_key]], meta[[config$sample_key]], function(x) length(unique(x)))
if (any(sample_condition_count != 1L)) stop("each biological sample must map to exactly one condition")

write_matrix <- function(matrix, name) {
  table <- data.frame(secreted_protein = rownames(matrix), as.data.frame(matrix, check.names = FALSE), check.names = FALSE)
  write.table(table, file.path(output_directory, name), sep = "\t", quote = FALSE, row.names = FALSE)
}

plot_both <- function(stem, expression) {
  pdf(file.path(output_directory, paste0(stem, ".pdf")), width = 7, height = 5, useDingbats = FALSE)
  print(eval(expression))
  dev.off()
  png(file.path(output_directory, paste0(stem, ".png")), width = 2100, height = 1500, res = 300)
  print(eval(expression))
  dev.off()
}

sample_rows <- list()
if (config$analysis == "sample-celltype-activity") {
  samples <- sort(unique(as.character(meta[[config$sample_key]])))
  for (sample_id in samples) {
    cells <- rownames(meta)[as.character(meta[[config$sample_key]]) == sample_id]
    sample_object <- subset(object, cells = cells)
    sizes <- table(sample_object@meta.data[[config$cell_type_key]])
    eligible <- names(sizes[sizes >= config$minimum_cells])
    if (length(eligible) < 2L) {
      sample_rows[[length(sample_rows) + 1L]] <- data.frame(sample = sample_id, status = "blocked", reason = "fewer than two eligible cell types")
      next
    }
    eligible_cells <- rownames(sample_object@meta.data)[sample_object@meta.data[[config$cell_type_key]] %in% eligible]
    sample_object <- subset(sample_object, cells = eligible_cells)
    sample_object <- SecAct.activity.inference.scRNAseq(
      sample_object,
      cellType_meta = config$cell_type_key,
      is.singleCellLevel = FALSE,
      sigMatrix = ifelse(is.null(config$sig_matrix), "SecAct", config$sig_matrix),
      is.filter.sig = isTRUE(config$filter_signatures),
      is.group.sig = !identical(config$group_signatures, FALSE),
      is.group.cor = ifelse(is.null(config$group_correlation), 0.9, config$group_correlation),
      lambda = ifelse(is.null(config$lambda), 5e5, config$lambda),
      nrand = config$nrand,
      ncores = ifelse(is.null(config$ncores), 1L, config$ncores),
      backend = ifelse(is.null(config$backend), "auto", config$backend),
      rng_method = "mt19937"
    )
    result <- sample_object@misc$SecAct_output$SecretedProteinActivity
    for (metric in c("beta", "se", "zscore", "pvalue")) {
      write_matrix(result[[metric]], paste0("secact_", sample_id, "_", metric, ".tsv"))
    }
    top <- unique(unlist(lapply(seq_len(ncol(result$zscore)), function(i) rownames(result$zscore)[order(result$zscore[, i], decreasing = TRUE)[seq_len(min(10L, nrow(result$zscore)))]])))
    fg <- result$zscore[top, , drop = FALSE]
    plot_both(paste0("secact_", sample_id, "_activity_heatmap"), quote(SecAct.heatmap.plot(fg, title = sample_id)))
    sample_rows[[length(sample_rows) + 1L]] <- data.frame(sample = sample_id, status = "observed", reason = "")
  }
  if (!any(vapply(sample_rows, function(x) x$status[[1L]] == "observed", logical(1)))) stop("no sample produced SecAct activity")
} else {
  if (!isTRUE(config$allow_pooled_descriptive)) {
    stop("pooled SecAct communication is descriptive and requires allow_pooled_descriptive=true")
  }
  for (field in c("case", "control")) if (is.null(config[[field]])) stop(paste("pooled communication requires", field))
  object <- SecAct.CCC.scRNAseq(
    object,
    cellType_meta = config$cell_type_key,
    condition_meta = config$condition_key,
    conditionCase = config$case,
    conditionControl = config$control,
    act_diff_cutoff = ifelse(is.null(config$activity_z_cutoff), 2, config$activity_z_cutoff),
    exp_logFC_cutoff = ifelse(is.null(config$expression_logfc_cutoff), 0.2, config$expression_logfc_cutoff),
    exp_fraction_case_cutoff = ifelse(is.null(config$expression_fraction_cutoff), 0.1, config$expression_fraction_cutoff),
    padj_cutoff = ifelse(is.null(config$adjusted_p_cutoff), 0.01, config$adjusted_p_cutoff),
    sigMatrix = ifelse(is.null(config$sig_matrix), "SecAct", config$sig_matrix),
    nrand = config$nrand
  )
  result <- object@misc$SecAct_output$SecretedProteinCCC
  write.table(result, file.path(output_directory, "secact_pooled_condition_communication_descriptive.tsv"), sep = "\t", quote = FALSE, row.names = FALSE)
  colours <- setNames(grDevices::hcl.colors(length(unique(meta[[config$cell_type_key]])), "Dark 3"), sort(unique(meta[[config$cell_type_key]])))
  plot_both("secact_pooled_communication_heatmap_descriptive", quote(SecAct.CCC.heatmap(object, row.sorted = TRUE, column.sorted = TRUE, colors_cellType = colours)))
  plot_both("secact_pooled_communication_circle_descriptive", quote(SecAct.CCC.circle(object, colors_cellType = colours)))
  sample_rows[[1L]] <- data.frame(sample = "condition-pooled", status = "descriptive-only", reason = "cells, not biological samples, define the official internal test")
}

runs <- do.call(rbind, sample_rows)
write.table(runs, file.path(output_directory, "secact_run_accounting.tsv"), sep = "\t", quote = FALSE, row.names = FALSE)
saveRDS(object, file.path(output_directory, "secact_result_object.rds"))
report <- list(
  schema_version = 1L,
  method = "SecAct official R API",
  analysis = config$analysis,
  biological_samples = length(unique(meta[[config$sample_key]])),
  conditions = sort(unique(as.character(meta[[config$condition_key]]))),
  scientific_scope = if (config$analysis == "sample-celltype-activity") "relative secreted-protein activity within each biological sample" else "condition-pooled descriptive communication only",
  condition_level_inference_allowed = FALSE,
  package_versions = list(R = paste(R.version$major, R.version$minor, sep = "."), SecAct = as.character(packageVersion("SecAct"))),
  parameters = config,
  limitations = c("SecAct activity is a model-derived relative activity estimate, not measured protein secretion or receptor activation.", "The official pooled condition communication workflow does not establish biological-sample-level differential communication."),
  outputs_reloaded = FALSE
)
write_json(report, file.path(output_directory, "secact_report.json"), auto_unbox = TRUE, pretty = TRUE, null = "null")
report2 <- fromJSON(file.path(output_directory, "secact_report.json"), simplifyVector = FALSE)
if (!identical(report2$schema_version, 1L)) stop("SecAct report reload failed")
report$outputs_reloaded <- TRUE
write_json(report, file.path(output_directory, "secact_report.json"), auto_unbox = TRUE, pretty = TRUE, null = "null")
