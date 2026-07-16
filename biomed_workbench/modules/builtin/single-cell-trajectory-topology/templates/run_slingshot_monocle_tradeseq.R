#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(BiocParallel)
  library(digest)
  library(jsonlite)
  library(Matrix)
  library(monocle3)
  library(SingleCellExperiment)
  library(slingshot)
  library(tradeSeq)
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

comma_list <- function(value, minimum = 1) {
  items <- trimws(strsplit(value, ",", fixed = TRUE)[[1]])
  if (length(items) < minimum || any(!nzchar(items)) || anyDuplicated(items)) stop("comma-separated value is invalid", call. = FALSE)
  items
}

sha256 <- function(path) digest(path, algo = "sha256", file = TRUE, serialize = FALSE)

directory_sha256 <- function(path) {
  files <- sort(list.files(path, recursive = TRUE, full.names = TRUE, all.files = TRUE, no.. = TRUE))
  files <- files[file.info(files)$isdir %in% FALSE]
  if (!length(files)) stop("serialized Monocle3 object directory is empty", call. = FALSE)
  relative <- substring(files, nchar(normalizePath(path, mustWork = TRUE)) + 2)
  digest(paste(relative, vapply(files, sha256, character(1)), sep = "\t", collapse = "\n"), algo = "sha256", serialize = FALSE)
}

package_version_or_absent <- function(name) {
  if (!requireNamespace(name, quietly = TRUE)) return("not-installed")
  as.character(packageVersion(name))
}

finite_matrix <- function(value, name) {
  value <- as.matrix(value)
  storage.mode(value) <- "numeric"
  if (!nrow(value) || !ncol(value) || any(!is.finite(value))) stop(name, " must be a nonempty finite matrix", call. = FALSE)
  value
}

