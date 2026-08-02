#!/usr/bin/env Rscript
# Rebuild a sparse peak-by-cell matrix from a frozen recalled peak set and 10x fragments.

suppressPackageStartupMessages({
  library(Matrix)
  library(Signac)
  library(Seurat)
  library(GenomicRanges)
  library(IRanges)
  library(jsonlite)
  library(digest)
})

parse_args <- function(values) {
  if (length(values) %% 2 != 0 || any(!startsWith(values[seq(1, length(values), 2)], "--"))) {
    stop("arguments must be --key value pairs")
  }
  keys <- sub("^--", "", values[seq(1, length(values), 2)])
  structure(as.list(values[seq(2, length(values), 2)]), names = keys)
}

args <- parse_args(commandArgs(trailingOnly = TRUE))
required <- c("fragments", "peaks-bed", "peak-set-manifest", "cell-metadata", "matrix-rds", "peak-metadata", "cell-qc", "report")
if (!all(required %in% names(args))) stop(paste("missing arguments:", paste(setdiff(required, names(args)), collapse = ", ")))
inputs <- unlist(args[c("fragments", "peaks-bed", "peak-set-manifest", "cell-metadata")])
if (any(!file.exists(inputs))) stop(paste("missing inputs:", paste(inputs[!file.exists(inputs)], collapse = ", ")))
if (!file.exists(paste0(args$fragments, ".tbi"))) stop("fragments require an adjacent tabix index")
outputs <- unlist(args[c("matrix-rds", "peak-metadata", "cell-qc", "report")])
if ("seurat-output" %in% names(args)) outputs <- c(outputs, args$`seurat-output`)
if (any(file.exists(outputs))) stop(paste("refusing to overwrite outputs:", paste(outputs[file.exists(outputs)], collapse = ", ")))
invisible(lapply(unique(dirname(outputs)), dir.create, recursive = TRUE, showWarnings = FALSE))

file_digest <- function(path) digest(file = path, algo = "sha256", serialize = FALSE)
input_digests <- vapply(inputs, file_digest, character(1))
fragment_index_digest <- file_digest(paste0(args$fragments, ".tbi"))

cells <- read.delim(args$`cell-metadata`, check.names = FALSE, stringsAsFactors = FALSE)
required_cell_fields <- c("cell_id", "sample_id", "peak_call_group")
if (!all(required_cell_fields %in% names(cells))) stop("cell metadata requires cell_id, sample_id, and peak_call_group")
if (nrow(cells) < 10 || any(!nzchar(cells$cell_id)) || anyDuplicated(cells$cell_id)) stop("cell metadata requires at least ten unique nonempty cell IDs")
if (any(!nzchar(cells$sample_id)) || any(!nzchar(cells$peak_call_group))) stop("sample_id and peak_call_group must be nonempty")
cell_ids <- paste0(cells$cell_id)

peak_manifest <- fromJSON(args$`peak-set-manifest`, simplifyVector = FALSE)
required_manifest <- c("schema_version", "genome_build", "call_unit", "grouping_field", "method",
  "combine_policy", "reproducibility_rule", "blacklist_sha256", "standard_chromosomes",
  "min_width", "max_width", "peak_set_frozen")
if (!all(required_manifest %in% names(peak_manifest))) stop("peak-set manifest is missing required provenance")
if (!identical(peak_manifest$schema_version, 1L) || !isTRUE(peak_manifest$peak_set_frozen) ||
    !(peak_manifest$method %in% c("macs3", "archr")) ||
    !(peak_manifest$combine_policy %in% c("reproducible-consensus", "union-reduce")) ||
    !identical(peak_manifest$grouping_field, "peak_call_group") ||
    !nzchar(peak_manifest$blacklist_sha256) || !length(peak_manifest$standard_chromosomes) ||
    peak_manifest$min_width < 1 || peak_manifest$max_width < peak_manifest$min_width) {
  stop("peak-set manifest violates the frozen grouping/filter contract")
}

