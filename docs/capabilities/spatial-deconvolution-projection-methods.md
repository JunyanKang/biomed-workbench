# 空间解卷积与参考投射方法规范

更新时间：2026-07-31

本规范把三类任务分开处理：

1. **spot 混合解卷积**：估计每个捕获位置中参考定义的细胞类型比例或丰度。
2. **细胞/簇到空间的投射**：估计单细胞或细胞簇落在空间位置上的映射概率。
3. **单细胞参考图谱投射**：把新的单细胞映射到冻结的参考潜在空间并建议标签。

三者的输出不可互换。映射概率不是细胞比例，模型推断的“超分辨率细胞”也不是直接观测细胞。

## 核心方法与适用场景

| 方法 | 任务与输出 | 优先适用场景 | 关键可调参数 | 不适用或必须谨慎 |
|---|---|---|---|---|
| RCTD | spot 解卷积；参考定义的权重；`full`、`doublet` 或 `multi` 模式 | Visium 等多细胞 spot；也可对接近单细胞大小的 bead/位置使用 `doublet` 模式；需要校正平台差异的稳健基线 | `doublet_mode`、每类参考细胞上下限、UMI/基因过滤、核心数 | `doublet` 不能用于明显多细胞 spot；参考缺失的状态不会被发现；权重不是直接细胞计数 |
| cell2location | 贝叶斯丰度模型；位置×细胞类型丰度及后验区间 | 深度较高的 spot 数据、细粒度细胞类型、稀有细胞类型、多样本联合信息；需要技术效应与后验不确定性 | `N_cells_per_location`、`detection_alpha`、训练轮数、后验样本数、参考回归批次 | 需要足够计算资源；先验细胞数必须有组织学/平台依据；丰度默认不等于比例 |
| Stereoscope | 负二项计数模型；位置×细胞类型比例 | 希望获得比 cell2location 更简洁的生成模型基线；原始 UMI 计数和匹配参考可靠 | 参考/空间训练轮数、学习率、`prior_weight` | 不显式使用空间邻接；参考错配和缺失类型仍会传递到结果 |
| SPOTlight | 标记基因播种的 NMF + NNLS；组成比例 | 有经过审查的细胞类型 marker 表；希望获得可解释、相对快速的分解 | marker 及权重、`min_prop`、NMF 迭代、L1/L2 惩罚、线程 | 对 marker 质量和共线性敏感；不能边看组织结构边调 marker；不得把 residual 列并入比例归一化 |
| CARD | 空间相关约束的参考解卷积；组成比例，可生成精细化空间图 | 邻近 spot 的组成具有平滑结构；参考与空间平台存在一定错配；希望比较有/无空间先验 | 计数过滤、选定细胞类型、空间核/相关参数、imputation 网格与邻居数 | 组织边界、离散微区或孤立稀有细胞可能被过度平滑；插值位置和单细胞重建不是直接观测 |
| SpatialDWLS | marker 预筛选 + dampened weighted least squares；组成比例 | marker 清晰、计算资源有限、需要经典快速基线或与 Giotto 流程衔接 | marker 集、`n_cell`、筛选 `cutoff`、标准化方式 | 强依赖 marker 与签名矩阵；相近细胞类型共线时不稳定；空间信息主要用于候选筛选而非完整生成模型 |
| DestVI | 多分辨率解卷积；细胞类型比例 + 类型内连续状态 | 研究同一细胞类型内部的连续激活、分化或疾病状态在组织中的分布 | 细胞类型层级、潜变量维数、VampPrior、稀疏惩罚、训练轮数、技术差异先验 | GPU 更合适；假设同一 spot 中每个已声明细胞类型只有一个连续状态；不应把互斥状态粗暴合并为同一标签 |
| Tangram | 单细胞或细胞簇到位置的映射概率；可投射基因和标签 | 单细胞与空间数据来自相同组织区域并共享足够基因；目标是细胞/簇空间定位或基因投射 | cell/cluster 模式、训练基因、密度先验、正则项、训练轮数、设备 | 映射矩阵不是计数模型得到的细胞比例；单细胞模式内存开销大；参考和空间组织不匹配时容易产生强制映射 |

官方与原始方法依据：

