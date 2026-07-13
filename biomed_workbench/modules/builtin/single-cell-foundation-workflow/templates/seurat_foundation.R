#!/usr/bin/env Rscript
# Project template for a traceable Seurat v5 single-cell foundation workflow.
# Codex must inspect and adapt this template before execution.

suppressPackageStartupMessages({
  library(Seurat)
  library(SeuratObject)
  library(jsonlite)
})

parse_args <- function(args) {
  if (length(args) %% 2 != 0) stop("arguments must be --name value pairs")
  out <- list()
  for (i in seq(1, length(args), by = 2)) {
    key <- sub("^--", "", args[[i]])
    if (key == args[[i]] || key %in% names(out)) stop("invalid or duplicate argument")
    out[[key]] <- args[[i + 1]]
  }
  out
}

required <- c("input", "output-rds", "qc-report", "cluster-report", "sample-key", "assay",
              "min-counts", "max-counts", "min-features", "max-features", "max-mito-percent",
              "n-variable-features", "n-pcs", "n-neighbors", "resolutions", "seed")
args <- parse_args(commandArgs(trailingOnly = TRUE))
missing <- setdiff(required, names(args))
if (length(missing)) stop(paste("missing arguments:", paste(missing, collapse = ", ")))
for (path in c(args$`output-rds`, args$`qc-report`, args$`cluster-report`)) {
  if (file.exists(path)) stop(paste("refusing to overwrite", basename(path)))
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
}

set.seed(as.integer(args$seed))
object <- readRDS(args$input)
if (!inherits(object, "Seurat")) stop("input is not a Seurat object")
if (!(args$assay %in% Assays(object))) stop("declared assay is absent")
DefaultAssay(object) <- args$assay
if (!(args$`sample-key` %in% colnames(object[[]]))) stop("biological sample key is absent")
if (anyNA(object[[args$`sample-key`, drop = TRUE]])) stop("biological sample key is incomplete")
if (anyDuplicated(Cells(object)) || anyDuplicated(Features(object))) stop("cell and feature identifiers must be unique")

layers <- Layers(object[[args$assay]])
if (!("counts" %in% layers)) stop("Seurat v5 counts layer is absent; do not guess or join layers")
counts <- LayerData(object, assay = args$assay, layer = "counts")
if (length(counts@x) == 0 || any(!is.finite(counts@x)) || any(counts@x < 0) || any(abs(counts@x - round(counts@x)) > 1e-8)) {
  stop("counts layer must contain finite nonnegative integer-like values")
}

object[["percent.mt"]] <- PercentageFeatureSet(object, pattern = "^(MT-|mt-)")
meta <- object[[]]
min_counts <- as.numeric(args$`min-counts`)
max_counts <- as.numeric(args$`max-counts`)
min_features <- as.numeric(args$`min-features`)
max_features <- as.numeric(args$`max-features`)
max_mito <- as.numeric(args$`max-mito-percent`)
reasons <- lapply(seq_len(nrow(meta)), function(i) character())
add_reason <- function(mask, label) for (i in which(mask)) reasons[[i]] <<- c(reasons[[i]], label)
add_reason(meta$nCount_RNA < min_counts, "low-counts")
add_reason(meta$nFeature_RNA < min_features, "low-features")
add_reason(meta$percent.mt > max_mito, "high-mitochondrial-fraction")
if (max_counts > 0) add_reason(meta$nCount_RNA > max_counts, "high-counts")
if (max_features > 0) add_reason(meta$nFeature_RNA > max_features, "high-features")
retained <- lengths(reasons) == 0
if (sum(retained) < 3) stop("QC retains too few cells")
accounting <- data.frame(cell_id = rownames(meta), sample = as.character(meta[[args$`sample-key`]]), retained = retained,
                         exclusion_reasons = vapply(reasons, paste, collapse = ";", FUN.VALUE = character(1)))
object <- subset(object, cells = accounting$cell_id[retained])

object <- NormalizeData(object, assay = args$assay, normalization.method = "LogNormalize", scale.factor = 10000, verbose = FALSE)
object <- FindVariableFeatures(object, assay = args$assay, selection.method = "vst",
                               nfeatures = as.integer(args$`n-variable-features`), verbose = FALSE)
object <- ScaleData(object, assay = args$assay, features = VariableFeatures(object), verbose = FALSE)
npcs <- min(as.integer(args$`n-pcs`), ncol(object) - 1, length(VariableFeatures(object)) - 1)
if (npcs < 2) stop("too few cells or variable features for PCA")
object <- RunPCA(object, assay = args$assay, features = VariableFeatures(object), npcs = npcs, seed.use = as.integer(args$seed), verbose = FALSE)
object <- FindNeighbors(object, reduction = "pca", dims = seq_len(npcs), k.param = as.integer(args$`n-neighbors`), verbose = FALSE)
resolutions <- sort(unique(as.numeric(strsplit(args$resolutions, ",", fixed = TRUE)[[1]])))
if (!length(resolutions) || any(!is.finite(resolutions)) || any(resolutions <= 0)) stop("invalid resolutions")
for (resolution in resolutions) {
  object <- FindClusters(object, resolution = resolution, random.seed = as.integer(args$seed), verbose = FALSE)
  object[[paste0("seurat_clusters_", format(resolution, trim = TRUE))]] <- Idents(object)
}
object <- RunUMAP(object, reduction = "pca", dims = seq_len(npcs), seed.use = as.integer(args$seed), verbose = FALSE)

object@misc$biomed_workbench <- list(
  template = "seurat_foundation.R",
  versions = list(R = R.version.string, Seurat = as.character(packageVersion("Seurat")), SeuratObject = as.character(packageVersion("SeuratObject"))),
  parameters = args,
  raw_count_location = paste0(args$assay, ":counts")
)
saveRDS(object, args$`output-rds`, compress = "xz")
reloaded <- readRDS(args$`output-rds`)
if (!inherits(reloaded, "Seurat") || !("counts" %in% Layers(reloaded[[args$assay]])) || ncol(reloaded) != sum(retained)) stop("reloaded Seurat object failed validation")

sample_rows <- lapply(split(accounting, accounting$sample), function(frame) list(
  sample = frame$sample[[1]], input_cells = nrow(frame), retained_cells = sum(frame$retained), excluded_cells = sum(!frame$retained)
))
qc <- list(
  input_cells = nrow(accounting), retained_cells = sum(retained), excluded_cells = sum(!retained),
  sample_accounting = unname(sample_rows),
  methods = list(empty_droplet = "not-run", ambient_rna = "not-run", doublet = "not-run"),
  thresholds = list(min_counts = min_counts, max_counts = max_counts, min_features = min_features, max_features = max_features, max_mito_percent = max_mito),
  versions = list(R = as.character(getRversion()), Seurat = as.character(packageVersion("Seurat")), SeuratObject = as.character(packageVersion("SeuratObject")))
)
cluster_columns <- grep("^seurat_clusters_", colnames(reloaded[[]]), value = TRUE)
clusters <- lapply(cluster_columns, function(key) list(key = key, cluster_sizes = as.list(table(reloaded[[key, drop = TRUE]]))))
cluster_report <- list(cluster_columns = cluster_columns, clusters = clusters, n_pcs = npcs,
                       n_neighbors = as.integer(args$`n-neighbors`), random_seed = as.integer(args$seed))
write_json(qc, args$`qc-report`, pretty = TRUE, auto_unbox = TRUE)
write_json(cluster_report, args$`cluster-report`, pretty = TRUE, auto_unbox = TRUE)
