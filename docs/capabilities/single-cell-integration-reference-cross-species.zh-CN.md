# 单细胞整合、参考投射与跨物种分析规范

语言：[中文](single-cell-integration-reference-cross-species.zh-CN.md) · [English](single-cell-integration-reference-cross-species.md)

更新时间：2026-07-31

本规范不把所有“整合”混成一个任务。实际分析先区分四个目标：

1. **同一模态跨批次整合**：获得用于邻域、聚类和可视化的共同表示。
2. **冻结参考图谱投射**：把 query 映射到 reference，尽量不重训或改变 reference。
3. **多模态/镶嵌整合**：整合 RNA、蛋白或 ATAC，并明确哪些细胞缺失哪些模态。
4. **跨物种整合**：比较保守状态、转移标签和同源模块，同时保留物种特异状态。

这些表示服务于邻域、注释、轨迹或可视化，不替代原始计数。差异表达、差异可及性或跨条件统计必须回到未校正的原始计数，以 sample/donor/species 为统计单位。

## 同一模态跨批次整合

| 方法 | 优先适用场景 | 关键可调参数 | 主要边界 |
|---|---|---|---|
| Seurat v5 CCA | 平台差异较明显，但预期共享细胞状态充分；需要成熟的 anchor 工作流 | `nfeatures`、`dims`、`k.anchor`、reference layers、`k.weight` | 共享状态不足时可能强制对齐；labels 不能参与无监督调参 |
| Seurat v5 RPCA | 数据较相近、规模较大、希望更保守和更快 | PCA 特征、`dims`、anchor 参数、reference layers | 对强非线性系统差异可能不足；仍须与未整合数据比较 |
| FastMNN | 批次之间存在可互相连接的共享群体；需要经典 MNN 基线 | HVG、PCA 维数、`k`、merge order、cosine normalization | merge order 和共享群体覆盖会影响结果；稀有批次特异群不能被当作批次效应 |
| Harmony | 已有 PCA/LSI，批次变量清晰，需要快速迭代 | `theta`、`lambda`、`sigma`、迭代次数、多个协变量 | 只能校正声明的协变量；不能修复完美混杂 |
| scVI/scANVI | 有原始 UMI 计数、多批次、非线性效应和较大样本；scANVI 仅在有可信部分标签时使用 | latent 维数、网络层数、dispersion、batch/covariates、epochs、seed | 标签不得泄漏到待评估 query；生成模型不等于自动正确 |
| sysVI | 跨系统、跨组织、跨物种或类器官—组织的强 system effect 候选 | system covariates、cycle weight、latent 维数、HVG、epochs、seed | 目前作为候选而非默认主流程；必须与成熟基线和多个 seed 比较 |

完整评估使用 scIB 的批次与生物保留两大类指标：batch ASW、graph connectivity、iLISI、kBET、PCR；ARI、NMI、cLISI、label ASW、isolated-label、HVG、cell-cycle 和 trajectory conservation。无法计算的指标必须给出数据驱动的 N/A 原因，不能静默删除。UMAP 外观不参与“赢家”选择。

