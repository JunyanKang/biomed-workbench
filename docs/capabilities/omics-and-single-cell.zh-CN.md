# 跨尺度通用与单细胞分析

语言：[中文](omics-and-single-cell.zh-CN.md) · [English](omics-and-single-cell.md)

## 科学角色

这一能力方向协调测序数据的输入与研究设计验证、统计分析、生物学解读、假设修订和发表交付。生物学重复、不可变原始测量、参考身份和实际输出检查都是一级要求。

## 研究尺度与方法分类

工作台先确定主要研究尺度：bulk、single-cell、spatial 或跨尺度通用；再分别记录测量家族、具体实验、生物学靶标、对照与归一化。它们不是一张扁平分类表。Bulk 实验覆盖见 [Bulk 测序指南](bulk-sequencing-assays.zh-CN.md)；本文聚焦通用基础与单细胞研究方案。

## 通用测序与统计方案

对于广义的测序、表达、变异、motif、NMF 或多测量请求，工作台从数据 profiling 和读段级 QC 开始，组织可复用的比对、排序、比对质量判定、变异或区间处理、次级综合和面向发表的解读。实验特异推断保留在相应实验模块中。独立分支可以并行；当下游依赖 QC、比对记录、过滤区间、peak、表达矩阵或已准入的统计结果时，必须显式声明依赖。

这使 FASTQ、BAM/CRAM、VCF、BED、count matrix、peak set、motif 资源、NMF program 和 gene-set 输出可在同一入口下管理，但不会把它们的格式或工具误当为可互换。每个模块都声明可接受产物格式、版本边界、必需元数据、可执行模板、质量门控和尚未解决的项目输入。

## 统一单细胞研究方案

对于广义单细胞或单细胞多组学问题，Biomed Workbench 不向用户展示一串互不相干的 skill。统一入口 `biomed-workbench` 将研究目标编译为分阶段计划，其中声明模块契约、输入与输出产物、兼容性行、模板、质量门控、未解决输入以及计划与实际证据之间的明确边界。

该计划按科学方案而非脚本列表组织：

1. 从原始与过滤 count 中建立 droplet 与 ambient RNA 证据。
2. 建立基础对象，验证输入格式，保留原始 count，完成 QC、归一化、HVG、PCA、邻域图、嵌入和聚类。
3. 双细胞检测与 barcode/细胞数对账。
4. 按需要开展批次整合、生成建模、配对多组学整合和单细胞 ATAC 调控准备。
5. marker 发现、参考/图谱注释、ontology 约束、置信度复核和未知状态保留。
6. 考虑 donor 的 pseudobulk、混合模型、纵向、组成与复杂实验设计推断。
7. 在样本层和方向性门控下开展通讯、轨迹、RNA velocity、拓扑、调控网络和空间证据分析。
8. 当项目包含发表工作时，连接命运映射、RegVelo 调控 velocity、假设修订与稿件/回复交付。

v1.0 单细胞核心由以下统一路由模块构成：`single-cell-atac-regulatory`、`single-cell-atlas-annotation`、`single-cell-batch-integration`、`single-cell-communication`、`single-cell-complex-inference`、`single-cell-donor-inference`、`single-cell-doublet-detection`、`single-cell-droplet-decontamination`、`single-cell-fate-mapping`、`single-cell-marker-discovery`、`single-cell-multimodal-integration`、`single-cell-qc`、`single-cell-reference-annotation`、`single-cell-regulatory-network`、`single-cell-regulatory-velocity`、`single-cell-spatial-analysis`、`single-cell-trajectory-topology` 和 `single-cell-trajectory-velocity`。

每个模块都提供 manifest 契约、可执行参数面、类型化输入输出、失败与限制边界、兼容性证据、质量门控、测试和文档入口。只有 Codex 检查用户真实产物、不修改已发布源模板地绑定输入与参数、记录实际工具和依赖版本、重新读取输出并仅准入通过质量控制的结果后，计划才会产生证据效力。

## 测序与基因组基础

