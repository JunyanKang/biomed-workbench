#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(digest)
  library(jsonlite)
  library(Matrix)
  library(Seurat)
  library(Signac)
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

matrix_digest <- function(matrix) digest(list(dim = dim(matrix), rows = rownames(matrix), columns = colnames(matrix), i = summary(as(matrix, "dgCMatrix"))), algo = "sha256")

package_version_or_absent <- function(name) if (requireNamespace(name, quietly = TRUE)) as.character(packageVersion(name)) else "not-installed"

main <- function() {
  args <- parse_args(commandArgs(trailingOnly = TRUE))
  input_path <- normalizePath(required_arg(args, "input-rds"), mustWork = TRUE)
  output_path <- required_arg(args, "output-rds")
  cell_table_path <- required_arg(args, "cell-table")
  report_path <- required_arg(args, "report")
  if (any(file.exists(c(output_path, cell_table_path, report_path)))) stop("refusing to overwrite declared outputs", call. = FALSE)
  lapply(c(output_path, cell_table_path, report_path), function(path) dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE))
  rna_assay <- required_arg(args, "rna-assay")
  secondary_assay <- required_arg(args, "secondary-assay")
  secondary_type <- required_arg(args, "secondary-type")
  if (!secondary_type %in% c("atac", "adt")) stop("secondary-type must be atac or adt", call. = FALSE)
  nfeatures <- numeric_arg(args, "rna-variable-features", 20, Inf, TRUE)
  rna_dims_requested <- numeric_arg(args, "rna-dims", 2, Inf, TRUE)
  secondary_dims_requested <- numeric_arg(args, "secondary-dims", 2, Inf, TRUE)
  k_nn <- numeric_arg(args, "k-nn", 5, Inf, TRUE)
  resolution <- numeric_arg(args, "resolution", 0, Inf)
  seed <- numeric_arg(args, "seed", 0, .Machine$integer.max, TRUE)

  source <- readRDS(input_path)
  if (!inherits(source, "Seurat") || !all(c(rna_assay, secondary_assay) %in% Assays(source))) stop("input must be a Seurat object with both declared assays", call. = FALSE)
  if (ncol(source) <= k_nn + 1 || anyDuplicated(Cells(source)) || nrow(source[[rna_assay]]) < nfeatures || nrow(source[[secondary_assay]]) < 10) stop("multimodal object is too small or has duplicate cells", call. = FALSE)
  source_cells <- Cells(source)
  source_digests <- c(rna = matrix_digest(GetAssayData(source, assay = rna_assay, layer = "counts")), secondary = matrix_digest(GetAssayData(source, assay = secondary_assay, layer = "counts")))
  work <- source
  set.seed(seed)

  DefaultAssay(work) <- rna_assay
  work <- NormalizeData(work, normalization.method = "LogNormalize", scale.factor = 10000, verbose = FALSE)
  work <- FindVariableFeatures(work, selection.method = "vst", nfeatures = nfeatures, verbose = FALSE)
  work <- ScaleData(work, features = VariableFeatures(work), verbose = FALSE)
  rna_rank <- min(rna_dims_requested, length(VariableFeatures(work)) - 1, ncol(work) - 1)
  work <- RunPCA(work, features = VariableFeatures(work), npcs = rna_rank, reduction.name = "rna.pca", reduction.key = "rnaPC_", seed.use = seed, verbose = FALSE)

  DefaultAssay(work) <- secondary_assay
  if (secondary_type == "atac") {
    work <- RunTFIDF(work)
    work <- FindTopFeatures(work, min.cutoff = "q0")
    secondary_rank <- min(secondary_dims_requested + 1, nrow(work[[secondary_assay]]) - 1, ncol(work) - 1)
    work <- RunSVD(work, n = secondary_rank, reduction.name = "secondary.lsi", reduction.key = "secondaryLSI_", verbose = FALSE)
    secondary_dims <- seq.int(2, secondary_rank)
  } else {
    work <- NormalizeData(work, normalization.method = "CLR", margin = 2, verbose = FALSE)
    work <- ScaleData(work, features = rownames(work[[secondary_assay]]), verbose = FALSE)
    secondary_rank <- min(secondary_dims_requested, nrow(work[[secondary_assay]]) - 1, ncol(work) - 1)
    work <- RunPCA(work, features = rownames(work[[secondary_assay]]), npcs = secondary_rank, reduction.name = "secondary.pca", reduction.key = "secondaryPC_", seed.use = seed, verbose = FALSE)
    secondary_dims <- seq_len(secondary_rank)
  }
  rna_dims <- seq_len(rna_rank)
  if (length(rna_dims) < 2 || length(secondary_dims) < 2) stop("too few modality dimensions for WNN", call. = FALSE)
  secondary_reduction <- if (secondary_type == "atac") "secondary.lsi" else "secondary.pca"
  knn_range <- min(ncol(work) - 1, max(k_nn + 1, k_nn * 3))
  work <- FindMultiModalNeighbors(work, reduction.list = list("rna.pca", secondary_reduction), dims.list = list(rna_dims, secondary_dims), k.nn = k_nn, knn.range = knn_range, knn.graph.name = "wknn", snn.graph.name = "wsnn", weighted.nn.name = "weighted.nn", modality.weight.name = c("RNA.weight", "secondary.weight"), verbose = FALSE)
  work <- RunUMAP(work, nn.name = "weighted.nn", reduction.name = "wnn.umap", reduction.key = "wnnUMAP_", seed.use = seed, verbose = FALSE)
  work <- FindClusters(work, graph.name = "wsnn", algorithm = 1, resolution = resolution, random.seed = seed, cluster.name = "wnn.cluster", verbose = FALSE)

  weight_sum <- work$RNA.weight + work$secondary.weight
  if (any(!is.finite(work$RNA.weight)) || any(work$RNA.weight < 0 | work$RNA.weight > 1) || any(abs(weight_sum - 1) > 1e-8)) stop("WNN modality weights are invalid", call. = FALSE)
  cell_table <- data.frame(cell_id = Cells(work), RNA_weight = work$RNA.weight, secondary_weight = work$secondary.weight, wnn_cluster = as.character(work$wnn.cluster), stringsAsFactors = FALSE)
  write.table(cell_table, cell_table_path, sep = "\t", quote = FALSE, row.names = FALSE)
  saveRDS(work, output_path)
  reloaded <- readRDS(output_path)
  reloaded_table <- read.delim(cell_table_path, check.names = FALSE, stringsAsFactors = FALSE)
  output_digests <- c(rna = matrix_digest(GetAssayData(reloaded, assay = rna_assay, layer = "counts")), secondary = matrix_digest(GetAssayData(reloaded, assay = secondary_assay, layer = "counts")))
  reload_valid <- identical(Cells(reloaded), source_cells) && identical(source_digests, output_digests) && all(c("wknn", "wsnn") %in% Graphs(reloaded)) && "weighted.nn" %in% Neighbors(reloaded) && "wnn.umap" %in% Reductions(reloaded) && nrow(reloaded_table) == ncol(source)
  if (!reload_valid) stop("WNN object failed graph, reduction, weight, cell, or count reload validation", call. = FALSE)

  weight_summary <- function(values) list(minimum = min(values), median = median(values), mean = mean(values), maximum = max(values))
  report <- list(schema_version = 1, quality_status = "passed", input = list(filename = basename(input_path), sha256 = sha256(input_path), cells = ncol(source), rna_features = nrow(source[[rna_assay]]), secondary_features = nrow(source[[secondary_assay]]), secondary_type = secondary_type), model = list(rna_assay = rna_assay, secondary_assay = secondary_assay, rna_dims = rna_dims, secondary_dims = secondary_dims, k_nn = k_nn, knn_range = knn_range, resolution = resolution, seed = seed), results = list(clusters = length(unique(cell_table$wnn_cluster)), RNA_weight = weight_summary(work$RNA.weight), secondary_weight = weight_summary(work$secondary.weight), wknn_nonzero = length(reloaded[["wknn"]]@x), wsnn_nonzero = length(reloaded[["wsnn"]]@x)), quality_gates = list(cells_aligned_across_assays = TRUE, modality_weights_finite_bounded_and_sum_to_one = TRUE, wknn_wsnn_and_weighted_neighbor_present = TRUE, source_counts_preserved = TRUE, outputs_reloaded = TRUE), output = list(rds_filename = basename(output_path), rds_sha256 = sha256(output_path), cell_table_filename = basename(cell_table_path), cell_table_sha256 = sha256(cell_table_path)), versions = list(R = as.character(getRversion()), Seurat = package_version_or_absent("Seurat"), Signac = package_version_or_absent("Signac"), Matrix = package_version_or_absent("Matrix"), uwot = package_version_or_absent("uwot"), jsonlite = package_version_or_absent("jsonlite"), digest = package_version_or_absent("digest")))
  write_json(report, report_path, pretty = TRUE, auto_unbox = TRUE, null = "null", na = "string")
}

main()
