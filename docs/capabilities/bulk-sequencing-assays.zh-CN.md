# Bulk 测序分析

Bulk、single-cell 和 spatial 描述的是数据与实验观察的尺度；它们不与“表观组学”“转录组学”构成同一层级。Biomed Workbench 采用三个相互独立的分类维度：

1. **数据尺度**：bulk、single-cell、spatial、跨尺度通用；
2. **测量家族与具体实验**：例如染色质可及性 → ATAC-seq，RNA–蛋白互作 → eCLIP；
3. **方法角色**：实验专用、可在同一测量家族复用、跨尺度统计方法或研究基础能力。

抗体、靶标、spike-in／内部参照、RNase H 处理、峰重新调用和归一化方式都是实验设计或分析策略，不是新的组学门类。例如：

`bulk → 蛋白或标记相关的染色质富集 → CUT&Tag → 靶标/抗体 S9.6 → 可选内部参照校正 → RNase H 特异性验证`

## 当前 bulk assay 家族

| 测量家族 | 实验 | 主要分析内容 | 关键设计与解释要点 |
| --- | --- | --- | --- |
| 稳态转录与表达 | bulk RNA-seq | RNA 定量、表达质控、差异表达及下游统计模块 | 表达量不是转录速率；重复单位是样本 |
| RNA 加工与异构体使用 | 短读长 bulk RNA-seq、长读长 RNA-seq | [事件级剪接、外显子使用、转录本使用、完整异构体和跨组学证据整合](rna-processing-alternative-splicing.zh-CN.md) | rMATS、DEXSeq、DRIMSeq–stageR 和 FLAIR 的统计对象不同；不能互换结论 |
| 蛋白或标记相关染色质富集 | ChIP-seq、CUT&RUN、CUT&Tag | 比对、质量控制、peak 识别、差异与注释 | assay、靶标/抗体、对照、内部参照和特异性处理分别登记 |
| RNA:DNA 杂交体与 R-loop 测量 | DRIP-seq、DRIPc-seq、sDRIP/ssDRIP-seq、qDRIP-seq、R-ChIP、MapR，以及传感器明确的 CUT&Tag | 实验专属预处理、信号识别、特异性和跨方法比较 | R-loop 是测量对象，不是 assay；S9.6 与 dRNase H1 传感器、离体/原位环境、片段化、链特异性、内部参照和 RNase H 对照分别登记 |
| 染色质可及性 | ATAC-seq、DNase-seq | 比对、质量控制、开放区域和足迹分析 | 可及性不是 TF 占位；足迹需要酶偏倚校正 |
| RNA–蛋白关联或结合位点 | RIP-seq、eCLIP、iCLIP、HITS-CLIP、PAR-CLIP、LACE-seq | 富集或结合区域识别、对照比较和注释 | RIP 支持关联转录本富集；不同 CLIP/LACE 的 UMI、交联和 RT-stop 模型不可互换 |
| 翻译 | Ribo-seq | P-site、周期性、翻译效率和 ORF 识别 | 先通过 P-site 与三核苷酸周期性质控；多个 ORF caller 的结果分别保留 |
| 新生转录 | GRO-seq、PRO-seq、TT-seq、NET-seq | 实验专属预处理、定量和动力学解释 | 链方向、run-on、脉冲标记或聚合酶位置决定不同信号模型 |
| 胞嘧啶修饰 | WGBS、RRBS、EM-seq | 转化率、覆盖、甲基化定量和区域比较 | 转化效率与覆盖是前置检查；常规亚硫酸氢盐信号通常不能区分 5mC 与 5hmC |
| 三维基因组 | Hi-C、Micro-C、Capture-C、HiChIP、PLAC-seq、ChIA-PET | 接触矩阵、质量控制、区室、结构域和互作分析 | 分辨率、背景和锚定策略随 assay 改变；接触频率不是直接结合 |
| RNA 修饰富集 | MeRIP-seq、m6A-seq | 富集区域识别、差异与功能注释 | 抗体富集是区域信号，不是单碱基位点或修饰比例 |

Ribo-seq 会先检查 P-site 和三核苷酸周期性，再分别保留 Ribo-TISH、Ribotricer 等 ORF 识别工具的结果。RiboCode 等方法可以作为敏感性分析；多个工具结果的并集不会被直接称为“真实 ORF”。

LACE-seq 从 FASTQ 开始，按照原始研究处理接头、poly(A)、pre-rRNA、链方向和多重比对，并使用匹配 IgG 对照识别结合区域。接头、质量阈值、最短读长、多重比对、区域合并和最低链特异读段数均可调整，实际软件版本和参数会随结果保存。

RIP-seq 使用明确配对的 RIP 与 input 或 IgG 对照进行区域识别，并保留分箱、链方向、多重比对处理、模型选择和显著性阈值。流程通过参数配置运行，不需要用户手工改写分析模板。

R-loop 方法之间出现不一致不应被简单求并集或投票消除。DRIP 家族、R-ChIP、MapR 和 CUT&Tag 在传感器、样本处理环境、测序对象、分辨率与偏倚上均不同；工作台将方法交集、方法特异信号和 RNase H 敏感性分别登记，并限制到对应 assay 能够支持的结论。

代表性验收覆盖 nf-core/riboseq、nf-core/nascent、nf-core/clipseq、nf-core/methylseq、nf-core/hic、ENCODE ATAC-seq、RLPipes、exomePeak2，以及 TT-seq、NET-seq、RIPSeeker 和 LACE-seq 的专属流程。每次实际分析仍需记录软件版本、参数和输入，并重新打开区间、矩阵、轨道、模型与质量报告。当前验收范围见[公共数据案例](../cases/README.zh-CN.md)和[发行说明](../releases/README.zh-CN.md)。
