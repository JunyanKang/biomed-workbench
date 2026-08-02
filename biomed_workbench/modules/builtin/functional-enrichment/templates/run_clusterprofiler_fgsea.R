#!/usr/bin/env Rscript
# Explicit GO/KEGG ORA or preranked GSEA using clusterProfiler/fgsea semantics.

suppressPackageStartupMessages({
  library(clusterProfiler)
  library(enrichplot)
  library(fgsea)
  library(AnnotationDbi)
  library(jsonlite)
  library(digest)
  library(ggplot2)
})

parse_args <- function(x) {
  if (length(x) %% 2 != 0 || any(!startsWith(x[seq(1, length(x), 2)], "--"))) stop("arguments must be --key value pairs")
  structure(as.list(x[seq(2, length(x), 2)]), names = sub("^--", "", x[seq(1, length(x), 2)]))
}
num <- function(key, default) if (key %in% names(args)) as.numeric(args[[key]]) else default
args <- parse_args(commandArgs(trailingOnly = TRUE))
required <- c("mode", "organism", "key-type", "output-dir")
if (!all(required %in% names(args))) stop("mode, organism, key-type, and output-dir are required")
if (!(args$mode %in% c("go-ora", "kegg-ora", "go-gsea", "kegg-gsea"))) stop("unsupported mode")
is_ora <- endsWith(args$mode, "-ora")
needed <- if (is_ora) c("genes", "universe") else c("ranking")
if (!all(needed %in% names(args)) || any(!file.exists(unlist(args[needed])))) stop("mode-specific input is missing")
if (dir.exists(args$`output-dir`) && length(list.files(args$`output-dir`, all.files = TRUE, no.. = TRUE))) stop("output directory is not empty")
dir.create(args$`output-dir`, recursive = TRUE, showWarnings = FALSE)

min_size <- as.integer(num("min-size", if (is_ora) 10 else 15))
max_size <- as.integer(num("max-size", 500))
p_cutoff <- num("p-cutoff", 0.05)
q_cutoff <- num("q-cutoff", 0.2)
if (min_size < 1 || max_size < min_size || p_cutoff <= 0 || p_cutoff > 1 || q_cutoff <= 0 || q_cutoff > 1) stop("invalid thresholds")

orgdb <- NULL
if (startsWith(args$mode, "go-")) {
  if (!("orgdb" %in% names(args))) stop("GO modes require --orgdb")
  suppressPackageStartupMessages(library(args$orgdb, character.only = TRUE))
  orgdb <- get(args$orgdb, envir = asNamespace(args$orgdb))
}

if (is_ora) {
  genes <- read.delim(args$genes, stringsAsFactors = FALSE)
  universe <- read.delim(args$universe, stringsAsFactors = FALSE)
  if (!identical(names(genes), "gene_id") || !identical(names(universe), "gene_id")) stop("ORA files require one gene_id column")
  genes$gene_id <- as.character(genes$gene_id)
  universe$gene_id <- as.character(universe$gene_id)
  genes <- unique(genes$gene_id[nzchar(genes$gene_id)])
  universe <- unique(universe$gene_id[nzchar(universe$gene_id)])
  if (!length(genes) || !all(genes %in% universe)) stop("query genes must be a nonempty subset of universe")
  if (args$mode == "go-ora") {
    ontology <- if ("ontology" %in% names(args)) args$ontology else "ALL"
    result <- enrichGO(gene = genes, universe = universe, OrgDb = orgdb, keyType = args$`key-type`,
      ont = ontology, pvalueCutoff = p_cutoff, pAdjustMethod = "BH", qvalueCutoff = q_cutoff,
      minGSSize = min_size, maxGSSize = max_size, readable = FALSE, pool = identical(ontology, "ALL"))
  } else {
    result <- enrichKEGG(gene = genes, universe = universe, organism = args$organism, keyType = args$`key-type`,
      pvalueCutoff = p_cutoff, pAdjustMethod = "BH", qvalueCutoff = q_cutoff,
      minGSSize = min_size, maxGSSize = max_size, use_internal_data = FALSE)
  }
} else {
  ranking <- read.delim(args$ranking, stringsAsFactors = FALSE)
  ranking$gene_id <- as.character(ranking$gene_id)
  if (!identical(names(ranking), c("gene_id", "stat")) || anyDuplicated(ranking$gene_id) ||
      any(!nzchar(ranking$gene_id)) || any(!is.finite(ranking$stat))) stop("ranking requires unique gene_id and finite stat")
  if (anyDuplicated(ranking$stat)) warning("ranking contains tied statistics; the upstream deterministic tie policy must be reported")
  stats <- ranking$stat
  names(stats) <- ranking$gene_id
  stats <- sort(stats, decreasing = TRUE)
  seed <- if ("seed" %in% names(args)) as.integer(args$seed) else 1L
  set.seed(seed)
  exponent <- num("exponent", 1)
  eps <- num("eps", 1e-10)
  if (args$mode == "go-gsea") {
    ontology <- if ("ontology" %in% names(args)) args$ontology else "ALL"
    result <- gseGO(geneList = stats, OrgDb = orgdb, keyType = args$`key-type`, ont = ontology,
      exponent = exponent, minGSSize = min_size, maxGSSize = max_size, eps = eps,
      pvalueCutoff = p_cutoff, pAdjustMethod = "BH", verbose = FALSE, seed = TRUE, by = "fgsea")
  } else {
    result <- gseKEGG(geneList = stats, organism = args$organism, keyType = args$`key-type`,
      exponent = exponent, minGSSize = min_size, maxGSSize = max_size, eps = eps,
      pvalueCutoff = p_cutoff, pAdjustMethod = "BH", verbose = FALSE, seed = TRUE, by = "fgsea")
  }
}