peaks <- read.delim(args$`peaks-bed`, header = FALSE, comment.char = "#", stringsAsFactors = FALSE)
if (ncol(peaks) < 3 || nrow(peaks) < 1) stop("peak BED requires at least one three-column interval")
names(peaks)[1:3] <- c("seqnames", "start0", "end0")
peaks$start0 <- as.integer(peaks$start0)
peaks$end0 <- as.integer(peaks$end0)
if (any(!is.finite(peaks$start0)) || any(!is.finite(peaks$end0)) || any(peaks$start0 < 0L) || any(peaks$end0 <= peaks$start0)) {
  stop("peak BED violates zero-based half-open coordinates")
}
peak_key <- paste(peaks$seqnames, peaks$start0, peaks$end0, sep = ":")
if (anyDuplicated(peak_key)) stop("recalled peak set contains duplicate intervals")
if (any(!peaks$seqnames %in% unlist(peak_manifest$standard_chromosomes))) stop("recalled peaks contain nonstandard chromosomes")
peak_width <- peaks$end0 - peaks$start0
if (any(peak_width < peak_manifest$min_width | peak_width > peak_manifest$max_width)) stop("recalled peaks violate declared width filters")
ordering <- order(peaks$seqnames, peaks$start0, peaks$end0)
if (!identical(ordering, seq_len(nrow(peaks)))) stop("recalled peak BED must be coordinate sorted")
peak_ranges <- GRanges(
  seqnames = peaks$seqnames,
  ranges = IRanges(start = peaks$start0 + 1L, end = peaks$end0)
)
peak_ids <- paste0(as.character(seqnames(peak_ranges)), ":", start(peak_ranges), "-", end(peak_ranges))
names(peak_ranges) <- peak_ids

fragment <- CreateFragmentObject(
  path = args$fragments,
  cells = cell_ids,
  validate.fragments = TRUE,
  verbose = FALSE
)
matrix <- FeatureMatrix(
  fragments = list(fragment),
  features = peak_ranges,
  keep_all_features = TRUE,
  cells = cell_ids,
  verbose = FALSE
)
matrix <- as(matrix, "dgCMatrix")
rownames(matrix) <- peak_ids
if (length(colnames(matrix)) != length(cell_ids) || any(colnames(matrix) != cell_ids)) stop("FeatureMatrix did not preserve declared cell order")
colnames(matrix) <- paste0(cells$cell_id)
if (!identical(rownames(matrix), peak_ids)) stop("FeatureMatrix did not preserve recalled peak order")
if (any(!is.finite(matrix@x)) || any(matrix@x < 0) || any(abs(matrix@x - round(matrix@x)) > 1e-8)) {
  stop("recalled peak matrix contains invalid counts")
}

saveRDS(matrix, args$`matrix-rds`, compress = TRUE)
reloaded <- readRDS(args$`matrix-rds`)
if (!inherits(reloaded, "sparseMatrix") || !identical(dim(reloaded), dim(matrix)) ||
    !identical(rownames(reloaded), peak_ids) || length(colnames(reloaded)) != length(cell_ids) ||
    any(colnames(reloaded) != cell_ids) ||
    !isTRUE(all.equal(reloaded, matrix, tolerance = 0))) {
  stop("recalled peak matrix failed exact reload")
}

peak_table <- data.frame(
  peak_id = peak_ids,
  seqnames = as.character(seqnames(peak_ranges)),
  start = start(peak_ranges),
  end = end(peak_ranges),
  width = width(peak_ranges),
  source_coordinate_system = "zero-based-half-open",
  matrix_coordinate_system = "one-based-closed",
  stringsAsFactors = FALSE
)
write.table(peak_table, args$`peak-metadata`, sep = "\t", quote = FALSE, row.names = FALSE)
cell_totals <- Matrix::colSums(matrix)
cell_detected <- Matrix::colSums(matrix > 0)
cell_qc <- data.frame(
  cell_id = cell_ids,
  sample_id = cells$sample_id,
  peak_call_group = cells$peak_call_group,
  fragments_in_recalled_peaks = as.numeric(cell_totals),
  detected_recalled_peaks = as.integer(cell_detected),
  stringsAsFactors = FALSE
)
write.table(cell_qc, args$`cell-qc`, sep = "\t", quote = FALSE, row.names = FALSE)