依据：[Seurat v5 integration](https://satijalab.org/seurat/articles/seurat5_integration)；[batchelor/FastMNN](https://bioconductor.org/packages/release/bioc/html/batchelor.html)；[Harmony](https://portals.broadinstitute.org/harmony/)；[scVI](https://docs.scvi-tools.org/en/stable/user_guide/models/scvi.html)；[scANVI](https://docs.scvi-tools.org/en/stable/user_guide/models/scanvi.html)；[sysVI](https://docs.scvi-tools.org/en/1.3.3/user_guide/models/sysvi.html)；[scIB, Nature Methods](https://www.nature.com/articles/s41592-021-01336-8)。

## 冻结参考投射与标签建议

| 方法 | 优先适用场景 | 输出语义 | 关键边界 |
|---|---|---|---|
| scArches | scVI/scANVI/totalVI 等生成式参考；需要把 query 投到冻结潜在空间 | query latent、posterior、可选标签概率 | reference 模型、基因顺序和 registry 必须冻结；query 未知群必须保留 |
| Symphony | 大型参考图谱的快速、轻量、可重复 query 映射 | reference coordinates、query embedding、标签建议 | reference centroids、loadings、标准化参数和版本必须同时保存 |
| RCTD | 参考 scRNA 到空间 spot 的细胞类型权重/丰度 | 位置×细胞类型组成 | 这是空间混合解卷积，不是普通 query 单细胞标签迁移 |
| Tangram | 单细胞/簇到空间位置的映射 | cell/cluster×location 映射概率 | 映射概率不是细胞比例；组织区域不匹配会造成强制映射 |

query 标签是预测，不是事实。强制输出 maximum probability、margin/entropy、unknown/unsupported 状态及 held-out 验证；不能把 query 真值标签用于模型选择后再把同一标签称为独立验证。

依据：[scArches, Nature Biotechnology](https://www.nature.com/articles/s41587-021-01001-7)；[scArches 官方文档](https://docs.scvi-tools.org/en/stable/user_guide/models/scarches.html)；[Symphony, Nature Communications](https://www.nature.com/articles/s41467-021-25991-3)；[Symphony 官方代码](https://github.com/immunogenomics/symphony)。

## 多模态与镶嵌整合

| 方法 | 模态与设计 | 优先适用场景 | 主要边界 |
|---|---|---|---|
| WNN | 同一细胞的配对多模态 | 10x Multiome、CITE-seq 等完全配对数据的邻域融合 | 不适用于大规模未配对数据；模态权重需要逐细胞审查 |
| MOFA+ | bulk 或 single-cell 的多视图因子模型；允许缺失视图 | 发现跨模态共享/特异因子和样本层级变异 | 因子是统计表示，不自动等于机制 |
| totalVI | RNA+protein 计数 | CITE-seq，需建模蛋白背景和 batch | 蛋白 panel QC 仍需独立完成；不能把去噪蛋白作为真实观测 |
| MultiVI | RNA+ATAC，配对或含单模态细胞的 mosaic | 有配对 anchors、共享 peak universe 的 RNA–ATAC | scvi-tools ≥1.4 使用 `setup_mudata`；缺失模态必须显式保留，不能伪造 |
| GLUE | 图先验连接的配对或未配对 RNA+ATAC | 有可信 promoter/peak/gene guidance graph 的未配对整合 | 结果依赖图的 genome build、注释 release 和边定义 |

评估至少包括 modality/batch mixing、label preservation、跨模态 label transfer、配对 anchor FOSCTTM、rare-state 保留、donor 重复性，以及“在拟合前隐藏已观测模态”的 held-out reconstruction。不能用拟合后随机遮盖冒充独立重建。

依据：[totalVI, Nature Methods](https://www.nature.com/articles/s41592-020-01050-x)；[MultiVI 官方 API](https://docs.scvi-tools.org/en/stable/api/reference/scvi.model.MULTIVI.html)；[MultiVI, Nature Methods](https://www.nature.com/articles/s41592-023-01909-9)；[GLUE, Nature Biotechnology](https://www.nature.com/articles/s41587-022-01284-4)；[GLUE 官方文档](https://scglue.readthedocs.io/en/latest/)。

## 跨物种整合

跨物种分析必须先建立可审计同源基因账本，逐行保留 source/target species、gene、orthogroup、一对一/一对多/多对多关系、confidence、resource 和 release。禁止用“第一个命中基因”静默压平复杂同源关系。

| 方法 | 使用的同源信息 | 优先适用场景 | 局限与可调参数 |
|---|---|---|---|
| 一对一共享基因 + scVI/scANVI、Harmony、CCA/RPCA | 高置信、所有物种共有的一对一 orthogroup | 保守、易解释的必备基线；进化距离较近或共享基因充分 | 会丢失 paralog 和多对多信息；HVG、latent/dims、批次变量、seed 必须统一比较 |
| SAMap | 双向蛋白序列相似度 + 表达邻域 | 两个或多个进化距离较远物种；研究细胞类型进化和 paralog 替代 | 需要 NCBI BLAST 与审核后的 map；调整物种短 ID、map、邻域与迭代；相似性仍不是同源证明 |
| SATURN | 每个物种的蛋白语言模型嵌入 + 学习的 macrogenes | 多物种、同源关系复杂或一对一基因不足；有 GPU 和版本化蛋白嵌入 | 计算量大；`hv_genes`、`num_macrogenes`、pretrain/metric epochs、embedding model、batch size、seed 影响结果 |
| CAME | 细胞—基因异质图 + 一对一/一对多/多对多关系 | 成对 reference→query 标签转移、需要保留复杂基因关系和联合基因模块 | 原始流程是 pairwise；`ntop_deg`、`ntop_deg_nodes`、non-1v1 features、epochs、batch size 可调 |

标准比较至少包括：

1. 同一细胞集合上的未整合基线、一对一经典基线和至少一种专用跨物种方法。
2. leave-one-species-out 标签转移；训练物种不存在的真值标签列为 unsupported，不计作普通错误后强制重命名。
3. species mixing、label/cell-state preservation、species predictability 分开报告；不要求物种信号降为零。
4. 物种特异群在未整合与整合空间中的保留，及其独立 marker/功能证据。
5. 匹配细胞类型的保守模块一致性；模块比较和细胞标签转移不能只依赖同一套 marker。
6. 差异分析回到每个物种的原始计数，使用 sample/donor/species 层级模型或分物种分析后 meta-analysis。

依据：[SAMap 官方代码与 v3 API](https://github.com/atarashansky/SAMap)；[SAMap, eLife](https://elifesciences.org/articles/66747)；[SATURN, Nature Methods](https://www.nature.com/articles/s41592-024-02191-z)；[SATURN 官方代码](https://github.com/snap-stanford/SATURN)；[CAME 官方教程](https://xingyanliu.github.io/CAME/tut_notebooks/getting_started_pipeline_un.html)；[CAME, Genome Research](https://genome.cshlp.org/content/early/2022/12/16/gr.276868.122)；[跨物种方法 benchmark, Nature Communications](https://www.nature.com/articles/s41467-023-41855-w)。

## JSD 在单细胞和空间投射中的位置

Jensen–Shannon divergence（JSD）是两个非负、归一化分布之间的对称差异度，不是投射或解卷积算法。

- 有独立真值或拟合前保留的模拟混合时，prediction-vs-truth JSD 可以作为准确度指标，范围为 0–1，越低越好。
- RCTD-vs-cell2location、scArches-vs-Symphony 等 method-vs-method JSD 只能描述一致性，不能称为准确度。
- 必须同时按 spot/cell 和 cell type/label 两个方向报告；先核对行列身份并对每个分布归一化。
- 若真值来自同一模型、同一 marker 或拟合后的 imputation，就不构成独立验证。

## 统一准入规则

任何整合方法只有同时满足以下条件才可进入解释：

1. 输入计数、细胞、特征、样本、批次、物种、模态缺失和 reference 版本可追溯。
2. target biology 与技术批次没有完美混杂；无法被设计识别的效应不靠算法“修复”。
3. 所有候选使用相同基础细胞和预先冻结的评估集合，原生输出分别保存。
4. mixing 与 biology preservation 分开评价，不构造掩盖失败项的单一总分。
5. unknown、unsupported、rare 和 species-specific 状态完整保留。
6. 输出可重载，细胞数、顺序、feature namespace、参数、版本、seed 和 digest 一致。
7. confirmatory inference 明确回到 raw counts 与生物学重复。
