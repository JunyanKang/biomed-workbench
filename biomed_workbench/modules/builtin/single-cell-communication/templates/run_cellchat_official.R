#!/usr/bin/env Rscript

# CellChat 2.2 adapter following the official per-object and comparison APIs.
suppressPackageStartupMessages({
  library(CellChat)
  library(jsonlite)
  library(Matrix)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2L) stop("expected configuration JSON and new output directory")
config <- fromJSON(normalizePath(args[[1L]], mustWork = TRUE), simplifyVector = TRUE)
output_directory <- normalizePath(args[[2L]], mustWork = FALSE)
if (file.exists(output_directory)) stop("refusing to overwrite an existing CellChat output directory")
dir.create(output_directory, recursive = TRUE, showWarnings = FALSE)
required <- c("input_kind", "cell_type_key", "sample_key", "condition_key", "species", "minimum_cells", "permutations", "seed")
missing <- setdiff(required, names(config))
if (length(missing)) stop(paste("configuration omits:", paste(missing, collapse = ", ")))
if (!config$input_kind %in% c("matrix-market", "seurat-rds", "singlecellexperiment-rds")) stop("unsupported input_kind")
if (!config$species %in% c("human", "mouse")) stop("species must be human or mouse")
if (config$minimum_cells < 3L || config$permutations < 100L) stop("minimum_cells must be >=3 and permutations >=100")

load_input <- function() {
  if (config$input_kind == "matrix-market") {
    for (field in c("matrix", "genes", "cells", "metadata")) if (is.null(config[[field]])) stop(paste("matrix-market input requires", field))
    counts <- readMM(normalizePath(config$matrix, mustWork = TRUE))
    genes <- readLines(normalizePath(config$genes, mustWork = TRUE), warn = FALSE)
    cells <- readLines(normalizePath(config$cells, mustWork = TRUE), warn = FALSE)
    meta <- read.delim(normalizePath(config$metadata, mustWork = TRUE), stringsAsFactors = FALSE, check.names = FALSE)
    if (!"cell_id" %in% colnames(meta)) stop("metadata requires cell_id")
    meta <- meta[match(cells, meta$cell_id), , drop = FALSE]
    rownames(meta) <- meta$cell_id
    rownames(counts) <- genes
    colnames(counts) <- cells
    return(list(counts = counts, meta = meta, source = "Matrix Market"))
  }
  object <- readRDS(normalizePath(config$object, mustWork = TRUE))
  if (config$input_kind == "seurat-rds") {
    if (!inherits(object, "Seurat")) stop("input is not a Seurat object")
    assay <- ifelse(is.null(config$assay), SeuratObject::DefaultAssay(object), config$assay)
    counts <- tryCatch(
      SeuratObject::LayerData(object, assay = assay, layer = ifelse(is.null(config$count_layer), "counts", config$count_layer)),
      error = function(e) SeuratObject::GetAssayData(object, assay = assay, slot = "counts")
    )
    return(list(counts = counts, meta = object[[]], source = "Seurat"))
  }
  if (!inherits(object, "SingleCellExperiment")) stop("input is not a SingleCellExperiment")
  assay_name <- ifelse(is.null(config$count_assay), "counts", config$count_assay)
  list(counts = SummarizedExperiment::assay(object, assay_name), meta = as.data.frame(SummarizedExperiment::colData(object)), source = "SingleCellExperiment")
}

loaded <- load_input()
counts <- loaded$counts
metadata <- loaded$meta
counts <- methods::as(counts, "dgCMatrix")
if (nrow(metadata) != ncol(counts)) stop("metadata rows do not match count columns")
if (is.null(rownames(metadata))) rownames(metadata) <- colnames(counts)
metadata <- metadata[colnames(counts), , drop = FALSE]
for (field in c(config$cell_type_key, config$sample_key, config$condition_key)) {
  if (!field %in% colnames(metadata)) stop(paste("metadata lacks", field))
  metadata[[field]] <- trimws(as.character(metadata[[field]]))
  if (anyNA(metadata[[field]]) || any(metadata[[field]] == "")) stop(paste("metadata is incomplete:", field))
}
if (anyNA(counts@x) || any(counts@x < 0) || any(abs(counts@x - round(counts@x)) > 1e-8)) stop("counts must be finite nonnegative integers")
sample_condition_count <- tapply(metadata[[config$condition_key]], metadata[[config$sample_key]], function(x) length(unique(x)))
if (any(sample_condition_count != 1L)) stop("each biological sample must map to exactly one condition")

normalise <- function(x) {
  totals <- Matrix::colSums(x)
  if (any(totals <= 0)) stop("zero-depth cells must be resolved upstream")
  x <- Matrix::t(Matrix::t(x) / totals) * 10000
  x@x <- log1p(x@x)
  x
}

build_cellchat <- function(indices, label) {
  meta <- metadata[indices, , drop = FALSE]
  sizes <- table(meta[[config$cell_type_key]])
  eligible <- names(sizes[sizes >= config$minimum_cells])
  keep <- meta[[config$cell_type_key]] %in% eligible
  if (length(eligible) < 2L) return(NULL)
  meta <- meta[keep, , drop = FALSE]
  expr <- normalise(counts[, indices[keep], drop = FALSE])
  object <- createCellChat(object = expr, meta = meta, group.by = config$cell_type_key)
  object@DB <- if (config$species == "human") CellChatDB.human else CellChatDB.mouse
  object <- subsetData(object)
  future::plan("sequential")
  object <- identifyOverExpressedGenes(object)
  object <- identifyOverExpressedInteractions(object)
  object <- computeCommunProb(object, type = ifelse(is.null(config$average_method), "triMean", config$average_method), raw.use = TRUE, population.size = isTRUE(config$population_size), distance.use = FALSE, nboot = config$permutations, seed.use = config$seed)
  object <- filterCommunication(object, min.cells = config$minimum_cells)
  object <- computeCommunProbPathway(object)
  object <- aggregateNet(object)
  list(object = object, table = subsetCommunication(object), label = label, eligible = eligible)
}

indices_for <- function(object, requested) {
  if (is.null(requested) || !length(requested)) return(NULL)
  found <- which(levels(object@idents) %in% requested)
  if (!length(found)) stop("requested sender or receiver labels are absent from this CellChat object")
  found
}

save_plot <- function(stem, draw) {
  for (extension in c("pdf", "png")) {
    path <- file.path(output_directory, paste0(stem, ".", extension))
    if (extension == "pdf") pdf(path, width = 7, height = 5, useDingbats = FALSE) else png(path, width = 2100, height = 1500, res = 300)
    value <- draw()
    if (inherits(value, c("gg", "ggplot", "Heatmap", "HeatmapList"))) print(value)
    dev.off()
  }
}

sample_objects <- list()
run_accounting <- list()
sample_ids <- sort(unique(metadata[[config$sample_key]]))
for (sample_id in sample_ids) {
  idx <- which(metadata[[config$sample_key]] == sample_id)
  result <- build_cellchat(idx, sample_id)
  if (is.null(result) || !nrow(result$table)) {
    run_accounting[[length(run_accounting) + 1L]] <- data.frame(sample = sample_id, condition = unique(metadata[[config$condition_key]][idx]), status = "blocked", interactions = 0L)
    next
  }
  sample_objects[[sample_id]] <- result$object
  table <- result$table
  table$sample <- sample_id
  table$condition <- unique(metadata[[config$condition_key]][idx])
  write.table(table, file.path(output_directory, paste0("cellchat_", sample_id, "_interactions.tsv")), sep = "\t", quote = FALSE, row.names = FALSE)
  write.table(as.data.frame(result$object@net$count), file.path(output_directory, paste0("cellchat_", sample_id, "_network_counts.tsv")), sep = "\t", quote = FALSE, col.names = NA)
  sources <- indices_for(result$object, config$senders)
  targets <- indices_for(result$object, config$receivers)
  save_plot(paste0("cellchat_", sample_id, "_circle"), function() netVisual_circle(result$object@net$count, vertex.weight = as.numeric(table(result$object@idents)), weight.scale = TRUE, label.edge = FALSE, title.name = sample_id))
  save_plot(paste0("cellchat_", sample_id, "_bubble"), function() netVisual_bubble(result$object, sources.use = sources, targets.use = targets, remove.isolate = FALSE))
  save_plot(paste0("cellchat_", sample_id, "_chord_gene"), function() netVisual_chord_gene(result$object, sources.use = sources, targets.use = targets, lab.cex = 0.6, legend.pos.x = 10))
  run_accounting[[length(run_accounting) + 1L]] <- data.frame(sample = sample_id, condition = table$condition[[1L]], status = "observed", interactions = nrow(table))
}
if (!length(sample_objects)) stop("no biological sample produced CellChat evidence")
saveRDS(sample_objects, file.path(output_directory, "cellchat_sample_objects.rds"))
write.table(do.call(rbind, run_accounting), file.path(output_directory, "cellchat_run_accounting.tsv"), sep = "\t", quote = FALSE, row.names = FALSE)

# Condition-pooled objects are generated only for official comparison graphics.
# They are deliberately excluded from condition-level statistical claims.
condition_objects <- list()
if (isTRUE(config$render_pooled_condition_comparison)) {
  for (condition in sort(unique(metadata[[config$condition_key]]))) {
    idx <- which(metadata[[config$condition_key]] == condition)
    result <- build_cellchat(idx, condition)
    if (!is.null(result) && nrow(result$table)) condition_objects[[condition]] <- result$object
  }
  if (length(condition_objects) >= 2L) {
    merged <- mergeCellChat(condition_objects, add.names = names(condition_objects), cell.prefix = TRUE)
    saveRDS(merged, file.path(output_directory, "cellchat_condition_pooled_merged_descriptive.rds"))
    save_plot("cellchat_condition_pooled_ranknet_descriptive", function() rankNet(merged, mode = "comparison", stacked = TRUE, do.stat = TRUE))
    if (!is.null(config$signaling_change_cell_type)) {
      identity_index <- which(levels(merged@idents$joint) == config$signaling_change_cell_type)
      if (length(identity_index) == 1L) save_plot("cellchat_condition_pooled_signaling_changes_descriptive", function() netAnalysis_signalingChanges_scatter(merged, idents.use = identity_index))
    }
  }
}

report <- list(
  schema_version = 1L,
  input_object = loaded$source,
  method = "CellChat official R API",
  biological_samples = length(sample_ids),
  observed_sample_runs = length(sample_objects),
  blocked_sample_runs = length(sample_ids) - length(sample_objects),
  condition_pooled_comparison_rendered = length(condition_objects) >= 2L,
  condition_pooled_comparison_scope = "descriptive visualization only; sample-level evidence remains authoritative",
  condition_level_inference_allowed = FALSE,
  package_versions = list(R = paste(R.version$major, R.version$minor, sep = "."), CellChat = as.character(packageVersion("CellChat"))),
  parameters = config,
  official_plot_families = c("netVisual_circle", "netVisual_chord_gene", "netVisual_bubble", "rankNet", "netAnalysis_signalingChanges_scatter"),
  outputs_reloaded = FALSE
)
write_json(report, file.path(output_directory, "cellchat_report.json"), auto_unbox = TRUE, pretty = TRUE, null = "null")
reloaded <- fromJSON(file.path(output_directory, "cellchat_report.json"), simplifyVector = FALSE)
if (!identical(reloaded$schema_version, 1L)) stop("CellChat report reload failed")
report$outputs_reloaded <- TRUE
write_json(report, file.path(output_directory, "cellchat_report.json"), auto_unbox = TRUE, pretty = TRUE, null = "null")