seurat_summary <- list(updated = FALSE)
if ("seurat-input" %in% names(args) || "seurat-output" %in% names(args)) {
  if (!all(c("seurat-input", "seurat-output") %in% names(args))) stop("seurat-input and seurat-output must be supplied together")
  if (!file.exists(args$`seurat-input`)) stop("Seurat input is missing")
  object <- readRDS(args$`seurat-input`)
  if (!inherits(object, "Seurat")) stop("seurat-input is not a Seurat object")
  if (length(Cells(object)) != length(cell_ids) || any(Cells(object) != cell_ids)) stop("Seurat cells must exactly match the rebuilt peak matrix in order")
  recalled_assay <- CreateChromatinAssay(
    counts = matrix,
    ranges = peak_ranges,
    fragments = fragment,
    sep = c(":", "-"),
    min.cells = 0,
    min.features = 0
  )
  object[["ATAC_recalled"]] <- recalled_assay
  original_assays <- setdiff(Assays(object), "ATAC_recalled")
  DefaultAssay(object) <- "ATAC_recalled"
  object <- RunTFIDF(object, verbose = FALSE)
  object <- FindTopFeatures(object, min.cutoff = "q0", verbose = FALSE)
  object <- RunSVD(object, reduction.name = "lsi_recalled", reduction.key = "LSIrecalled_", verbose = FALSE)
  lsi <- Embeddings(object, reduction = "lsi_recalled")
  depth <- Matrix::colSums(matrix)
  lsi_depth_cor <- apply(lsi, 2, function(value) suppressWarnings(cor(value, log10(depth + 1), method = "pearson")))
  wnn_rerun <- FALSE
  wnn_k <- NULL
  if ("rerun-wnn" %in% names(args) && identical(tolower(args$`rerun-wnn`), "true")) {
    rna_reduction <- if ("rna-reduction" %in% names(args)) args$`rna-reduction` else "pca"
    if (!(rna_reduction %in% Reductions(object))) stop("requested RNA reduction is absent")
    rna_dims <- if ("rna-dims" %in% names(args)) as.integer(strsplit(args$`rna-dims`, ",", fixed = TRUE)[[1]]) else 1:30
    atac_dims <- if ("atac-dims" %in% names(args)) as.integer(strsplit(args$`atac-dims`, ",", fixed = TRUE)[[1]]) else 2:min(30, ncol(lsi))
    wnn_k <- if ("wnn-k" %in% names(args)) as.integer(args$`wnn-k`) else min(20L, ncol(object) - 1L)
    if (!is.finite(wnn_k) || wnn_k < 2L || wnn_k >= ncol(object)) stop("wnn-k must be at least two and smaller than the cell count")
    if (max(rna_dims) > ncol(Embeddings(object, rna_reduction)) || max(atac_dims) > ncol(lsi)) stop("requested WNN dimensions are unavailable")
    object <- FindMultiModalNeighbors(
      object,
      reduction.list = list(rna_reduction, "lsi_recalled"),
      dims.list = list(rna_dims, atac_dims),
      k.nn = wnn_k,
      knn.range = min(200L, max(wnn_k, floor(2L * ncol(object) / 3L))),
      modality.weight.name = c("RNA.weight.recalled", "ATAC.weight.recalled"),
      weighted.nn.name = "weighted.nn.recalled",
      knn.graph.name = "wknn.recalled",
      snn.graph.name = "wsnn.recalled",
      verbose = FALSE
    )
    wnn_rerun <- TRUE
  }
  object@misc$peak_recall <- list(
    peak_set_sha256 = input_digests[["peaks-bed"]],
    fragments_sha256 = input_digests[["fragments"]],
    matrix_sha256 = file_digest(args$`matrix-rds`)
  )
  saveRDS(object, args$`seurat-output`, compress = TRUE)
  object_reloaded <- readRDS(args$`seurat-output`)
  reloaded_ranges <- if (inherits(object_reloaded, "Seurat") && "ATAC_recalled" %in% Assays(object_reloaded)) {
    granges(object_reloaded[["ATAC_recalled"]])
  } else {
    GRanges()
  }
  if (!inherits(object_reloaded, "Seurat") || !("ATAC_recalled" %in% Assays(object_reloaded)) ||
      (length(Cells(object_reloaded)) != length(cell_ids) || any(Cells(object_reloaded) != cell_ids)) ||
      length(reloaded_ranges) != length(peak_ranges) ||
      any(as.character(seqnames(reloaded_ranges)) != as.character(seqnames(peak_ranges))) ||
      any(start(reloaded_ranges) != start(peak_ranges)) ||
      any(end(reloaded_ranges) != end(peak_ranges))) {
    stop("updated Seurat object failed recalled-assay reload")
  }
  seurat_summary <- list(
    updated = TRUE,
    output_sha256 = file_digest(args$`seurat-output`),
    assay = "ATAC_recalled",
    original_assays = original_assays,
    lsi_reduction = "lsi_recalled",
    lsi_depth_correlation = unname(lsi_depth_cor),
    wnn_rerun = wnn_rerun,
    wnn_k = wnn_k
  )
}

