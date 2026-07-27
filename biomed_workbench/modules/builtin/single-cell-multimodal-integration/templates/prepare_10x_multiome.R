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

sha256 <- function(path) digest(path, algo = "sha256", file = TRUE, serialize = FALSE)

read_ids <- function(path, name) {
  values <- trimws(readLines(path, warn = FALSE))
  if (!length(values) || any(!nzchar(values)) || anyDuplicated(values)) stop(name, " must contain unique nonempty identifiers", call. = FALSE)
  values
}

matrix_digest <- function(matrix) {
  value <- as(matrix, "dgCMatrix")
  digest(
    list(
      dim = dim(value), rows = rownames(value), columns = colnames(value),
      i = value@i, p = value@p, x = value@x
    ),
    algo = "sha256"
  )
}

package_version_or_absent <- function(name) {
  if (!requireNamespace(name, quietly = TRUE)) return("not-installed")
  as.character(packageVersion(name))
}

main <- function() {
  args <- parse_args(commandArgs(trailingOnly = TRUE))
  input_path <- normalizePath(required_arg(args, "input-h5"), mustWork = TRUE)
  cell_path <- normalizePath(required_arg(args, "cell-allowlist"), mustWork = TRUE)
  rna_path <- normalizePath(required_arg(args, "rna-feature-allowlist"), mustWork = TRUE)
  atac_path <- normalizePath(required_arg(args, "atac-feature-allowlist"), mustWork = TRUE)
  output_path <- required_arg(args, "output-rds")
  report_path <- required_arg(args, "report")
  genome <- required_arg(args, "genome-build")
  if (any(file.exists(c(output_path, report_path)))) stop("refusing to overwrite declared outputs", call. = FALSE)
  lapply(c(output_path, report_path), function(path) dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE))

  cells <- read_ids(cell_path, "cell allowlist")
  rna_features <- read_ids(rna_path, "RNA feature allowlist")
  atac_features <- read_ids(atac_path, "ATAC feature allowlist")
  if (length(cells) < 30 || length(rna_features) < 20 || length(atac_features) < 20) stop("multiome allowlists are too small", call. = FALSE)

  source_digest <- sha256(input_path)
  matrices <- Read10X_h5(input_path, use.names = TRUE, unique.features = TRUE)
  if (!is.list(matrices) || !all(c("Gene Expression", "Peaks") %in% names(matrices))) stop("10x HDF5 lacks Gene Expression or Peaks matrices", call. = FALSE)
  rna <- matrices[["Gene Expression"]]
  atac <- matrices[["Peaks"]]
  if (!identical(colnames(rna), colnames(atac))) stop("10x RNA and ATAC cell axes differ", call. = FALSE)
  if (!all(cells %in% colnames(rna)) || !all(rna_features %in% rownames(rna)) || !all(atac_features %in% rownames(atac))) stop("declared cells or features are absent from 10x HDF5", call. = FALSE)
  rna <- rna[rna_features, cells, drop = FALSE]
  atac <- atac[atac_features, cells, drop = FALSE]
  if (any(rna@x < 0) || any(atac@x < 0) || any(abs(rna@x - round(rna@x)) > 1e-8) || any(abs(atac@x - round(atac@x)) > 1e-8)) stop("10x multiome matrices must contain nonnegative integer-like counts", call. = FALSE)

  object <- CreateSeuratObject(counts = rna, assay = "RNA", project = "public-10x-multiome", min.cells = 0, min.features = 0)
  object[["ATAC"]] <- CreateChromatinAssay(
    counts = atac, sep = c(":", "-"), genome = genome,
    min.cells = 0, min.features = 0
  )
  source_matrix_digests <- c(
    RNA = matrix_digest(GetAssayData(object, assay = "RNA", layer = "counts")),
    ATAC = matrix_digest(GetAssayData(object, assay = "ATAC", layer = "counts"))
  )
  saveRDS(object, output_path)
  reloaded <- readRDS(output_path)
  reloaded_digests <- c(
    RNA = matrix_digest(GetAssayData(reloaded, assay = "RNA", layer = "counts")),
    ATAC = matrix_digest(GetAssayData(reloaded, assay = "ATAC", layer = "counts"))
  )
  if (!identical(Cells(reloaded), cells) || !identical(source_matrix_digests, reloaded_digests)) stop("prepared 10x multiome object failed cell or count reload validation", call. = FALSE)
  if (sha256(input_path) != source_digest) stop("10x multiome source changed during preparation", call. = FALSE)

  report <- list(
    schema_version = 1, quality_status = "passed",
    input = list(
      filename = basename(input_path), sha256 = source_digest,
      cell_allowlist_sha256 = sha256(cell_path),
      rna_feature_allowlist_sha256 = sha256(rna_path),
      atac_feature_allowlist_sha256 = sha256(atac_path)
    ),
    output = list(
      filename = basename(output_path), sha256 = sha256(output_path),
      cells = ncol(reloaded), RNA_features = nrow(reloaded[["RNA"]]),
      ATAC_features = nrow(reloaded[["ATAC"]]), genome_build = genome
    ),
    quality_gates = list(
      paired_cell_axis_exact = TRUE,
      nonnegative_integer_counts = TRUE,
      declared_cells_and_features_exact = TRUE,
      source_immutable = TRUE,
      output_reloaded = TRUE
    ),
    versions = list(
      R = as.character(getRversion()),
      Seurat = package_version_or_absent("Seurat"),
      Signac = package_version_or_absent("Signac"),
      Matrix = package_version_or_absent("Matrix"),
      jsonlite = package_version_or_absent("jsonlite"),
      digest = package_version_or_absent("digest")
    )
  )
  write_json(report, report_path, pretty = TRUE, auto_unbox = TRUE, null = "null")
}

main()