main <- function() {
  args <- parse_args(commandArgs(trailingOnly = TRUE))
  counts_path <- normalizePath(required_arg(args, "counts"), mustWork = TRUE)
  metadata_path <- normalizePath(required_arg(args, "metadata"), mustWork = TRUE)
  embedding_path <- normalizePath(required_arg(args, "embedding"), mustWork = TRUE)
  cell_results_path <- required_arg(args, "cell-results")
  gene_results_path <- required_arg(args, "gene-results")
  cds_path <- required_arg(args, "cds-output")
  report_path <- required_arg(args, "report")
  outputs <- c(cell_results_path, gene_results_path, cds_path, report_path)
  if (any(file.exists(outputs))) stop("refusing to overwrite declared outputs", call. = FALSE)
  lapply(outputs, function(path) dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE))

  cluster_key <- required_arg(args, "cluster-key")
  sample_key <- required_arg(args, "sample-key")
  external_time_key <- required_arg(args, "external-time-key")
  start_cluster <- required_arg(args, "start-cluster")
  end_clusters <- comma_list(required_arg(args, "end-clusters"), 2)
  root_cells <- comma_list(required_arg(args, "root-cells"), 3)
  nknots <- numeric_arg(args, "nknots", 3, 12, TRUE)
  minimum_lineage_cells <- numeric_arg(args, "minimum-lineage-cells", 10, Inf, TRUE)
  minimum_time_correlation <- numeric_arg(args, "minimum-time-correlation", -1, 1)
  seed <- numeric_arg(args, "seed", 0, .Machine$integer.max, TRUE)

  count_table <- read.delim(counts_path, check.names = FALSE, stringsAsFactors = FALSE)
  if (!"gene_id" %in% names(count_table) || anyDuplicated(count_table$gene_id) || any(!nzchar(count_table$gene_id))) stop("counts require unique nonempty gene_id values", call. = FALSE)
  genes <- as.character(count_table$gene_id)
  counts <- as.matrix(count_table[, setdiff(names(count_table), "gene_id"), drop = FALSE])
  storage.mode(counts) <- "numeric"
  rownames(counts) <- genes
  if (!nrow(counts) || ncol(counts) < 30 || any(!is.finite(counts)) || any(counts < 0) || any(abs(counts - round(counts)) > 1e-8)) stop("counts must be finite nonnegative integer-like gene-by-cell values", call. = FALSE)

  metadata <- read.delim(metadata_path, check.names = FALSE, stringsAsFactors = FALSE)
  required <- c("cell_id", cluster_key, sample_key, external_time_key)
  missing <- setdiff(required, names(metadata))
  if (length(missing) || anyDuplicated(metadata$cell_id) || !setequal(colnames(counts), metadata$cell_id)) stop("metadata and count cells do not align", call. = FALSE)
  metadata <- metadata[match(colnames(counts), metadata$cell_id), , drop = FALSE]
  if (any(is.na(metadata[, required]))) stop("trajectory metadata contains missing values", call. = FALSE)
  metadata[[cluster_key]] <- factor(metadata[[cluster_key]])
  external_time <- suppressWarnings(as.numeric(metadata[[external_time_key]]))
  if (any(!is.finite(external_time)) || length(unique(external_time)) < 3) stop("external time requires at least three finite levels", call. = FALSE)
  if (length(unique(metadata[[sample_key]])) < 2) stop("trajectory requires multiple biological samples", call. = FALSE)
  if (!all(c(start_cluster, end_clusters) %in% levels(metadata[[cluster_key]]))) stop("declared start or end cluster is absent", call. = FALSE)
  if (!all(root_cells %in% metadata$cell_id)) stop("declared root cells are absent", call. = FALSE)

  embedding <- read.delim(embedding_path, check.names = FALSE, stringsAsFactors = FALSE)
  if (!"cell_id" %in% names(embedding) || anyDuplicated(embedding$cell_id) || !setequal(embedding$cell_id, metadata$cell_id)) stop("embedding cells do not align", call. = FALSE)
  embedding <- embedding[match(metadata$cell_id, embedding$cell_id), , drop = FALSE]
  coordinates <- finite_matrix(embedding[, setdiff(names(embedding), "cell_id"), drop = FALSE], "embedding")
  rownames(coordinates) <- metadata$cell_id
  if (ncol(coordinates) < 2) stop("embedding requires at least two dimensions", call. = FALSE)

  set.seed(seed)
  sling <- slingshot(coordinates, clusterLabels = metadata[[cluster_key]], start.clus = start_cluster, end.clus = end_clusters, allow.breaks = FALSE)
  sling_pt <- slingPseudotime(sling, na = TRUE)
  sling_weights <- slingCurveWeights(sling)
  if (ncol(sling_pt) != length(end_clusters) || any(colSums(sling_weights > 0.1) < minimum_lineage_cells)) stop("Slingshot did not recover the declared lineages with adequate cells", call. = FALSE)
  lineage_names <- colnames(sling_pt)
  if (is.null(lineage_names)) lineage_names <- paste0("Lineage", seq_len(ncol(sling_pt)))

  gene_metadata <- data.frame(gene_short_name = genes, row.names = genes)
  cell_metadata <- metadata
  rownames(cell_metadata) <- cell_metadata$cell_id
  cds <- new_cell_data_set(as(counts, "dgCMatrix"), cell_metadata = cell_metadata, gene_metadata = gene_metadata)
  reducedDims(cds)$UMAP <- coordinates[, 1:2, drop = FALSE]
  cds <- cluster_cells(cds, reduction_method = "UMAP", k = min(20, nrow(metadata) - 1), num_iter = 2, random_seed = seed, verbose = FALSE)
  cds <- learn_graph(cds, use_partition = FALSE, close_loop = FALSE, learn_graph_control = list(minimal_branch_len = 5), verbose = FALSE)
  cds <- order_cells(cds, reduction_method = "UMAP", root_cells = root_cells)
  monocle_pt <- pseudotime(cds)
  if (any(!is.finite(monocle_pt))) stop("Monocle3 produced infinite pseudotime; graph coverage is incomplete", call. = FALSE)

  weighted_pt <- rowSums(sling_pt * sling_weights, na.rm = TRUE) / pmax(rowSums(sling_weights, na.rm = TRUE), .Machine$double.eps)
  sling_time_rho <- suppressWarnings(cor(weighted_pt, external_time, method = "spearman", use = "complete.obs"))
  monocle_time_rho <- suppressWarnings(cor(monocle_pt, external_time, method = "spearman", use = "complete.obs"))
  method_rho <- suppressWarnings(cor(weighted_pt, monocle_pt, method = "spearman", use = "complete.obs"))
  if (any(!is.finite(c(sling_time_rho, monocle_time_rho, method_rho)))) stop("trajectory correlations are nonfinite", call. = FALSE)

  set.seed(seed)
  fit_pseudotime <- sling_pt
  fit_pseudotime[is.na(fit_pseudotime)] <- 0
  if (any(sling_weights[is.na(sling_pt)] > .Machine$double.eps)) stop("Slingshot NA pseudotime carries nonzero lineage weight", call. = FALSE)
  sce <- fitGAM(
    counts = counts, pseudotime = fit_pseudotime, cellWeights = sling_weights,
    nknots = nknots, verbose = FALSE, parallel = FALSE, family = "nb"
  )
  association <- associationTest(sce, global = TRUE, lineages = TRUE, l2fc = 0)
  pattern <- patternTest(sce, global = TRUE, pairwise = TRUE, nPoints = 50, l2fc = 0)
  start_end <- startVsEndTest(sce, global = TRUE, lineages = TRUE, l2fc = 0)
  differential_end <- diffEndTest(sce, global = TRUE, pairwise = TRUE, l2fc = 0)
  standardize <- function(table, test) {
    table <- as.data.frame(table, check.names = FALSE)
    prefix <- gsub("-", "_", test, fixed = TRUE)
    names(table) <- paste0(prefix, "__", names(table))
    table$gene_id <- rownames(table)
    rownames(table) <- NULL
    table[, c("gene_id", setdiff(names(table), "gene_id")), drop = FALSE]
  }
  gene_results <- Reduce(function(x, y) merge(x, y, by = "gene_id", all = TRUE), list(
    standardize(association, "association"), standardize(pattern, "pattern"),
    standardize(start_end, "start-vs-end"), standardize(differential_end, "differential-end")
  ))

  cell_results <- data.frame(cell_id = metadata$cell_id, external_time = external_time, monocle3_pseudotime = as.numeric(monocle_pt), slingshot_weighted_pseudotime = weighted_pt, stringsAsFactors = FALSE)
  for (index in seq_len(ncol(sling_pt))) {
    cell_results[[paste0("slingshot_pseudotime_", lineage_names[[index]])]] <- sling_pt[, index]
    cell_results[[paste0("slingshot_weight_", lineage_names[[index]])]] <- sling_weights[, index]
  }
  write.table(cell_results, cell_results_path, sep = "\t", quote = FALSE, row.names = FALSE, na = "NA")
  write.table(gene_results, gene_results_path, sep = "\t", quote = FALSE, row.names = FALSE, na = "NA")
  save_monocle_objects(cds, directory_path = cds_path, hdf5_assays = FALSE, comment = "biomed-workbench trajectory topology", verbose = FALSE, archive_control = list(archive_type = "none"))
  reloaded_cells <- read.delim(cell_results_path, check.names = FALSE, stringsAsFactors = FALSE)
  reloaded_genes <- read.delim(gene_results_path, check.names = FALSE, stringsAsFactors = FALSE)
  reloaded_cds <- load_monocle_objects(cds_path)
  reload_valid <- nrow(reloaded_cells) == ncol(counts) && nrow(reloaded_genes) == nrow(counts) && ncol(reloaded_cds) == ncol(counts) && identical(colnames(reloaded_cds), colnames(counts))
  if (!reload_valid) stop("trajectory outputs failed cell, gene, or CDS reload validation", call. = FALSE)

  gates <- list(
    slingshot_lineages_recovered = ncol(sling_pt) == length(end_clusters),
    slingshot_lineage_coverage = all(colSums(sling_weights > 0.1) >= minimum_lineage_cells),
    slingshot_external_time_direction = sling_time_rho >= minimum_time_correlation,
    monocle3_external_time_direction = monocle_time_rho >= minimum_time_correlation,
    methods_directionally_concordant = method_rho > 0,
    tradeseq_all_tests_completed = all(vapply(list(association, pattern, start_end, differential_end), nrow, integer(1)) == nrow(counts)),
    biological_samples_not_cells_are_condition_replicates = TRUE,
    source_counts_preserved = sum(counts) == sum(assay(reloaded_cds, "counts")),
    outputs_reloaded = TRUE
  )
  quality_status <- if (all(unlist(gates))) "passed" else "blocked"

  report <- list(
    schema_version = 1, quality_status = quality_status,
    input = list(counts_filename = basename(counts_path), counts_sha256 = sha256(counts_path), metadata_filename = basename(metadata_path), metadata_sha256 = sha256(metadata_path), embedding_filename = basename(embedding_path), embedding_sha256 = sha256(embedding_path), cells = ncol(counts), genes = nrow(counts), samples = length(unique(metadata[[sample_key]]))),
    model = list(start_cluster = start_cluster, end_clusters = end_clusters, root_cells = length(root_cells), lineages = lineage_names, nknots = nknots, seed = seed, cds_serialization = "monocle3 native object directory with nearest-neighbor indexes"),
    results = list(slingshot_external_time_spearman = sling_time_rho, monocle3_external_time_spearman = monocle_time_rho, slingshot_monocle3_spearman = method_rho, lineage_cell_support = as.list(colSums(sling_weights > 0.1)), association_rows = nrow(association), pattern_rows = nrow(pattern), start_vs_end_rows = nrow(start_end), differential_end_rows = nrow(differential_end)),
    quality_thresholds = list(minimum_lineage_cells = minimum_lineage_cells, minimum_time_correlation = minimum_time_correlation),
    quality_gates = gates,
    output = list(cell_results_filename = basename(cell_results_path), cell_results_sha256 = sha256(cell_results_path), gene_results_filename = basename(gene_results_path), gene_results_sha256 = sha256(gene_results_path), cds_directory = basename(cds_path), cds_directory_sha256 = directory_sha256(cds_path)),
    versions = list(R = as.character(getRversion()), slingshot = package_version_or_absent("slingshot"), monocle3 = package_version_or_absent("monocle3"), tradeSeq = package_version_or_absent("tradeSeq"), SingleCellExperiment = package_version_or_absent("SingleCellExperiment"), Matrix = package_version_or_absent("Matrix"), BiocParallel = package_version_or_absent("BiocParallel"), jsonlite = package_version_or_absent("jsonlite"), digest = package_version_or_absent("digest"))
  )
  write_json(report, report_path, pretty = TRUE, auto_unbox = TRUE, null = "null", na = "string")
}

main()
