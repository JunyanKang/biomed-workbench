#!/usr/bin/env Rscript
# Execute motif matching, chromVAR deviations, and Signac peak-to-gene linking.

suppressPackageStartupMessages({
  library(Matrix)
  library(Seurat)
  library(Signac)
  library(Biostrings)
  library(chromVAR)
  library(digest)
  library(GenomicRanges)
  library(jsonlite)
  library(motifmatchr)
  library(SummarizedExperiment)
})

parse_args <- function(values) {
  if (length(values) %% 2 != 0 || any(!startsWith(values[seq(1, length(values), 2)], "--"))) stop("arguments must be --key value pairs")
  keys <- sub("^--", "", values[seq(1, length(values), 2)])
  structure(as.list(values[seq(2, length(values), 2)]), names = keys)
}

required <- c(
  "peak-counts-rds", "cell-metadata", "peak-metadata", "peak-sequences-fasta", "motifs-rds",
  "rna-counts-rds", "gene-metadata", "output-rds", "motif-match-table", "deviation-table",
  "background-table", "link-table", "report", "seed", "background-iterations", "background-window",
  "background-bins", "link-distance", "link-min-cells", "link-background-samples", "link-pvalue", "link-score"
)
args <- parse_args(commandArgs(trailingOnly = TRUE))
if (!all(required %in% names(args))) stop(paste("missing arguments:", paste(setdiff(required, names(args)), collapse = ", ")))

input_paths <- unlist(args[c("peak-counts-rds", "cell-metadata", "peak-metadata", "peak-sequences-fasta", "motifs-rds", "rna-counts-rds", "gene-metadata")])
if (any(!file.exists(input_paths))) stop(paste("input files are missing:", paste(input_paths[!file.exists(input_paths)], collapse = ", ")))
output_paths <- unlist(args[c("output-rds", "motif-match-table", "deviation-table", "background-table", "link-table", "report")])
if (any(file.exists(output_paths))) stop(paste("refusing to overwrite outputs:", paste(output_paths[file.exists(output_paths)], collapse = ", ")))
invisible(lapply(unique(dirname(output_paths)), dir.create, recursive = TRUE, showWarnings = FALSE))

seed <- as.integer(args$seed)
background_iterations <- as.integer(args$`background-iterations`)
background_window <- as.numeric(args$`background-window`)
background_bins <- as.integer(args$`background-bins`)
link_distance <- as.numeric(args$`link-distance`)
link_min_cells <- as.integer(args$`link-min-cells`)
link_background_samples <- as.integer(args$`link-background-samples`)
link_pvalue <- as.numeric(args$`link-pvalue`)
link_score <- as.numeric(args$`link-score`)
if (any(!is.finite(c(seed, background_iterations, background_window, background_bins, link_distance, link_min_cells, link_background_samples, link_pvalue, link_score)))) stop("numeric parameters must be finite")
if (background_iterations < 10 || background_window <= 0 || background_bins < 10 || link_distance <= 0 || link_min_cells < 1 || link_background_samples < 10 || link_pvalue <= 0 || link_pvalue > 1 || link_score < 0 || link_score >= 1) stop("invalid background or LinkPeaks parameter")

file_digest <- function(path) digest(file = path, algo = "sha256", serialize = FALSE)
input_digests <- vapply(input_paths, file_digest, character(1))
names(input_digests) <- names(input_paths)

peak_counts <- readRDS(args$`peak-counts-rds`)
rna_counts <- readRDS(args$`rna-counts-rds`)
if (!inherits(peak_counts, "sparseMatrix") || !inherits(rna_counts, "sparseMatrix")) stop("peak and RNA counts must be sparse Matrix objects")
if (is.null(rownames(peak_counts)) || is.null(colnames(peak_counts)) || is.null(rownames(rna_counts)) || is.null(colnames(rna_counts))) stop("count matrices require feature and cell identifiers")
if (anyDuplicated(rownames(peak_counts)) || anyDuplicated(colnames(peak_counts)) || anyDuplicated(rownames(rna_counts)) || anyDuplicated(colnames(rna_counts))) stop("count identifiers must be unique")
if (!identical(colnames(peak_counts), colnames(rna_counts))) stop("RNA and ATAC cells must be identical and in the same order")
for (matrix in list(peak_counts, rna_counts)) {
  if (any(!is.finite(matrix@x)) || any(matrix@x < 0) || any(abs(matrix@x - round(matrix@x)) > 1e-8)) stop("count values must be finite, nonnegative, and integer-like")
}
source_matrix_digests <- c(peak_counts = digest(peak_counts, algo = "sha256"), rna_counts = digest(rna_counts, algo = "sha256"))

