#!/usr/bin/env Rscript

# Sample-aware CellChat and contrast-aware NicheNet project template.
# Codex must adapt the JSON configuration only after inspecting the biological
# design, count provenance, gene identifiers, and donor-aware DE evidence.

suppressPackageStartupMessages({
  library(CellChat)
  library(jsonlite)
  library(Matrix)
  library(nichenetr)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2L) {
  stop("expected configuration JSON and new output directory")
}

config_path <- normalizePath(args[[1L]], mustWork = TRUE)
output_directory <- normalizePath(args[[2L]], mustWork = FALSE)
if (file.exists(output_directory)) {
  stop("refusing to overwrite an existing communication output directory")
}
dir.create(output_directory, recursive = TRUE, showWarnings = FALSE)
config <- fromJSON(config_path, simplifyVector = TRUE)

required_fields <- c(
  "matrix", "genes", "cells", "metadata", "cell_type_key", "sample_key",
  "condition_key", "species", "method", "minimum_cells", "minimum_samples",
  "expression_proportion", "permutations", "seed"
)
missing_fields <- setdiff(required_fields, names(config))
if (length(missing_fields) > 0L) {
  stop(paste("configuration omits required fields:", paste(missing_fields, collapse = ", ")))
}
if (!config$method %in% c("cellchat", "nichenet", "both")) {
  stop("method must be cellchat, nichenet, or both")
}
if (!config$species %in% c("human", "mouse")) {
  stop("species must be human or mouse")
}
if (config$minimum_cells < 3L || config$minimum_samples < 2L) {
  stop("minimum cell and biological-sample thresholds are too small")
}
if (config$expression_proportion <= 0 || config$expression_proportion > 1) {
  stop("expression proportion must be in (0, 1]")
}
if (config$permutations < 100L) {
  stop("at least 100 permutations are required")
}

counts <- readMM(normalizePath(config$matrix, mustWork = TRUE))
genes <- readLines(normalizePath(config$genes, mustWork = TRUE), warn = FALSE)
cells <- readLines(normalizePath(config$cells, mustWork = TRUE), warn = FALSE)
metadata <- read.delim(
  normalizePath(config$metadata, mustWork = TRUE), stringsAsFactors = FALSE,
  check.names = FALSE
)
if (nrow(counts) != length(genes) || ncol(counts) != length(cells)) {
  stop("matrix dimensions do not match gene and cell identifiers")
}
if (anyDuplicated(genes) || anyDuplicated(cells) || anyNA(counts@x) || any(counts@x < 0)) {
  stop("counts and identifiers must be finite, nonnegative, and unique")
}
if (any(abs(counts@x - round(counts@x)) > 1e-8)) {
  stop("input matrix is not integer-like raw counts")
}
required_metadata <- c("cell_id", config$cell_type_key, config$sample_key, config$condition_key)
if (!all(required_metadata %in% colnames(metadata))) {
  stop("metadata lacks cell, cell-type, sample, or condition fields")
}
metadata <- metadata[match(cells, metadata$cell_id), , drop = FALSE]
if (anyNA(metadata$cell_id) || !identical(as.character(metadata$cell_id), cells)) {
  stop("metadata cannot be aligned one-to-one with matrix cells")
}
for (field in required_metadata) {
  metadata[[field]] <- trimws(as.character(metadata[[field]]))
  if (anyNA(metadata[[field]]) || any(metadata[[field]] == "")) {
    stop(paste("metadata contains missing values:", field))
  }
}
sample_condition_count <- tapply(metadata[[config$condition_key]], metadata[[config$sample_key]], function(x) length(unique(x)))
if (any(sample_condition_count != 1L)) {
  stop("each biological sample must map to exactly one condition")
}
rownames(counts) <- genes
colnames(counts) <- cells

normalize_counts <- function(matrix) {
  totals <- Matrix::colSums(matrix)
  if (any(totals <= 0)) {
    stop("zero-depth cells must be resolved before communication analysis")
  }
  normalized <- Matrix::t(Matrix::t(matrix) / totals) * 10000
  normalized@x <- log1p(normalized@x)
  normalized
}

standardize_cellchat <- function(table, sample_id, condition) {
  required <- c("source", "target", "ligand", "receptor", "prob", "pval")
  if (!all(required %in% colnames(table))) {
    stop("CellChat output lacks required interaction fields")
  }
  data.frame(
    sample = sample_id,
    condition = condition,
    method = "cellchat",
    sender = as.character(table$source),
    receiver = as.character(table$target),
    ligand = as.character(table$ligand),
    receptor = as.character(table$receptor),
    score = as.numeric(table$prob),
    p_value = as.numeric(table$pval),
    stringsAsFactors = FALSE,
    check.names = FALSE
  )
}

run_cellchat_sample <- function(indices, sample_id, condition) {
  sample_meta <- metadata[indices, , drop = FALSE]
  group_sizes <- table(sample_meta[[config$cell_type_key]])
  eligible <- names(group_sizes[group_sizes >= config$minimum_cells])
  keep <- sample_meta[[config$cell_type_key]] %in% eligible
  if (length(eligible) < 2L) {
    return(NULL)
  }
  sample_meta <- sample_meta[keep, , drop = FALSE]
  sample_counts <- counts[, indices[keep], drop = FALSE]
  rownames(sample_meta) <- sample_meta$cell_id
  sample_meta$samples <- sample_id
  if (!identical(rownames(sample_meta), colnames(sample_counts))) {
    stop("sample metadata and count columns are not aligned")
  }
  expression <- normalize_counts(sample_counts)
  cellchat <- createCellChat(object = expression, meta = sample_meta, group.by = config$cell_type_key)
  cellchat@DB <- if (config$species == "human") CellChatDB.human else CellChatDB.mouse
  cellchat <- subsetData(cellchat)
  future::plan("sequential")
  cellchat <- identifyOverExpressedGenes(cellchat)
  cellchat <- identifyOverExpressedInteractions(cellchat)
  cellchat <- computeCommunProb(
    cellchat, type = "triMean", raw.use = TRUE, population.size = FALSE,
    distance.use = FALSE, nboot = config$permutations, seed.use = config$seed
  )
  cellchat <- filterCommunication(cellchat, min.cells = config$minimum_cells)
  cellchat <- computeCommunProbPathway(cellchat)
  cellchat <- aggregateNet(cellchat)
  table <- subsetCommunication(cellchat)
  if (nrow(table) == 0L) {
    return(NULL)
  }
  standardized <- standardize_cellchat(table, sample_id, condition)
  list(table = standardized, object = cellchat)
}

expressed_genes <- function(matrix, indices, proportion) {
  if (length(indices) == 0L) {
    return(character())
  }
  rownames(matrix)[Matrix::rowMeans(matrix[, indices, drop = FALSE] > 0) >= proportion]
}

run_nichenet <- function() {
  required <- c(
    "nichenet_ligand_target_matrix", "nichenet_lr_network",
    "nichenet_weighted_networks", "receiver", "contrast_condition",
    "reference_condition", "receiver_de_table"
  )
  missing <- setdiff(required, names(config))
  if (length(missing) > 0L) {
    stop(paste("NicheNet configuration omits:", paste(missing, collapse = ", ")))
  }
  ligand_target_matrix <- readRDS(normalizePath(config$nichenet_ligand_target_matrix, mustWork = TRUE))
  lr_network <- readRDS(normalizePath(config$nichenet_lr_network, mustWork = TRUE))
  weighted_networks <- readRDS(normalizePath(config$nichenet_weighted_networks, mustWork = TRUE))
  de_table <- read.delim(normalizePath(config$receiver_de_table, mustWork = TRUE), stringsAsFactors = FALSE)
  if (!all(c("gene", "log2_fold_change", "adjusted_p_value") %in% colnames(de_table))) {
    stop("receiver DE table must contain gene, log2_fold_change, and adjusted_p_value")
  }
  receiver_indices <- which(metadata[[config$cell_type_key]] == config$receiver)
  contrast_indices <- receiver_indices[metadata[[config$condition_key]][receiver_indices] == config$contrast_condition]
  reference_indices <- receiver_indices[metadata[[config$condition_key]][receiver_indices] == config$reference_condition]
  if (length(contrast_indices) < config$minimum_cells || length(reference_indices) < config$minimum_cells) {
    stop("receiver lacks sufficient cells in the declared contrast")
  }
  receiver_samples <- tapply(
    metadata[[config$sample_key]][receiver_indices],
    metadata[[config$condition_key]][receiver_indices],
    function(x) length(unique(x))
  )
  if (any(receiver_samples[c(config$contrast_condition, config$reference_condition)] < config$minimum_samples)) {
    stop("receiver contrast lacks independent biological samples")
  }
  geneset <- unique(de_table$gene[de_table$adjusted_p_value <= 0.05 & de_table$log2_fold_change > 0])
  background <- expressed_genes(counts, receiver_indices, config$expression_proportion)
  sender_indices <- which(metadata[[config$cell_type_key]] != config$receiver)
  sender_expressed <- expressed_genes(counts, sender_indices, config$expression_proportion)
  potential_ligands <- lr_network |>
    dplyr::filter(from %in% sender_expressed, to %in% background) |>
    dplyr::pull(from) |>
    unique()
  potential_ligands <- intersect(potential_ligands, colnames(ligand_target_matrix))
  if (length(geneset) < 5L || length(potential_ligands) < 2L) {
    stop("NicheNet gene set or potential-ligand universe is too small")
  }
  activities <- predict_ligand_activities(
    geneset = geneset,
    background_expressed_genes = background,
    ligand_target_matrix = ligand_target_matrix,
    potential_ligands = potential_ligands
  )
  activities <- activities[order(-activities$aupr_corrected), , drop = FALSE]
  top_ligands <- head(activities$test_ligand, 50L)
  links <- do.call(
    rbind,
    lapply(top_ligands, function(ligand) {
      get_weighted_ligand_target_links(
        ligand = ligand,
        geneset = geneset,
        ligand_target_matrix = ligand_target_matrix,
        n = 250L
      )
    })
  )
  receptors <- lr_network |>
    dplyr::filter(from %in% top_ligands, to %in% background) |>
    dplyr::select(ligand = from, receptor = to) |>
    dplyr::distinct()
  result <- merge(activities, receptors, by.x = "test_ligand", by.y = "ligand", all.x = TRUE)
  result$method <- "nichenet"
  result$receiver <- config$receiver
  list(activities = result, ligand_target_links = links, weighted_network_names = names(weighted_networks))
}

cellchat_results <- list()
cellchat_objects <- list()
run_records <- list()
if (config$method %in% c("cellchat", "both")) {
  sample_ids <- sort(unique(metadata[[config$sample_key]]))
  for (sample_id in sample_ids) {
    indices <- which(metadata[[config$sample_key]] == sample_id)
    condition <- unique(metadata[[config$condition_key]][indices])
    result <- run_cellchat_sample(indices, sample_id, condition)
    if (is.null(result)) {
      run_records[[length(run_records) + 1L]] <- list(sample = sample_id, method = "cellchat", status = "blocked")
    } else {
      cellchat_results[[sample_id]] <- result$table
      cellchat_objects[[sample_id]] <- result$object
      run_records[[length(run_records) + 1L]] <- list(sample = sample_id, method = "cellchat", status = "observed", interactions = nrow(result$table))
    }
  }
  if (length(cellchat_results) == 0L) {
    stop("no biological sample produced CellChat communication evidence")
  }
  all_interactions <- do.call(rbind, cellchat_results)
  write.table(all_interactions, file.path(output_directory, "cellchat_sample_interactions.tsv"), sep = "\t", quote = FALSE, row.names = FALSE)
  saveRDS(cellchat_objects, file.path(output_directory, "cellchat_objects.rds"))
}

nichenet_result <- NULL
if (config$method %in% c("nichenet", "both")) {
  nichenet_result <- run_nichenet()
  write.table(nichenet_result$activities, file.path(output_directory, "nichenet_ligand_activities.tsv"), sep = "\t", quote = FALSE, row.names = FALSE)
  write.table(nichenet_result$ligand_target_links, file.path(output_directory, "nichenet_ligand_target_links.tsv"), sep = "\t", quote = FALSE, row.names = FALSE)
}

versions <- list(
  r = paste(R.version$major, R.version$minor, sep = "."),
  CellChat = as.character(packageVersion("CellChat")),
  nichenetr = as.character(packageVersion("nichenetr")),
  Matrix = as.character(packageVersion("Matrix")),
  jsonlite = as.character(packageVersion("jsonlite"))
)
report <- list(
  schema_version = 1L,
  methods = config$method,
  biological_samples = length(unique(metadata[[config$sample_key]])),
  conditions = sort(unique(metadata[[config$condition_key]])),
  sample_runs = run_records,
  nichenet_executed = !is.null(nichenet_result),
  source_dimensions_preserved = identical(dim(counts), c(length(genes), length(cells))),
  parameters = config,
  versions = versions,
  quality_status = "observed"
)
write_json(report, file.path(output_directory, "communication_report.json"), auto_unbox = TRUE, pretty = TRUE, null = "null")
reloaded <- fromJSON(file.path(output_directory, "communication_report.json"), simplifyVector = FALSE)
if (!identical(reloaded$schema_version, 1L) || !isTRUE(reloaded$source_dimensions_preserved)) {
  stop("communication report reload or source-preservation validation failed")
}