- FastQC 与 fastp 读段级质量检查、MultiQC 跨样本汇总和声明参考的污染筛查。
- BWA-MEM 比对、samtools 比对质量判定、坐标排序与索引。
- 在声明源/目标 assembly 下进行与 chain 绑定的坐标 liftover，验证不可变 chain digest，并对 mapped、split 和 unmapped 记录对账；适用时再进行基因组版本匹配的 BED 区间重叠。
- 使用声明 minimap2 preset 开展 assembly-to-reference 比对，重载 FASTA/PAF 并完成记录级覆盖对账；与变异、单倍型、共线性和同源推断分开。
- BGZF/tabix VCF 处理、显式变异过滤、多样本一致性和考虑 callable territory 的肿瘤突变负荷。
- Bulk ChIP-seq、CUT&RUN 与 CUT&Tag 的 MACS3 peak calling，包含实验特异对照策略、peak 形状声明、输出重载与禁止替代 peak set；独立的已知 PWM 富集使用声明背景和 FDR 校正。
- 从严格单分辨率 `.cool` contact map 提取明确类型的 enhancer/promoter 区间，保留原始 cis count 和描述性距离分层基线，不直接调用 loop 或赋予调控关系。
- 对独立选定 GWAS 位点开展 SuSiE-RSS fine-mapping，要求预先协调的 summary statistics、精确有序且祖源兼容的 LD、固定模型复杂度、收敛检查和 credible set 重载，并明确阻断因果性过度解读。
- 使用冻结的生物学 fold 进行 group-held-out RR-BLUP 基因组预测，隔离训练与测试，并仅在已观察 held-out 性能范围内解读。
- 使用 `msprime` 在预声明单群体恒定、瓶颈或扩张情景下进行共祖模拟，保留参数、seed、tree sequence、VCF 和版本溯源；模拟与经验人口历史推断分开。
- 获取 ARCHS4 公开组织或细胞系表达背景，进行字段级 CSV 验证、层级行对账和按中位数排序，同时与项目特异差异表达或特异性主张分开。

这些步骤由 `read-quality-fastqc`、`read-quality-fastp`、`quality-report-multiqc`、`read-contamination-screen`、`dna-align-bwa-mem-single`、`alignment-quality-samtools`、`assembly-reference-alignment`、`genome-coordinate-liftover`、`interval-overlap-bedtools`、`variant-filter-vcf`、`tumor-mutation-burden-vcf`、`bulk-chromatin-peak-calling`、`sequence-motif-enrichment`、`cool-contact-evidence`、`gwas-susie-fine-mapping`、`rrblup-genomic-prediction`、`msprime-demographic-simulation` 和 `archs4-expression-evidence` 等可独立路由模块支持。相关契约见 [坐标 liftover](genome-coordinate-liftover.md)、[Bulk 染色质 peak calling](bulk-chromatin-peak-calling.md)、[已知 motif 富集](sequence-motif-enrichment.md)、[染色质接触证据](cool-contact-evidence.md)、[GWAS fine-mapping](gwas-susie-fine-mapping.md)、[基因组预测](rrblup-genomic-prediction.md)、[人口历史模拟](msprime-demographic-simulation.md)、[ARCHS4 表达背景](archs4-expression-evidence.md) 和 [UCSC 公开案例](../cases/ucsc-coordinate-liftover.md)。

## Bulk 表达与系统分析

- 表达矩阵验证和样本层质量评估。
- 使用明确设计和统计输出进行差异表达。
- gene-set overrepresentation、生物网络汇总、FDR 控制的共表达假设和稳定多起点 NMF metagene program。
- 区分探索性模式与推断性主张，并保留生物学采样单位。

代表性模块包括 `expression-qc`、`differential-expression`、`enrichment-analysis`、`network-analysis`、`ddr-coexpression-hypothesis-network` 和 `metagene-factorization-nmf`。

## 单细胞基础

- 严格按项目处理 H5AD、10x HDF5、Matrix Market 和 Seurat v5 输入。
- 在 Scanpy 或 Seurat 流程中保留原始 count，完成 QC、归一化、特征选择、scaling、降维、邻域图、聚类和稳定性复核。
- EmptyDrops、SoupX 和 CellBender 的 droplet/ambient RNA 证据，包含 barcode 对账和不可变源 count。
- 按 capture library 执行 [Scrublet 与 scDblFinder 双细胞检测](doublet-detection.md)，保留源数据、withheld-label 评估和方法不一致性。
- 透明输出逐细胞 count、检出基因数、线粒体比例和阈值标记。

核心模块为 `single-cell-foundation-workflow`、`single-cell-qc`、`single-cell-droplet-decontamination` 和 `single-cell-doublet-detection`。EmptyDrops、SoupX、CellBender 的执行与方法不一致边界见 [droplet 与 ambient RNA 指南](droplet-decontamination.md)。

## 考虑 Donor 的推断与整合

- 按生物学样本和细胞类型进行 pseudobulk 聚合，检查可估性、混杂、重复、异常值和敏感性。
- 使用独立生物学重复的项目特异 edgeR、DESeq2 或 limma-voom contrast。
- 使用 subject random effect 的纵向 dream 模型、线性与 spline 假设、方差分解、重复测量组成模型、propeller 敏感性和多参考 additive-log-ratio 证据。
- Harmony、Scanorama 和 BBKNN 与不变基线比较，在批次混合和生物学标签保留之间平衡。
- scVI/scANVI 与基线比较，并使用 held-out label、未知标签保留和模型重载检查。