table <- as.data.frame(result)
result_path <- file.path(args$`output-dir`, "enrichment_results.tsv")
write.table(table, result_path, sep = "\t", quote = FALSE, row.names = FALSE)
theme_pub <- theme_classic(base_family = "Arial", base_size = 7) +
  theme(axis.line = element_line(linewidth = 0.5), axis.ticks = element_line(linewidth = 0.5),
    legend.position = "right", plot.margin = margin(2, 2, 2, 2, "mm"))
save_plot <- function(plot, stem, width = 183 / 25.4, height = 90 / 25.4) {
  ggsave(file.path(args$`output-dir`, paste0(stem, ".pdf")), plot + theme_pub, width = width, height = height, units = "in", device = cairo_pdf)
  ggsave(file.path(args$`output-dir`, paste0(stem, ".svg")), plot + theme_pub, width = width, height = height, units = "in")
}
figures <- character()
if (nrow(table)) {
  show_n <- min(20, nrow(table))
  if (is_ora) {
    save_plot(dotplot(result, showCategory = show_n), "enrichment_dotplot")
    save_plot(barplot(result, showCategory = show_n), "enrichment_barplot")
    figures <- c("enrichment_dotplot", "enrichment_barplot")
  } else {
    save_plot(dotplot(result, showCategory = show_n), "nes_dotplot")
    top_id <- table$ID[which.min(table$p.adjust)]
    save_plot(gseaplot2(result, geneSetID = top_id, pvalue_table = TRUE), "gsea_top_pathway")
    top_table <- head(table[order(table$p.adjust, -abs(table$NES)), , drop = FALSE], 10)
    leading <- do.call(rbind, lapply(seq_len(nrow(top_table)), function(i) {
      genes <- head(strsplit(as.character(top_table$core_enrichment[i]), "/", fixed = TRUE)[[1]], 50)
      data.frame(pathway = top_table$Description[i], gene_id = genes, stat = unname(stats[genes]), stringsAsFactors = FALSE)
    }))
    leading$pathway <- factor(leading$pathway, levels = rev(unique(top_table$Description)))
    leading_plot <- ggplot(leading, aes(gene_id, pathway, fill = stat)) +
      geom_tile() + scale_fill_gradient2(low = "#3B4CC0", mid = "#F7F7F7", high = "#B40426", midpoint = 0) +
      labs(x = "Leading-edge gene", y = NULL, fill = "Rank stat") +
      theme(axis.text.x = element_text(angle = 60, hjust = 1))
    save_plot(leading_plot, "leading_edge_heatmap", height = 120 / 25.4)
    figures <- c("nes_dotplot", "gsea_top_pathway", "leading_edge_heatmap")
  }
}

file_sha <- function(path) digest(file = path, algo = "sha256", serialize = FALSE)
report <- list(
  schema_version = 1, passed = TRUE, mode = args$mode, organism = args$organism,
  key_type = args$`key-type`, orgdb = if (is.null(orgdb)) NULL else args$orgdb,
  ontology = if ("ontology" %in% names(args)) args$ontology else NULL,
  min_size = min_size, max_size = max_size, p_cutoff = p_cutoff, q_cutoff = if (is_ora) q_cutoff else NULL,
  result_count = nrow(table), result_sha256 = file_sha(result_path), figures = figures,
  versions = list(R = as.character(getRversion()), clusterProfiler = as.character(packageVersion("clusterProfiler")),
    enrichplot = as.character(packageVersion("enrichplot")), fgsea = as.character(packageVersion("fgsea"))),
  plot_standard_version = "1.1.0",
  quality_gates = list(explicit_ora_universe = is_ora, complete_ranked_vector = !is_ora,
    identifier_namespace_declared = TRUE, database_identity_declared = TRUE, results_reloaded = TRUE),
  limitations = c("Empty results are valid and are not replaced by relaxed thresholds.", "Enrichment is association-level evidence and does not establish causality.")
)
write(toJSON(report, auto_unbox = TRUE, pretty = TRUE, digits = NA, null = "null"), file.path(args$`output-dir`, "enrichment_report.json"))
cat(toJSON(list(passed = TRUE, mode = args$mode, terms = nrow(table)), auto_unbox = TRUE), "\n")
