# 样本感知的细胞通讯与分泌信号活性

语言：[中文](cell-communication.zh-CN.md) · [English](cell-communication.md)

这项能力从保留原始计数的单细胞数据出发，分别处理三类不同问题：配体–受体相容性、受体细胞状态的配体优先级，以及分泌蛋白的相对信号活性。三类结果不会被合并成一种“通讯强度”。

## CellChat

- 接收 Matrix Market、Seurat 5 RDS 或 SingleCellExperiment RDS，并明确指定细胞类型、生物学样本和条件字段。
- 每个生物学样本独立建立 CellChat 对象，固定物种数据库、最小细胞数、平均表达方法、置换次数、随机种子和 sender→receiver 范围。
- 输出逐样本 interaction 表、网络计数表、CellChat 对象，以及官方 `netVisual_circle`、`netVisual_chord_gene` 和 `netVisual_bubble` 图的 PDF/PNG。
- 可按条件建立合并对象并输出 `rankNet` 和 `netAnalysis_signalingChanges_scatter`，但这些图明确标为条件合并后的描述性比较，不替代生物学样本层面的条件检验。

当前 CellChat 2.2.0 适配器已用两份独立样本的受控数据真实运行，interaction 表、RDS 对象和官方图形均已重新打开检查，成熟度为 `EXECUTED_FIXTURE`。尚未把该状态扩大为公共生物学案例验证。

## SecAct

SecAct 使用官方 R API，不以自定义 response score 模拟其功能。

- `sample-celltype-activity` 在每个生物学样本内分别调用 `SecAct.activity.inference.scRNAseq`，输出 beta、标准误、z score、p 值和官方活性热图。
- `pooled-condition-communication-descriptive` 调用官方 `SecAct.CCC.scRNAseq`，输出分泌蛋白表达、活性和 sender–receiver 关系及官方 heatmap/circle 图。
- 条件合并模式必须显式允许，并永久标记为描述性结果，因为官方内部检验以细胞为观测，不构成生物学样本层面的条件差异证据。
- SecAct 活性是模型推断的相对活性，不等同于蛋白分泌量、受体激活或因果通讯。

当前 SecAct 1.1.0 已完成无需改源码的官方 API 适配；本机未安装该软件，本版本没有借此声称已执行，成熟度保持为 `CONTRACT_ONLY`。

## LIANA、CellPhoneDB 与 NicheNet

LIANA、直接 CellPhoneDB 和 CellChat 在每个合格生物学样本内独立运行，并保留各自的分数与显著性语义。NicheNet 只有在具备 donor-aware 的受体细胞差异分析、背景基因、sender 表达和固定版本的 ligand–target 资源时才运行。

[GSE96583 公共案例](../cases/gse96583-communication.md)验证的是 LIANA–CellPhoneDB 方法切片：16 个 donor-condition 样本分别运行，并以预先确定的独立样本支持规则汇总。它不同时验证直接 CellPhoneDB、CellChat、NicheNet 或 SecAct。

## 解释边界

表达相容性、数据库记录、CellChat 概率、NicheNet 配体优先级和 SecAct 活性属于不同证据。它们都不能单独证明物理接触、体内方向、蛋白分泌、受体激活或因果机制。正式条件结论必须回到独立生物学样本，并由能够估计条件差异的统计设计和正交 readout 支持。