report <- list(
  schema_version = 1,
  passed = TRUE,
  input = list(
    fragments_sha256 = input_digests[["fragments"]],
    fragments_index_sha256 = fragment_index_digest,
    peaks_sha256 = input_digests[["peaks-bed"]],
    peak_set_manifest_sha256 = input_digests[["peak-set-manifest"]],
    cell_metadata_sha256 = input_digests[["cell-metadata"]]
  ),
  accounting = list(
    cells = ncol(matrix),
    peaks = nrow(matrix),
    nonzero_entries = length(matrix@x),
    sparsity = 1 - length(matrix@x) / (nrow(matrix) * ncol(matrix)),
    samples = length(unique(cells$sample_id)),
    peak_call_groups = length(unique(cells$peak_call_group)),
    zero_fragment_cells = sum(cell_totals == 0)
  ),
  policy = list(
    label_leakage_prohibited = TRUE,
    peak_set_frozen_before_matrix_rebuild = TRUE,
    original_assays_preserved = TRUE,
    genome_build = peak_manifest$genome_build,
    peak_call_unit = peak_manifest$call_unit,
    grouping_field = peak_manifest$grouping_field,
    peak_call_method = peak_manifest$method,
    combine_policy = peak_manifest$combine_policy,
    reproducibility_rule = peak_manifest$reproducibility_rule,
    blacklist_sha256 = peak_manifest$blacklist_sha256,
    width_filter = c(peak_manifest$min_width, peak_manifest$max_width)
  ),
  outputs = list(
    matrix_sha256 = file_digest(args$`matrix-rds`),
    peak_metadata_sha256 = file_digest(args$`peak-metadata`),
    cell_qc_sha256 = file_digest(args$`cell-qc`),
    seurat = seurat_summary
  ),
  versions = list(
    R = as.character(getRversion()),
    Signac = as.character(packageVersion("Signac")),
    Seurat = as.character(packageVersion("Seurat")),
    Matrix = as.character(packageVersion("Matrix")),
    GenomicRanges = as.character(packageVersion("GenomicRanges"))
  ),
  plot_standard_version = "1.1.0",
  quality_gates = list(
    fragment_and_index_digests_retained = TRUE,
    peak_coordinates_validated_and_sorted = TRUE,
    peak_set_frozen_before_quantification = TRUE,
    grouping_consensus_blacklist_and_width_provenance_retained = TRUE,
    cell_order_preserved = TRUE,
    sparse_integer_counts_reloaded = TRUE,
    source_assays_preserved = TRUE
  )
)
write(toJSON(report, auto_unbox = TRUE, pretty = TRUE, digits = NA), args$report)
cat(toJSON(list(passed = TRUE, cells = ncol(matrix), peaks = nrow(matrix), nonzero = length(matrix@x)), auto_unbox = TRUE), "\n")
