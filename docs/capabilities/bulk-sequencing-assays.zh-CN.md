# Bulk 测序分析的科学分类与执行能力

Bulk、single-cell 和 spatial 描述的是数据与实验观察的尺度；它们不与“表观组学”“转录组学”构成同一层级。Biomed Workbench 采用三个相互独立的分类维度：

1. **数据尺度**：bulk、single-cell、spatial、跨尺度通用；
2. **测量家族与具体实验**：例如染色质可及性 → ATAC-seq，RNA–蛋白互作 → eCLIP；
3. **方法角色**：实验专用、可在同一测量家族复用、跨尺度统计方法或研究基础能力。

抗体、靶标、spike-in／内部参照、RNase H 处理、峰重新调用和归一化方式都是实验设计或分析策略，不是新的组学门类。例如：

`bulk → 蛋白或标记相关的染色质富集 → CUT&Tag → 靶标/抗体 S9.6 → 可选内部参照校正 → RNase H 特异性验证`

## 当前 bulk assay 家族

| 测量家族 | 实验 | 主要执行入口 | 关键设计与解释要点 |
| --- | --- | --- | --- |
| 稳态转录与表达 | bulk RNA-seq | RNA 定量、表达质控、差异表达及下游统计模块 | 表达量不是转录速率；重复单位是样本 |
| 蛋白或标记相关染色质富集 | ChIP-seq、CUT&RUN、CUT&Tag | `bulk-chromatin-peak-calling` | assay、靶标/抗体、对照、内部参照和特异性处理分别登记 |
| RNA:DNA 杂交体与 R-loop 测量 | DRIP-seq、DRIPc-seq、sDRIP/ssDRIP-seq、qDRIP-seq、R-ChIP、MapR，以及传感器明确的 CUT&Tag | `bulk-r-loop-mapping` | R-loop 是测量对象，不是 assay；S9.6 与 dRNase H1 传感器、离体/原位环境、片段化、链特异性、内部参照和 RNase H 对照分别登记 |
| 染色质可及性 | ATAC-seq、DNase-seq | `bulk-chromatin-accessibility` | 可及性不是 TF 占位；足迹需要酶偏倚校正 |
| RNA–蛋白关联或结合位点 | RIP-seq、eCLIP、iCLIP、HITS-CLIP、PAR-CLIP、LACE-seq | `bulk-rbp-rna-binding` | RIP 支持关联转录本富集；不同 CLIP/LACE 的 UMI、交联和 RT-stop 模型不可互换 |
| 翻译 | Ribo-seq | `bulk-ribosome-profiling` | 先通过 P-site 与三核苷酸周期性质控；多个 ORF caller 的结果分别保留 |
| 新生转录 | GRO-seq、PRO-seq、TT-seq、NET-seq | `bulk-nascent-transcription` | 链方向、run-on、脉冲标记或聚合酶位置决定不同信号模型 |
| 胞嘧啶修饰 | WGBS、RRBS、EM-seq | `bulk-dna-methylation` | 转化效率与覆盖是前置门禁；常规亚硫酸氢盐信号通常不能区分 5mC 与 5hmC |
| 三维基因组 | Hi-C、Micro-C、Capture-C、HiChIP、PLAC-seq、ChIA-PET | `bulk-three-dimensional-genome` | 分辨率、背景和锚定策略随 assay 改变；接触频率不是直接结合 |
| RNA 修饰富集 | MeRIP-seq、m6A-seq | `bulk-rna-modification-enrichment` | 抗体富集是区域信号，不是单碱基位点或修饰比例 |

Ribo-seq 的默认基线来自 nf-core/riboseq：Ribo-TISH 与 Ribotricer 分别运行并保留各自 ORF 结果，riboWaltz 用于 P-site 识别。RiboCode 等额外 caller 可以作为独立敏感性分支；系统不会把多个 caller 的并集直接称为“真实 ORF”。

LACE-seq 绑定原始论文、GSE137925 元数据和公开的 `caochch/LACEseq` 提交 `b8d1193638190c50c8553847ad3a1653544dbe14`。正式入口从 FASTQ 开始，按原文顺序去除接头与 poly(A)、过滤 pre-rRNA、以 Bowtie 允许 2 个错配和最多 10 个多重比对、生成链特异读段区间，再进入匹配 IgG 对照扣除和结合簇识别。Cutadapt 1.15 与 Bowtie 1.2.3 使用固定软件镜像运行，接头、质量阈值、最短读长、多重比对、合并距离、RPM 和最低链特异读段数均可在请求中调整并进入结果来源记录。

RIP-seq 的正式区域识别入口使用 RIPSeeker 1.28.0 和 Bioconductor 3.11 的固定容器环境，读取显式配对的 RIP 与 input/IgG BAM，保留分箱、链方向、多重比对分配、HMM 模型、显著性阈值及原生 R 模型对象。它不依赖宿主机预装旧版 R 或人工改写模板。

R-loop 方法之间出现不一致不应被简单求并集或投票消除。DRIP 家族、R-ChIP、MapR 和 CUT&Tag 在传感器、样本处理环境、测序对象、分辨率与偏倚上均不同；工作台将方法交集、方法特异信号和 RNase H 敏感性分别登记，并限制到对应 assay 能够支持的结论。

公开数据端到端验收覆盖 nf-core/riboseq、nf-core/nascent、nf-core/clipseq、nf-core/methylseq、nf-core/hic、ENCODE ATAC-seq、RLPipes、exomePeak2，以及 TT-seq、NET-seq、RIPSeeker 和 LACE-seq 的实验专属执行器。每个正式入口均保存实际版本、参数、输入与输出校验值，并重新读取原生对象、区间、矩阵、轨道和质量报告。完整分类与当前验收记录由 `reports/module-scientific-taxonomy.json` 和 `reports/public-case-*.json` 生成。
