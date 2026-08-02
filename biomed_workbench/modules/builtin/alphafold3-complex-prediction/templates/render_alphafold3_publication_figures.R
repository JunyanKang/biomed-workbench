#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(ggplot2)
  library(patchwork)
  library(scales)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 4L) {
  stop("usage: render_alphafold3_publication_figures.R REPORT_DIR JOB_LABEL CHAIN_A_LABEL CHAIN_B_LABEL")
}

report_dir <- normalizePath(args[[1]], mustWork = TRUE)
job_label <- args[[2]]
chain_labels <- c(A = args[[3]], B = args[[4]])
chain_colors <- c(A = "#2C7FB8", B = "#D95F59")
neutral <- "#B9C2C9"
signal <- "#2C7FB8"
accent <- "#D95F59"

read_table <- function(name) {
  read.delim(file.path(report_dir, name), check.names = FALSE, stringsAsFactors = FALSE)
}

save_triplet <- function(plot, stem, width_mm, height_mm, dpi = 600) {
  width_in <- width_mm / 25.4
  height_in <- height_mm / 25.4
  svglite::svglite(file.path(report_dir, paste0(stem, ".svg")), width = width_in, height = height_in)
  print(plot)
  dev.off()
  grDevices::cairo_pdf(file.path(report_dir, paste0(stem, ".pdf")), width = width_in, height = height_in, family = "Arial")
  print(plot)
  dev.off()
  ragg::agg_png(file.path(report_dir, paste0(stem, ".png")), width = width_in, height = height_in, units = "in", res = dpi, background = "white")
  print(plot)
  dev.off()
}

theme_set(
  theme_classic(base_size = 6.5, base_family = "Arial") +
    theme(
      axis.line = element_line(linewidth = 0.35, colour = "black"),
      axis.ticks = element_line(linewidth = 0.35, colour = "black"),
      legend.title = element_text(size = 6.2),
      legend.text = element_text(size = 5.8),
      plot.title = element_text(size = 7, face = "bold"),
      plot.subtitle = element_text(size = 6.2, colour = "#4A4A4A"),
      strip.text = element_text(size = 6.2, face = "bold"),
      panel.grid = element_blank()
    )
)

ranking <- read_table("ranking_scores.tsv")
ranking$model_label <- paste0("model ", ranking$model_index)
ranking$is_top <- ranking$ranking_score == max(ranking$ranking_score)
p_rank <- ggplot(ranking, aes(x = reorder(model_label, -ranking_score), y = ranking_score, fill = is_top)) +
  geom_col(width = 0.68) +
  scale_fill_manual(values = c(`FALSE` = neutral, `TRUE` = signal), guide = "none") +
  coord_cartesian(ylim = c(0, max(0.5, max(ranking$ranking_score) * 1.12))) +
  labs(x = NULL, y = "Ranking score", title = "Model ranking") +
  theme(axis.text.x = element_text(angle = 35, hjust = 1))

summary <- read_table("top_model_summary.tsv")
summary$metric <- factor(summary$metric, levels = c("ranking_score", "ptm", "iptm", "fraction_disordered"), labels = c("ranking", "pTM", "ipTM", "disordered"))
p_metric <- ggplot(summary, aes(x = metric, y = value, fill = metric)) +
  geom_col(width = 0.64) +
  geom_hline(yintercept = 0.8, linewidth = 0.35, linetype = 2, colour = "#6F6F6F") +
  scale_fill_manual(values = c(ranking = signal, pTM = "#6BAED6", ipTM = accent, disordered = "#B39DDB"), guide = "none") +
  scale_y_continuous(limits = c(0, 1), expand = expansion(mult = c(0, 0.03))) +
  labs(x = NULL, y = "Score / fraction", title = "Top-model confidence") +
  theme(axis.text.x = element_text(angle = 25, hjust = 1))

pae <- read_table("pae_binned.tsv")
p_pae <- ggplot(pae, aes(x = column_bin, y = row_bin, fill = mean_pae)) +
  geom_raster() +
  scale_y_reverse(expand = c(0, 0)) +
  scale_fill_gradientn(colours = c("#17324D", "#3F8EAA", "#F2E8CF", "#D97757"), limits = c(0, max(30, max(pae$mean_pae))), oob = squish, name = "Mean PAE\n(Å)") +
  coord_equal(expand = FALSE) +
  labs(x = "Predicted token bins", y = "Scored token bins", title = "Predicted aligned error") +
  theme(legend.position = "right")

pairs <- read_table("chain_pair_confidence.tsv")
pairs$source_label <- ifelse(pairs$source_chain %in% names(chain_labels), chain_labels[pairs$source_chain], pairs$source_chain)
pairs$target_label <- ifelse(pairs$target_chain %in% names(chain_labels), chain_labels[pairs$target_chain], pairs$target_chain)
p_pair <- ggplot(pairs, aes(x = target_label, y = source_label, fill = chain_pair_iptm)) +
  geom_tile(colour = "white", linewidth = 0.4) +
  geom_text(aes(label = sprintf("%.2f", chain_pair_iptm)), size = 2.0, family = "Arial") +
  scale_fill_gradient(low = "#F1F4F6", high = signal, limits = c(0, 1), name = "ipTM") +
  coord_equal() +
  labs(x = NULL, y = NULL, title = "Chain-pair confidence") +
  theme(axis.text.x = element_text(angle = 25, hjust = 1), axis.line = element_blank(), axis.ticks = element_blank())

