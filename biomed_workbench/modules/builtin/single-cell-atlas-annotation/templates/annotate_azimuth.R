#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(Azimuth)
  library(digest)
  library(jsonlite)
  library(Matrix)
  library(Seurat)
  library(SeuratObject)
})

parse_args <- function(values) {
  if (length(values) %% 2 != 0) stop("arguments must be supplied as --name value pairs", call. = FALSE)
  result <- list()
  for (index in seq(1, length(values), by = 2)) {
    key <- sub("^--", "", values[[index]])
    if (key == values[[index]] || key %in% names(result)) stop("invalid or duplicate argument: ", values[[index]], call. = FALSE)
    result[[key]] <- values[[index + 1]]
  }
  result
}

required_argument <- function(args, name) {
  value <- args[[name]]
  if (is.null(value) || !nzchar(value)) stop("missing --", name, call. = FALSE)
  value
}

number_argument <- function(args, name, lower, upper = Inf, integer = FALSE) {
  value <- suppressWarnings(as.numeric(required_argument(args, name)))
  if (!is.finite(value) || value < lower || value > upper || (integer && value != floor(value))) {
    stop("invalid --", name, call. = FALSE)
  }
  value
}

file_sha256 <- function(path) digest(path, algo = "sha256", file = TRUE, serialize = FALSE)

validate_counts <- function(object, assay) {
  if (!inherits(object, "Seurat")) stop("query-rds must contain a Seurat object", call. = FALSE)
  if (!assay %in% Assays(object)) stop("declared assay is absent from query", call. = FALSE)
  cells <- Cells(object)
  features <- rownames(object[[assay]])
  if (length(cells) == 0 || anyDuplicated(cells) || length(features) == 0 || anyDuplicated(features)) {
    stop("query cell and feature identifiers must be present and unique", call. = FALSE)
  }
  counts <- LayerData(object, assay = assay, layer = "counts")
  values <- if (inherits(counts, "sparseMatrix")) counts@x else as.vector(counts)
  if (length(values) == 0 || any(!is.finite(values)) || any(values < 0) || any(abs(values - round(values)) > 1e-8)) {
    stop("Azimuth mapping requires finite nonnegative integer-like counts", call. = FALSE)
  }
  counts
}

args <- parse_args(commandArgs(trailingOnly = TRUE))
query_path <- normalizePath(required_argument(args, "query-rds"), mustWork = TRUE)
reference_dir <- normalizePath(required_argument(args, "reference-dir"), mustWork = TRUE)
homolog_path <- normalizePath(required_argument(args, "homolog-table"), mustWork = TRUE)
output_path <- required_argument(args, "output-rds")
annotations_path <- required_argument(args, "annotations-tsv")
report_path <- required_argument(args, "report")
annotation_level <- required_argument(args, "annotation-level")
assay <- required_argument(args, "assay")
score_threshold <- number_argument(args, "prediction-score-threshold", 0, 1)
mapping_threshold <- number_argument(args, "mapping-score-threshold", 0, 1)
k_weight <- number_argument(args, "k-weight", 1, integer = TRUE)
mapping_score_k <- number_argument(args, "mapping-score-k", 20, integer = TRUE)
n_trees <- number_argument(args, "n-trees", 1, integer = TRUE)
seed <- number_argument(args, "seed", 0, integer = TRUE)

if (any(file.exists(c(output_path, annotations_path, report_path)))) stop("refusing to overwrite declared outputs", call. = FALSE)
reference_rds <- file.path(reference_dir, "ref.Rds")
reference_index <- file.path(reference_dir, "idx.annoy")
if (!file.exists(reference_rds) || !file.exists(reference_index)) stop("reference-dir must contain ref.Rds and idx.annoy", call. = FALSE)
homolog_table <- readRDS(homolog_path)
if (!is.data.frame(homolog_table) || nrow(homolog_table) == 0 || ncol(homolog_table) < 2) stop("homolog-table is not a usable Azimuth homolog table", call. = FALSE)

query <- readRDS(query_path)
source_counts <- validate_counts(query, assay)
source_cells <- Cells(query)
reference <- readRDS(reference_rds)
ValidateAzimuthReference(reference)
if (!annotation_level %in% colnames(reference[[]])) stop("annotation-level is absent from the Azimuth reference", call. = FALSE)
feature_overlap <- length(intersect(rownames(query[[assay]]), rownames(reference)))
if (feature_overlap < 20) stop("query and Azimuth reference have insufficient feature overlap", call. = FALSE)
reference_dims <- ncol(Embeddings(reference[["refDR"]]))
if (reference_dims < 2) stop("Azimuth reference has insufficient dimensions", call. = FALSE)
if (mapping_score_k >= length(source_cells)) stop("mapping-score-k must be smaller than query cell count", call. = FALSE)