cells <- read.delim(args$`cell-metadata`, check.names = FALSE, stringsAsFactors = FALSE)
if (!("cell_id" %in% names(cells)) || anyDuplicated(cells$cell_id)) stop("cell metadata requires unique cell_id")
if (!identical(cells$cell_id, colnames(peak_counts))) stop("cell metadata must have exact count-matrix order")
rownames(cells) <- cells$cell_id

peaks <- read.delim(args$`peak-metadata`, check.names = FALSE, stringsAsFactors = FALSE)
peak_fields <- c("peak_id", "seqnames", "start", "end")
if (!all(peak_fields %in% names(peaks)) || anyDuplicated(peaks$peak_id)) stop("peak metadata requires unique peak_id, seqnames, start, and end")
if (!identical(peaks$peak_id, rownames(peak_counts))) stop("peak metadata must have exact count-matrix order")
if (any(!is.finite(peaks$start)) || any(!is.finite(peaks$end)) || any(peaks$start < 1) || any(peaks$end < peaks$start)) stop("peak coordinates must be finite one-based closed intervals")
peak_ranges <- GRanges(seqnames = peaks$seqnames, ranges = IRanges(start = as.integer(peaks$start), end = as.integer(peaks$end)))
names(peak_ranges) <- peaks$peak_id

peak_sequences <- readDNAStringSet(args$`peak-sequences-fasta`)
names(peak_sequences) <- sub(" .*", "", names(peak_sequences))
if (anyDuplicated(names(peak_sequences)) || !identical(names(peak_sequences), peaks$peak_id)) stop("peak FASTA names and order must exactly match peak_id")
if (!identical(as.integer(width(peak_sequences)), as.integer(width(peak_ranges)))) stop("peak sequence widths must match peak coordinates")
gc_bias <- as.numeric(letterFrequency(peak_sequences, letters = "GC", as.prob = TRUE)[, 1])
if (any(!is.finite(gc_bias)) || any(gc_bias < 0 | gc_bias > 1)) stop("peak GC fractions are invalid")

genes <- read.delim(args$`gene-metadata`, check.names = FALSE, stringsAsFactors = FALSE)
gene_fields <- c("gene_id", "gene_name", "seqnames", "start", "end", "strand")
if (!all(gene_fields %in% names(genes)) || anyDuplicated(genes$gene_id) || anyDuplicated(genes$gene_name)) stop("gene metadata requires unique gene_id and gene_name plus coordinates and strand")
if (!identical(genes$gene_name, rownames(rna_counts))) stop("gene metadata must have exact RNA count-matrix order")
if (any(!genes$strand %in% c("+", "-", "*")) || any(genes$start < 1) || any(genes$end < genes$start)) stop("gene coordinates or strands are invalid")
gene_ranges <- GRanges(seqnames = genes$seqnames, ranges = IRanges(start = as.integer(genes$start), end = as.integer(genes$end)), strand = genes$strand)
gene_ranges$gene_id <- genes$gene_id
gene_ranges$gene_name <- genes$gene_name

chromatin <- CreateChromatinAssay(counts = peak_counts, ranges = peak_ranges, min.cells = 0, min.features = 0)
object <- CreateSeuratObject(counts = chromatin, assay = "ATAC", meta.data = cells)
object[["RNA"]] <- CreateAssayObject(counts = rna_counts, min.cells = 0, min.features = 0)
object <- NormalizeData(object, assay = "RNA", normalization.method = "LogNormalize", scale.factor = 10000, verbose = FALSE)
peak_statistics <- data.frame(GC.percent = gc_bias * 100, sequence.length = width(peak_ranges), row.names = peaks$peak_id)
object[["ATAC"]] <- AddMetaData(object[["ATAC"]], metadata = peak_statistics)
set.seed(seed)
message("ATAC regulatory stage: LinkPeaks")
object <- LinkPeaks(
  object = object, peak.assay = "ATAC", expression.assay = "RNA", peak.slot = "counts", expression.slot = "data",
  method = "pearson", gene.coords = gene_ranges, distance = link_distance, min.cells = link_min_cells,
  genes.use = genes$gene_name, n_sample = link_background_samples, pvalue_cutoff = link_pvalue,
  score_cutoff = link_score, gene.id = FALSE, verbose = FALSE
)
links <- Links(object[["ATAC"]])
link_frame <- if (length(links)) as.data.frame(links) else data.frame()
rm(object, chromatin)
invisible(gc(verbose = FALSE))