chains <- read_table("chain_confidence.tsv")
chains$chain_label <- ifelse(chains$chain_id %in% names(chain_labels), chain_labels[chains$chain_id], chains$chain_id)
chain_long <- rbind(
  data.frame(chain_label = chains$chain_label, metric = "chain pTM", value = chains$chain_ptm),
  data.frame(chain_label = chains$chain_label, metric = "chain ipTM", value = chains$chain_iptm)
)
p_chain <- ggplot(chain_long, aes(x = chain_label, y = value, fill = metric)) +
  geom_col(position = position_dodge(width = 0.72), width = 0.64) +
  scale_fill_manual(values = c(`chain pTM` = signal, `chain ipTM` = accent), name = NULL) +
  scale_y_continuous(limits = c(0, 1), expand = expansion(mult = c(0, 0.03))) +
  labs(x = NULL, y = "Confidence", title = "Per-chain confidence") +
  theme(axis.text.x = element_text(angle = 25, hjust = 1), legend.position = c(0.5, 0.96), legend.direction = "horizontal")

residue <- read_table("residue_confidence.tsv")
residue$chain_label <- ifelse(residue$chain_id %in% names(chain_labels), chain_labels[residue$chain_id], residue$chain_id)
p_residue <- ggplot(residue, aes(x = residue_number, y = mean_plddt, colour = chain_label)) +
  geom_line(linewidth = 0.36, alpha = 0.9) +
  geom_hline(yintercept = 70, linewidth = 0.35, linetype = 2, colour = "#6F6F6F") +
  facet_wrap(~chain_label, scales = "free_x", ncol = 1) +
  scale_colour_manual(values = setNames(unname(chain_colors[seq_along(unique(residue$chain_id))]), unique(residue$chain_label)), guide = "none") +
  scale_y_continuous(limits = c(0, 100), breaks = c(0, 50, 70, 90)) +
  labs(x = "Residue", y = "Mean pLDDT", title = "Residue-level confidence") +
  theme(strip.background = element_blank(), strip.text = element_text(hjust = 0))

confidence_figure <- ((p_rank | p_metric | p_pair) / (p_pae | p_residue | p_chain)) +
  plot_layout(widths = c(1, 1, 1), heights = c(0.9, 1.2), guides = "collect") +
  plot_annotation(
    title = job_label,
    subtitle = "AlphaFold Server prediction audit; scores describe model confidence, not experimental interaction evidence",
    tag_levels = "a",
    theme = theme(plot.title = element_text(size = 8.2, face = "bold"), plot.subtitle = element_text(size = 6.4), plot.tag = element_text(size = 8, face = "bold"))
  ) & theme(legend.position = "right")
save_triplet(confidence_figure, "alphafold3_confidence_overview", 183, 135)

coordinates <- read_table("structure_coordinates.tsv")
trace <- coordinates[coordinates$atom_name == "CA", ]
if (nrow(trace) < 4L) {
  trace <- coordinates
}
trace$chain_label <- ifelse(trace$chain_id %in% names(chain_labels), chain_labels[trace$chain_id], trace$chain_id)
color_values <- setNames(unname(chain_colors[match(unique(trace$chain_id), names(chain_colors))]), unique(trace$chain_label))
color_values[is.na(color_values)] <- "#7A7A7A"
projection <- function(x_name, y_name, title) {
  ggplot(trace, aes(x = .data[[x_name]], y = .data[[y_name]], colour = chain_label, group = chain_label)) +
    geom_path(linewidth = 0.42, alpha = 0.86) +
    geom_point(size = 0.18, alpha = 0.35) +
    coord_equal() +
    scale_colour_manual(values = color_values, name = NULL) +
    labs(x = NULL, y = NULL, title = title) +
    theme_void(base_size = 6.5, base_family = "Arial") +
    theme(plot.title = element_text(size = 7, face = "bold"), legend.position = "bottom")
}
p_xy <- projection("x", "y", "Orthogonal view 1")
p_xz <- projection("x", "z", "Orthogonal view 2")
structure_figure <- (p_xy | p_xz) +
  plot_layout(guides = "collect") +
  plot_annotation(
    title = paste0(job_label, " — top-ranked model"),
    subtitle = "Cα backbone projections; chain placement should be interpreted together with ipTM and cross-chain PAE",
    tag_levels = "a",
    theme = theme(plot.title = element_text(size = 8.2, face = "bold"), plot.subtitle = element_text(size = 6.4), plot.tag = element_text(size = 8, face = "bold"))
  ) & theme(legend.position = "bottom")
save_triplet(structure_figure, "alphafold3_structure_overview", 183, 82)

cat(jsonlite::toJSON(list(
  figures = c(
    "alphafold3_confidence_overview.pdf", "alphafold3_confidence_overview.svg", "alphafold3_confidence_overview.png",
    "alphafold3_structure_overview.pdf", "alphafold3_structure_overview.svg", "alphafold3_structure_overview.png"
  ),
  backend = "R",
  style_version = "biomed-workbench-structure-v2"
), auto_unbox = TRUE))
