#!/usr/bin/env Rscript
# Sample-level WGCNA with explicit threshold diagnostics and module/trait outputs.

suppressPackageStartupMessages({
  library(WGCNA)
  library(jsonlite)
  library(digest)
})
options(stringsAsFactors = FALSE)

parse_args <- function(x) {
  if (length(x) %% 2 != 0 || any(!startsWith(x[seq(1, length(x), 2)], "--"))) stop("arguments must be --key value pairs")
  structure(as.list(x[seq(2, length(x), 2)]), names = sub("^--", "", x[seq(1, length(x), 2)]))
}
args <- parse_args(commandArgs(trailingOnly = TRUE))
required <- c("expression", "traits", "output-dir", "network-type", "cor-type", "powers", "min-module-size", "deep-split", "merge-cut-height", "seed")
if (!all(required %in% names(args))) stop("required WGCNA parameters are missing")
threads <- if ("threads" %in% names(args)) as.integer(args$threads) else 1L
if (!is.finite(threads) || threads < 1L) stop("threads must be a positive integer")
if (threads == 1L) disableWGCNAThreads() else allowWGCNAThreads(nThreads = threads)
if (!all(file.exists(unlist(args[c("expression", "traits")]))) ) stop("input file is missing")
if (dir.exists(args$`output-dir`) && length(list.files(args$`output-dir`, all.files = TRUE, no.. = TRUE))) stop("output directory is not empty")
dir.create(args$`output-dir`, recursive = TRUE, showWarnings = FALSE)

expr <- read.delim(args$expression, check.names = FALSE, stringsAsFactors = FALSE)
traits <- read.delim(args$traits, check.names = FALSE, stringsAsFactors = FALSE)
if (!identical(names(expr)[1], "feature_id") || !identical(names(traits)[1], "sample_id")) stop("expression starts with feature_id and traits with sample_id")
if (anyDuplicated(expr$feature_id) || anyDuplicated(traits$sample_id)) stop("identifiers must be unique")
sample_ids <- names(expr)[-1]
if (!identical(sample_ids, traits$sample_id)) stop("expression sample columns must exactly match ordered trait sample_id")
datExpr <- t(as.matrix(expr[, -1, drop = FALSE]))
storage.mode(datExpr) <- "double"
colnames(datExpr) <- expr$feature_id
rownames(datExpr) <- sample_ids
if (nrow(datExpr) < 15) stop("fewer than 15 independent samples: block standard WGCNA and use a justified exploratory or resampled design")
if (any(is.infinite(datExpr))) stop("expression contains infinity")
gsg <- goodSamplesGenes(datExpr, verbose = 0)
if (!gsg$allOK) stop("bad samples or genes detected; resolve upstream rather than silently filter")

network_type <- args$`network-type`
cor_type <- args$`cor-type`
if (!(network_type %in% c("unsigned", "signed", "signed hybrid")) || !(cor_type %in% c("pearson", "bicor"))) stop("invalid network or correlation type")
powers <- as.integer(strsplit(args$powers, ",", fixed = TRUE)[[1]])
if (!length(powers) || any(!is.finite(powers)) || any(powers < 1)) stop("powers must be positive integers")
set.seed(as.integer(args$seed))
sft <- pickSoftThreshold(datExpr, powerVector = powers, networkType = network_type,
  corFnc = if (cor_type == "bicor") "bicor" else "cor", verbose = 0)
fit <- sft$fitIndices
fit$Signed.SFT.R.sq <- -sign(fit$slope) * fit$SFT.R.sq
if ("power" %in% names(args)) {
  power <- as.integer(args$power)
  if (!(power %in% powers)) stop("manual power must be included in diagnostic powers")
  power_rule <- "manual-predeclared"
} else {
  eligible <- fit$Power[is.finite(fit$Signed.SFT.R.sq) & fit$Signed.SFT.R.sq >= 0.85]
  if (!length(eligible)) stop("no candidate power reached the declared scale-free topology R-squared criterion 0.85")
  power <- min(eligible)
  power_rule <- "lowest-candidate-reaching-R2-0.85"
}