message("ATAC regulatory stage: motifmatchr and chromVAR")
motifs <- readRDS(args$`motifs-rds`)
if (!inherits(motifs, c("PFMatrixList", "PWMatrixList")) || length(motifs) < 1) stop("motifs RDS must contain a nonempty PFMatrixList or PWMatrixList")
motif_ids <- names(motifs)
if (is.null(motif_ids) || any(!nzchar(motif_ids)) || anyDuplicated(motif_ids)) stop("motifs require unique nonempty names")
motif_result <- matchMotifs(motifs, peak_sequences, out = "matches")
motif_matches <- motifMatches(motif_result)
rownames(motif_matches) <- peaks$peak_id
colnames(motif_matches) <- motif_ids
if (!identical(dim(motif_matches), c(nrow(peak_counts), length(motifs)))) stop("motif match dimensions are inconsistent")
motif_match_counts <- Matrix::colSums(motif_matches)
eligible_motifs <- motif_match_counts >= 2 & motif_match_counts <= (nrow(peak_counts) - 2)
if (!any(eligible_motifs)) stop("no motif has enough matched and unmatched peaks for chromVAR")
motif_status <- ifelse(eligible_motifs, "modeled", "insufficient_matched_peaks")
names(motif_status) <- motif_ids

experiment <- SummarizedExperiment(assays = list(counts = peak_counts), rowRanges = peak_ranges, colData = DataFrame(cells))
rowData(experiment)$bias <- gc_bias
set.seed(seed)
background_peaks <- getBackgroundPeaks(experiment, bias = gc_bias, niterations = background_iterations, w = background_window, bs = background_bins)
if (nrow(background_peaks) != nrow(peak_counts) || ncol(background_peaks) != background_iterations) stop("chromVAR background matrix has unexpected dimensions")
if (any(background_peaks < 1 | background_peaks > nrow(peak_counts))) stop("chromVAR background indices are invalid")
deviations <- computeDeviations(experiment, motif_matches[, eligible_motifs, drop = FALSE], background_peaks = background_peaks)
deviation_matrix <- assay(deviations, "deviations")
z_matrix <- assay(deviations, "z")
rownames(deviation_matrix) <- rownames(z_matrix) <- motif_ids[eligible_motifs]
if (!identical(dim(deviation_matrix), c(sum(eligible_motifs), ncol(peak_counts))) || any(!is.finite(deviation_matrix)) || any(!is.finite(z_matrix))) stop("eligible chromVAR deviation outputs are incomplete or nonfinite")

message("ATAC regulatory stage: export tables")
match_summary <- summary(motif_matches)
match_table <- if (nrow(match_summary)) data.frame(
  peak_id = peaks$peak_id[match_summary$i], motif_id = motif_ids[match_summary$j], matched = TRUE,
  stringsAsFactors = FALSE
) else data.frame(peak_id = character(), motif_id = character(), matched = logical())
write.table(match_table, args$`motif-match-table`, sep = "\t", quote = FALSE, row.names = FALSE)

deviation_table <- expand.grid(motif_id = motif_ids, cell_id = colnames(peak_counts), stringsAsFactors = FALSE)
deviation_table$status <- motif_status[deviation_table$motif_id]
deviation_table$matched_peaks <- as.integer(motif_match_counts[deviation_table$motif_id])
deviation_table$deviation <- NA_real_
deviation_table$z <- NA_real_
eligible_rows <- deviation_table$status == "modeled"
deviation_table$deviation[eligible_rows] <- as.vector(deviation_matrix)
deviation_table$z[eligible_rows] <- as.vector(z_matrix)
write.table(deviation_table, args$`deviation-table`, sep = "\t", quote = FALSE, row.names = FALSE)