对应模块为 `single-cell-donor-inference`、`single-cell-complex-inference`、`single-cell-batch-integration` 和 `single-cell-generative-modeling`。详见 [复杂推断](complex-inference.md)、[经典批次整合](batch-integration.md) 和 [经门控的 scVI/scANVI](generative-modeling.md)。

## 注释、通讯与动力学

- 基于 count 的 marker 发现，预声明 discovery/held-out 样本角色，保留分组特异检出率、效应量、独立方向验证和描述性细胞层显著性边界，不自动把 marker 转为标签。
- CellTypist、Azimuth、popV、SingleR 和 scANVI 注释，包含 feature namespace 对齐、方法特异置信度、score/pruning 复核、规范标签与 Cell Ontology 映射、跨方法加权 consensus、专家分歧和未知状态保留。
- LIANA、CellPhoneDB、CellChat 和 NicheNet 逐样本分析，保留方法原生显著性，并要求预声明的独立显著样本支持才能声称重现。
- scVelo dynamical model；RegVelo 0.4.2 GRN-informed velocity、基因分辨 latent time、调控约束比较与扰动假设；CellRank 2.3.2 的 velocity、connectivity-weight、pseudotime 和真实时间 GPCCA 命运映射；moscot optimal transport；Slingshot/Monocle3 拓扑；以及通过独立时间、root、branch 和 terminal anchor 验证的 tradeSeq lineage test。

相关模块为 `single-cell-marker-discovery`、`single-cell-atlas-annotation`、`single-cell-reference-annotation`、`single-cell-communication`、`single-cell-trajectory-velocity`、`single-cell-regulatory-velocity`、`single-cell-fate-mapping` 和 `single-cell-trajectory-topology`。详见 [marker 发现](marker-discovery.md)、[保守参考注释](reference-annotation.md)、[感知样本的通讯](cell-communication.md)、[方向验证 RNA velocity](trajectory-velocity.md)、[RegVelo](regulatory-velocity.md)、[命运映射](fate-mapping.md) 和 [lineage 拓扑](trajectory-topology.md)。

## 多模态、调控与空间分析

- RNA+ATAC 与 RNA+ADT/CITE-seq 的 WNN 整合，保留逐细胞模态权重、加权图、聚类和源 count。
- 在两种或以上配对模态上估计 MOFA+ factor、view-specific feature loading 和方差解释率。
- 从 barcode 对账 fragment 开展 MACS3 peak calling，使用序列支持的 motif matching、GC/可及性匹配 chromVAR 和 Signac peak-to-gene link。
- pySCENIC GRNBoost2、cisTarget motif pruning、regulon 构建和 AUCell activity；SCENIC+ 基因/区域 eRegulon scoring，包含显式 motif 与 region–gene 证据。
- H5AD 与 SpatialData Zarr 输入，保留图像和 shape 溯源；使用样本隔离空间图、邻域富集、逐样本 co-occurrence、全局与样本层 Moran test、重现空间基因和探索性表达—空间区域。

相关模块为 `single-cell-multimodal-integration`、`single-cell-atac-regulatory`、`single-cell-regulatory-network` 和 `single-cell-spatial-analysis`。详见 [多模态整合](multimodal-integration.md)、[单细胞 ATAC 调控](atac-regulatory.md)、[调控网络](regulatory-network.md) 和 [空间分析](spatial-analysis.md)。

## 质量门控与限制

细胞和空间 spot 不得替代独立条件层重复。当整合抹去生物学结构或泄漏标签时，结果被拒绝。注释冲突保持 unknown。通讯和空间基因主张需要样本层支持。必需 layer、anchor、先验网络溯源、基线比较或独立时间证据缺失时，时间解读被阻断。没有独立证据时，共表达、motif 支持、peak-to-gene 关联、eRegulon 一致性和空间自相关不会被报告为因果调控。

已验证模板和植入信号 fixture 证明方法可执行性、兼容性、源数据保留和科学门控行为。它们不会取代项目特异的 chemistry、组织结构、参考、基因组版本、motif 资源、实验设计、模型敏感性、生物学重复或外部验证检查。

## 典型交付物

已验证输入清单、QC 报告、考虑 donor 的统计表、整合与注释对象、敏感性分析、互作和轨迹证据、图件规格、方法、结果叙述、未解决状态日志与稿件分析包。