modules <- blockwiseModules(datExpr, power = power, maxBlockSize = if ("max-block-size" %in% names(args)) as.integer(args$`max-block-size`) else 5000,
  corType = cor_type, networkType = network_type, TOMType = if (startsWith(network_type, "signed")) "signed" else "unsigned",
  minModuleSize = as.integer(args$`min-module-size`), deepSplit = as.integer(args$`deep-split`),
  mergeCutHeight = as.numeric(args$`merge-cut-height`), pamRespectsDendro = TRUE,
  numericLabels = FALSE, randomSeed = as.integer(args$seed), verbose = 0)
colors <- modules$colors
MEs <- orderMEs(moduleEigengenes(datExpr, colors = colors)$eigengenes)
trait_data <- traits[, -1, drop = FALSE]
numeric_traits <- vapply(trait_data, is.numeric, logical(1))
if (!any(numeric_traits)) stop("at least one numeric trait is required")
trait_matrix <- as.matrix(trait_data[, numeric_traits, drop = FALSE])
cor_method <- if (cor_type == "bicor") "bicor" else "pearson"
module_trait_cor <- if (cor_method == "bicor") bicor(MEs, trait_matrix, use = "pairwise.complete.obs") else cor(MEs, trait_matrix, use = "pairwise.complete.obs")
module_trait_p <- corPvalueStudent(module_trait_cor, nSamples = nrow(datExpr))
kme <- signedKME(datExpr, MEs, outputColumnName = "kME", corFnc = if (cor_type == "bicor") "bicor" else "cor")
gene_trait_cor <- if (cor_type == "bicor") {
  bicor(datExpr, trait_matrix, use = "pairwise.complete.obs")
} else {
  cor(datExpr, trait_matrix, use = "pairwise.complete.obs")
}

write.table(data.frame(feature_id = colnames(datExpr), module = colors, kme, check.names = FALSE),
  file.path(args$`output-dir`, "module_membership.tsv"), sep = "\t", quote = FALSE, row.names = FALSE)
write.table(data.frame(sample_id = rownames(MEs), MEs, check.names = FALSE),
  file.path(args$`output-dir`, "module_eigengenes.tsv"), sep = "\t", quote = FALSE, row.names = FALSE)
cor_long <- do.call(rbind, lapply(seq_len(nrow(module_trait_cor)), function(i)
  data.frame(module = rownames(module_trait_cor)[i], trait = colnames(module_trait_cor),
    correlation = module_trait_cor[i, ], p_value = module_trait_p[i, ])))
cor_long$p_adjust_bh <- p.adjust(cor_long$p_value, method = "BH")
write.table(cor_long, file.path(args$`output-dir`, "module_trait_associations.tsv"), sep = "\t", quote = FALSE, row.names = FALSE)
write.table(fit, file.path(args$`output-dir`, "soft_threshold_diagnostics.tsv"), sep = "\t", quote = FALSE, row.names = FALSE)