background_table <- data.frame(peak_id = peaks$peak_id, background_peaks, check.names = FALSE)
names(background_table)[-1] <- paste0("background_", seq_len(ncol(background_peaks)))
for (column in names(background_table)[-1]) background_table[[column]] <- peaks$peak_id[background_table[[column]]]
write.table(background_table, args$`background-table`, sep = "\t", quote = FALSE, row.names = FALSE)
write.table(link_frame, args$`link-table`, sep = "\t", quote = FALSE, row.names = FALSE)

message("ATAC regulatory stage: save and reload RDS")
derived <- list(
  motif_matches = motif_matches, motif_status = motif_status, background_peaks = background_peaks, chromvar_deviations = deviations,
  links = links, peak_ids = peaks$peak_id, cell_ids = cells$cell_id, gene_ids = genes$gene_id,
  input_digests = input_digests,
  parameters = list(seed = seed, background_iterations = background_iterations, background_window = background_window, background_bins = background_bins, link_distance = link_distance, link_min_cells = link_min_cells, link_background_samples = link_background_samples, link_pvalue = link_pvalue, link_score = link_score)
)
saveRDS(derived, args$`output-rds`)
reloaded <- readRDS(args$`output-rds`)
if (!identical(reloaded$peak_ids, peaks$peak_id) || !identical(reloaded$cell_ids, cells$cell_id) || !identical(dim(reloaded$motif_matches), dim(motif_matches))) stop("reloaded regulatory RDS failed validation")
if (!identical(vapply(input_paths, file_digest, character(1)), input_digests)) stop("an input artifact changed during analysis")
if (!identical(c(peak_counts = digest(peak_counts, algo = "sha256"), rna_counts = digest(rna_counts, algo = "sha256")), source_matrix_digests)) stop("source count matrices changed in memory")

message("ATAC regulatory stage: write report")
versions <- list(
  R = as.character(getRversion()), Signac = as.character(packageVersion("Signac")), Seurat = as.character(packageVersion("Seurat")),
  chromVAR = as.character(packageVersion("chromVAR")), motifmatchr = as.character(packageVersion("motifmatchr")),
  Matrix = as.character(packageVersion("Matrix")), GenomicRanges = as.character(packageVersion("GenomicRanges")),
  Biostrings = as.character(packageVersion("Biostrings")), SummarizedExperiment = as.character(packageVersion("SummarizedExperiment")),
  TFBSTools = as.character(packageVersion("TFBSTools")), jsonlite = as.character(packageVersion("jsonlite")), digest = as.character(packageVersion("digest"))
)
report <- list(
  schema_version = 1, passed = TRUE, quality_status = "passed", versions = versions,
  input = list(peaks = nrow(peak_counts), cells = ncol(peak_counts), genes = nrow(rna_counts), motifs = length(motifs), source_sha256 = as.list(input_digests)),
  results = list(motif_matches = nrow(match_table), modeled_motifs = sum(eligible_motifs), unsupported_motifs = sum(!eligible_motifs), background_rows = nrow(background_table), background_iterations = ncol(background_peaks), deviation_rows = nrow(deviation_table), peak_gene_links = length(links)),
  parameters = derived$parameters,
  scientific_checks = list(
    motifmatchr_executed = TRUE, gc_and_accessibility_matched_backgrounds_executed = TRUE, chromvar_executed = TRUE,
    signac_linkpeaks_executed = TRUE, paired_rna_atac_cells_preserved = TRUE, raw_counts_preserved = TRUE,
    method_specific_outputs_retained = TRUE, outputs_reloaded = TRUE, no_environment_or_compute_infrastructure_managed = TRUE
  ),
  output_sha256 = list(
    regulatory_rds = file_digest(args$`output-rds`), motif_matches = file_digest(args$`motif-match-table`),
    deviations = file_digest(args$`deviation-table`), backgrounds = file_digest(args$`background-table`), links = file_digest(args$`link-table`)
  )
)
write_json(report, args$report, pretty = TRUE, auto_unbox = TRUE, digits = NA)
cat(toJSON(list(passed = TRUE, motif_matches = nrow(match_table), peak_gene_links = length(links), versions = versions[c("Signac", "chromVAR", "motifmatchr")]), auto_unbox = TRUE), "\n")
