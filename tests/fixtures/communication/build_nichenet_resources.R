#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2L) {
  stop("expected gene list and output directory")
}
genes <- readLines(args[[1L]], warn = FALSE)
output <- args[[2L]]
dir.create(output, recursive = TRUE, showWarnings = FALSE)
ligands <- c("TGFB1", "CXCL12")
targets <- setdiff(genes, c(ligands, "TGFBR1", "TGFBR2", "CXCR4"))
if (length(targets) < 8L) {
  stop("fixture requires at least eight target genes")
}
set.seed(19L)
ligand_target_matrix <- matrix(
  runif(length(genes) * length(ligands), min = 0, max = 0.05),
  nrow = length(genes), dimnames = list(genes, ligands)
)
ligand_target_matrix[targets[1:5], "TGFB1"] <- seq(0.95, 0.75, length.out = 5L)
ligand_target_matrix[targets[4:8], "CXCL12"] <- seq(0.90, 0.70, length.out = 5L)
lr_network <- data.frame(
  from = ligands,
  to = c("TGFBR1", "CXCR4"),
  stringsAsFactors = FALSE
)
weighted_networks <- list(
  lr_sig = transform(lr_network, weight = c(1, 1)),
  gr = data.frame(from = rep(ligands, each = 5L), to = c(targets[1:5], targets[4:8]), weight = 1)
)
receiver_de <- data.frame(
  gene = targets[1:8],
  log2_fold_change = c(rep(1.5, 5L), rep(0.8, 3L)),
  adjusted_p_value = rep(0.01, 8L),
  stringsAsFactors = FALSE
)
saveRDS(ligand_target_matrix, file.path(output, "ligand_target_matrix.rds"))
saveRDS(lr_network, file.path(output, "lr_network.rds"))
saveRDS(weighted_networks, file.path(output, "weighted_networks.rds"))
write.table(receiver_de, file.path(output, "receiver_de.tsv"), sep = "\t", quote = FALSE, row.names = FALSE)