for (ext in c("pdf", "svg")) {
  device <- function(path, width, height) {
    if (ext == "pdf") pdf(path, width = width, height = height, family = "Helvetica", pointsize = 7, useDingbats = FALSE)
    else svg(path, width = width, height = height, family = "Arial", pointsize = 7)
  }
  device(file.path(args$`output-dir`, paste0("soft_threshold_diagnostics.", ext)), 7.2047, 3.5)
  par(mfrow = c(1, 2), mar = c(3.2, 3.2, 1, 0.5), mgp = c(1.8, 0.45, 0), cex = 0.75, lwd = 0.5)
  plot(fit$Power, fit$Signed.SFT.R.sq, xlab = "Soft-threshold power", ylab = "Signed scale-free fit, R2", type = "n")
  text(fit$Power, fit$Signed.SFT.R.sq, labels = fit$Power, cex = 0.7); abline(h = 0.85, col = "#D55E00", lty = 2)
  plot(fit$Power, fit$mean.k., xlab = "Soft-threshold power", ylab = "Mean connectivity", type = "b", pch = 16, cex = 0.6)
  dev.off()
  device(file.path(args$`output-dir`, paste0("sample_dendrogram_and_traits.", ext)), 7.2047, 4.2)
  sample_tree <- hclust(dist(datExpr), method = "average")
  trait_colors <- numbers2colors(trait_matrix, signed = TRUE)
  plotDendroAndColors(sample_tree, trait_colors, groupLabels = colnames(trait_matrix),
    main = "Sample clustering and declared traits", dendroLabels = FALSE, hang = 0.03)
  dev.off()
  device(file.path(args$`output-dir`, paste0("gene_dendrogram_module_colors.", ext)), 7.2047, 4.2)
  plotDendroAndColors(modules$dendrograms[[1]], colors[modules$blockGenes[[1]]], "Module", dendroLabels = FALSE, hang = 0.03)
  dev.off()
  device(file.path(args$`output-dir`, paste0("module_size_distribution.", ext)), 3.5039, 3.2)
  sizes <- sort(table(colors), decreasing = TRUE)
  barplot(sizes, col = names(sizes), las = 2, ylab = "Feature count", border = NA)
  dev.off()
  device(file.path(args$`output-dir`, paste0("module_trait_heatmap.", ext)), 7.2047, 4.2)
  text_matrix <- paste0(sprintf("%.2f", module_trait_cor), "\n(", format(module_trait_p, digits = 1), ")")
  dim(text_matrix) <- dim(module_trait_cor)
  labeledHeatmap(Matrix = module_trait_cor, xLabels = colnames(module_trait_cor), yLabels = rownames(module_trait_cor),
    ySymbols = rownames(module_trait_cor), colorLabels = FALSE, colors = blueWhiteRed(50), textMatrix = text_matrix,
    setStdMargins = FALSE, cex.text = 0.55, zlim = c(-1, 1), main = "Module-trait correlation (p)")
  dev.off()
  device(file.path(args$`output-dir`, paste0("eigengene_network.", ext)), 7.2047, 4.2)
  plotEigengeneNetworks(MEs, setLabels = "all", marDendro = c(0, 4, 2, 0), marHeatmap = c(3, 4, 2, 2),
    plotDendrograms = TRUE, xLabelsAngle = 45)
  dev.off()
  target_trait <- colnames(module_trait_cor)[which.max(apply(abs(module_trait_cor), 2, max, na.rm = TRUE))]
  target_module_row <- rownames(module_trait_cor)[which.max(abs(module_trait_cor[, target_trait]))]
  target_color <- sub("^ME", "", target_module_row)
  target_features <- colors == target_color
  target_kme_column <- paste0("kME", target_color)
  device(file.path(args$`output-dir`, paste0("module_membership_gene_significance.", ext)), 3.5039, 3.2)
  plot(abs(kme[target_features, target_kme_column]), abs(gene_trait_cor[target_features, target_trait]),
    pch = 16, cex = 0.55, col = target_color, xlab = paste0("|Module membership|, ", target_color),
    ylab = paste0("|Gene significance|, ", target_trait))
  dev.off()
}

file_sha <- function(path) digest(file = path, algo = "sha256", serialize = FALSE)
report <- list(
  schema_version = 1, passed = TRUE, samples = nrow(datExpr), features = ncol(datExpr),
  parameters = list(network_type = network_type, cor_type = cor_type, powers = powers, selected_power = power,
    power_rule = power_rule, deep_split = as.integer(args$`deep-split`), min_module_size = as.integer(args$`min-module-size`),
    merge_cut_height = as.numeric(args$`merge-cut-height`), seed = as.integer(args$seed), threads = threads),
  module_count_excluding_grey = length(setdiff(unique(colors), "grey")),
  figures = c("sample_dendrogram_and_traits", "soft_threshold_diagnostics", "gene_dendrogram_module_colors",
    "module_size_distribution", "module_trait_heatmap", "eigengene_network", "module_membership_gene_significance"),
  versions = list(R = as.character(getRversion()), WGCNA = as.character(packageVersion("WGCNA"))),
  inputs = list(expression_sha256 = file_sha(args$expression), traits_sha256 = file_sha(args$traits)),
  plot_standard_version = "1.1.0",
  quality_gates = list(ordered_sample_identity = TRUE, good_samples_genes = TRUE, soft_threshold_criterion_recorded = TRUE,
    module_trait_multiplicity_reported = TRUE, deterministic_seed = TRUE),
  limitations = c("Module membership is coexpression evidence, not physical interaction or causality.",
    "Consequential module or hub claims require resampling, consensus, or independent-cohort stability analysis.")
)
write(toJSON(report, auto_unbox = TRUE, pretty = TRUE, digits = NA), file.path(args$`output-dir`, "wgcna_report.json"))
cat(toJSON(list(passed = TRUE, samples = nrow(datExpr), modules = report$module_count_excluding_grey), auto_unbox = TRUE), "\n")