- RCTD / spacexr：[Nature Biotechnology](https://www.nature.com/articles/s41587-021-00830-w)；[Bioconductor spacexr](https://www.bioconductor.org/packages/release/bioc/html/spacexr.html)
- cell2location：[Nature Biotechnology](https://www.nature.com/articles/s41587-021-01139-4)；[官方文档](https://cell2location.readthedocs.io/en/latest/)
- Stereoscope：[Nature Communications](https://www.nature.com/articles/s41467-020-19015-1)；[scvi-tools API](https://docs.scvi-tools.org/en/stable/api/reference/scvi.external.SpatialStereoscope.html)
- SPOTlight：[Nucleic Acids Research](https://academic.oup.com/nar/article/49/9/e50/6129676)；[Bioconductor 手册](https://bioconductor.org/packages/release/bioc/manuals/SPOTlight/man/SPOTlight.pdf)
- CARD：[Nature Biotechnology](https://www.nature.com/articles/s41587-022-01273-7)；[官方示例](https://yma-lab.github.io/CARD/documentation/04_CARD_Example.html)
- SpatialDWLS：[Genome Biology](https://genomebiology.biomedcentral.com/articles/10.1186/s13059-021-02362-7)；[Giotto API](https://giottosuite.com/reference/runDWLSDeconv.html)
- DestVI：[Nature Biotechnology](https://www.nature.com/articles/s41587-022-01272-8)；[scvi-tools 教程](https://docs.scvi-tools.org/en/stable/tutorials/notebooks/spatial/DestVI_tutorial.html)
- Tangram：[Nature Methods](https://www.nature.com/articles/s41592-021-01264-7)；[官方代码](https://github.com/broadinstitute/Tangram)

## 平台选择边界

- Visium、老版 Spatial Transcriptomics、DBiT-seq 和明显多细胞 bead：优先考虑 spot 解卷积。
- Slide-seq/Stereo-seq 等 bead 尺度方法：先用成像、UMI 和估算细胞数判断每个位置是单细胞、doublet 还是混合；不能只凭 bead 直径选择模式。
- Visium HD：先做 bin/segment 策略和每个位置的细胞数评估；不能机械沿用普通 Visium 的先验。
- Xenium、CosMx、MERFISH、seqFISH 等已经完成细胞分割的单细胞分辨率数据：默认任务是细胞注释、参考投射和空间邻域分析，不应默认再做 spot 解卷积。只有未分割区域、混合 ROI 或明确的伪 bulk 单元才进入解卷积。
- GeoMx ROI：优先考虑适配背景模型的 SpatialDecon 或经过验证的自定义 profile，而不是直接套用为 UMI spot 设计的默认参数。

## 统一验证要求

每个方法必须独立输出原生模型、标准化矩阵、参数、版本、输入摘要和可重载报告。至少检查：

1. 原始非负整数计数、基因命名空间、参考标签和生物样本身份。
2. 每个空间样本单独拟合或使用方法明确支持的多样本层级模型，禁止跨切片建立伪空间邻接。
3. 输出非负、有限、位置完整；只有比例输出才要求行和约为 1。
4. held-out gene 重建、模拟混合或独立原位标记验证。
5. 参考下采样、marker 扰动、细胞类型粒度和关键先验的敏感性分析。
6. 至少一个生成模型、一个非生成模型或一个空间先验方法作为敏感性对照；不把平均结果定义为“真值”。
7. 有独立或模拟真值时，JSD、MAE、相关和 top-type accuracy 可称为准确度；方法对方法的 JSD 只能称为一致性。
8. 条件差异回到生物样本层面，不能把 spot 或推断细胞当独立生物学重复。

## 其他可选方法

TACCO、CytoSPACE、CellTrek、SCDC、SpatialDecon 和 BayesPrism 在特定问题中有价值，但不作为所有平台的默认入口：

- TACCO 适合统一的细胞类型注释、组成映射和多种距离/先验策略；
- CytoSPACE、CellTrek 更偏向单细胞到空间位置的分配；
- SCDC 和 BayesPrism 更适合需要多参考或贝叶斯表达分解的场景；
- SpatialDecon 对 GeoMx/ROI 和背景建模尤其重要。

这些方法应在存在对应平台或研究问题时进入候选集，并接受与核心方法相同的输入、真值、分辨率和复现性门控。