set.seed(seed)
options(Azimuth.map.ndims = reference_dims)
original_converter <- get("ConvertGeneNames", envir = asNamespace("Azimuth"))
local_homolog_path <- homolog_path
assignInNamespace(
  "ConvertGeneNames",
  function(object, reference.names, homolog.table) original_converter(object, reference.names, local_homolog_path),
  ns = "Azimuth"
)
on.exit(assignInNamespace("ConvertGeneNames", original_converter, ns = "Azimuth"), add = TRUE)

mapped <- RunAzimuth(
  query = query,
  reference = reference_dir,
  annotation.levels = annotation_level,
  assay = assay,
  k.weight = k_weight,
  n.trees = n_trees,
  mapping.score.k = mapping_score_k,
  verbose = FALSE
)
raw_key <- paste0("predicted.", annotation_level)
score_key <- paste0(raw_key, ".score")
required_fields <- c(raw_key, score_key, "mapping.score")
if (!all(required_fields %in% colnames(mapped[[]]))) stop("Azimuth did not return labels, confidence, and mapping score", call. = FALSE)
raw_labels <- as.character(mapped[[raw_key, drop = TRUE]])
prediction_scores <- as.numeric(mapped[[score_key, drop = TRUE]])
mapping_scores <- as.numeric(mapped[["mapping.score", drop = TRUE]])
if (any(!is.finite(prediction_scores)) || any(prediction_scores < -1e-8 | prediction_scores > 1 + 1e-8) ||
    any(!is.finite(mapping_scores)) || any(mapping_scores < -1e-8 | mapping_scores > 1 + 1e-8)) {
  stop("Azimuth returned invalid confidence values", call. = FALSE)
}
prediction_scores <- pmin(1, pmax(0, prediction_scores))
mapping_scores <- pmin(1, pmax(0, mapping_scores))
reviewed <- ifelse(prediction_scores >= score_threshold & mapping_scores >= mapping_threshold, raw_labels, "Unknown")
mapped[["azimuth_label_raw"]] <- factor(raw_labels)
mapped[["azimuth_prediction_score"]] <- prediction_scores
mapped[["azimuth_mapping_score"]] <- mapping_scores
mapped[["azimuth_label_review"]] <- factor(reviewed)
mapped@misc$biomed_azimuth_mapping <- list(
  reference_sha256 = file_sha256(reference_rds),
  reference_index_sha256 = file_sha256(reference_index),
  homolog_table_sha256 = file_sha256(homolog_path),
  annotation_level = annotation_level,
  prediction_score_threshold = score_threshold,
  mapping_score_threshold = mapping_threshold,
  feature_overlap = feature_overlap,
  seed = seed
)

dir.create(dirname(output_path), recursive = TRUE, showWarnings = FALSE)
dir.create(dirname(annotations_path), recursive = TRUE, showWarnings = FALSE)
dir.create(dirname(report_path), recursive = TRUE, showWarnings = FALSE)
saveRDS(mapped, output_path)
annotations <- data.frame(
  cell_id = Cells(mapped), raw_label = raw_labels, prediction_score = prediction_scores,
  mapping_score = mapping_scores, review_label = reviewed, stringsAsFactors = FALSE
)
write.table(annotations, annotations_path, sep = "\t", quote = FALSE, row.names = FALSE)

reloaded <- readRDS(output_path)
reloaded_counts <- LayerData(reloaded, assay = assay, layer = "counts")
if (!identical(Cells(reloaded), source_cells) || !isTRUE(all.equal(reloaded_counts, source_counts, check.attributes = TRUE)) ||
    !"azimuth_label_review" %in% colnames(reloaded[[]])) {
  stop("Azimuth output failed cell, count, or annotation reload validation", call. = FALSE)
}
reloaded_annotations <- read.delim(annotations_path, check.names = FALSE, stringsAsFactors = FALSE)
if (!identical(reloaded_annotations$cell_id, source_cells) || nrow(reloaded_annotations) != length(source_cells)) {
  stop("Azimuth annotation table failed cell accounting", call. = FALSE)
}

report <- list(
  query_sha256 = file_sha256(query_path), reference_sha256 = file_sha256(reference_rds),
  reference_index_sha256 = file_sha256(reference_index), homolog_table_sha256 = file_sha256(homolog_path),
  query_cells = length(source_cells), query_features = nrow(query), feature_overlap = feature_overlap,
  annotation_level = annotation_level, raw_label_counts = as.list(table(raw_labels)),
  review_label_counts = as.list(table(reviewed)), unknown_cells = sum(reviewed == "Unknown"),
  median_prediction_score = unname(median(prediction_scores)), median_mapping_score = unname(median(mapping_scores)),
  prediction_score_threshold = score_threshold, mapping_score_threshold = mapping_threshold,
  raw_counts_preserved = TRUE, output_reloaded = TRUE, annotation_table_reloaded = TRUE,
  versions = list(R = as.character(getRversion()), Azimuth = as.character(packageVersion("Azimuth")),
                  Seurat = as.character(packageVersion("Seurat")), SeuratObject = as.character(packageVersion("SeuratObject"))),
  quality_status = "review-required"
)
write_json(report, report_path, auto_unbox = TRUE, pretty = TRUE, null = "null")
