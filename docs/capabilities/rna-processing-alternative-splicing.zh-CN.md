# RNA 加工与可变剪接分析

语言：[中文](rna-processing-alternative-splicing.zh-CN.md) · [English](rna-processing-alternative-splicing.md)

RNA 加工不是单一统计问题。剪接事件、外显子使用、转录本使用、完整异构体、3′ 单细胞 junction 信号和 spliced/unspliced 动力学观察的是不同对象。工作台先确定数据能回答哪一个问题，再选择一个主分析和一个能够改变科研判断的正交验证。

## 如何选择分析路径

| 数据与问题 | 默认主分析 | 适合解决的问题 | 不应被替代的边界 |
| --- | --- | --- | --- |
| 有生物学重复的短读长 bulk RNA-seq；经典局部事件 | [rMATS-turbo](https://github.com/Xinglab/rmats-turbo) | SE、A5SS、A3SS、MXE、RI 的样本间变化，输出事件计数、PSI、ΔPSI、P 值和 FDR | 一个局部事件不等于完整异构体发生切换 |
| 新 junction、注释不完整或复杂局部剪接 | [MAJIQ/VOILA](https://majiq.biociphers.org/) 或 [LeafCutter](https://github.com/davidaknowles/leafcutter) | 复杂局部剪接图、未注释 junction、intron excision cluster | 只有在研究问题需要新事件或复杂事件时才替代 rMATS；不会为了增加方法数量而同时运行 |
| 转录本相对使用变化 | Salmon/tximport → [DRIMSeq](https://bioconductor.org/packages/release/bioc/html/DRIMSeq.html) → [stageR](https://bioconductor.org/packages/release/bioc/html/stageR.html) | 先在基因层面筛查，再定位发生使用变化的转录本；可纳入 batch 等设计变量 | DTU 不是差异基因表达，也不是天然等同于一个经典剪接事件 |
| 外显子使用变化 | [DEXSeq](https://bioconductor.org/packages/release/bioc/html/DEXSeq.html) | 找到相对于同一基因其他 counting bins 发生变化的外显子区域 | 需要 junction 或转录本证据后才能写成具体剪接机制 |
| 全长单细胞数据 | [BRIE2](https://brie.readthedocs.io/en/latest/quick_start.html)、SpliZ 或 scQuint | 在保留样本结构的前提下估计细胞状态相关的事件或 splice-site usage | 细胞不是条件比较的生物学重复；细胞级关联不能取代供体或样本级推断 |
| 10x 3′ 单细胞/单核数据 | 样本级 junction 候选筛查 | 判断现有 BAM 是否有可重复 junction 证据，形成 bulk RNA-seq 或 RT-PCR 候选 | 3′ 偏倚、核内 pre-mRNA 和稀疏覆盖限制正式差异剪接结论；intronic/exonic signal 与 velocity layer 均不足以建立 AS 事件 |
| Nanopore 或 PacBio 长读长 RNA | [FLAIR](https://flair.readthedocs.io/en/latest/) | 比对、splice-site 校正、共享 transcriptome collapse、逐样本定量及异构体比较 | novel isoform 仍需读段支持、重复一致性、短读长 junction 或靶向实验验证 |

## 设计和参数如何确定

在运行前会锁定生物学样本、条件、配对、批次、文库类型、链特异性、读长、参考基因组和注释版本。不同参数回答不同技术问题：

- rMATS 的 `--readLength` 来自实际文库；读长不一致时显式使用 `--variable-read-length`；链方向由 `--libType` 决定；配对设计才允许 `--paired-stats`；`--novelSS` 只在确实需要未注释 splice site 时启用；`--cstat` 定义要检验的最小剪接差异，而不是事后显著性过滤。
- DRIMSeq 的基因、转录本表达量、出现样本数和最小使用比例过滤会在看结果前确定；stageR 负责“基因筛查—转录本确认”的两阶段错误率控制。
- 3′ 单细胞/单核筛查要求每个事件在各生物学样本中达到最低 event 和 junction 计数，并检查组内 PSI 范围、状态匹配和阈值敏感性。结果始终标为候选，直到独立 bulk 或 junction-specific RT-PCR 支持。
- 长读长分析先构建跨样本共享异构体参考，再按样本定量。把每个样本分别 collapse 后直接比较会混入参考集合差异。

## 标准输出

短读长事件分析会保留 rMATS 的 JC 和 JCEC 原始表，并生成统一事件表、运行与版本报告、参数和文件指纹，以及三部分矢量概览图：

1. 各事件类型的测试数与通过预设 FDR/|ΔPSI| 门槛的数量；
2. ΔPSI 与多重校正证据的联合分布；
3. 重复单位、方向、计数口径和结论边界。

正式候选还需要基因结构或 splice graph、逐生物学样本 PSI、junction coverage、代表性 sashimi/VOILA 图和验证设计。图件会保存作图数据，坐标方向和 group 1/group 2 定义进入图注，避免只凭形状解释。

## 与其他组学怎样整合

每个剪接事件以稳定的 event ID、gene ID、坐标、方向、样本级使用率和来源文件进入科学证据地图。差异表达、RBP 结合、IP–MS、BANP 或其他染色质结合、R-loop、ATAC 和保守性证据可以连接到同一基因或事件，但各自保留独立角色：

- 结合或 IP–MS 支持“可能存在调控联系”；
- RNA 表达或染色质变化支持“同一项目中存在伴随变化”；
- splice-site 或异构体结果支持“RNA 加工表型”；
- 只有直接结合、事件特异干预、同方向功能验证和排除竞争解释后，才考虑升级为直接 RNA 加工机制。

工作台的整合表因此会把 `multi-assay candidate` 与 `direct mechanism` 分开，并默认将因果状态保留为未解决。

## 已完成的验收范围

当前封装已在本机隔离环境中真实运行 rMATS-turbo 4.4.0 的官方 skipped-exon 测试，随后由工作台执行器重新执行、重读事件表并生成统一 SVG。样本级 junction 分支和跨证据整合分支通过受控的四生物学样本案例。长读长、BRIE2、MAJIQ、LeafCutter、DEXSeq 和 DRIMSeq–stageR 已纳入方法选择、输入要求和结论边界，但尚未接入本模块的可执行分支；在各自完成参数化实现和代表性运行前，不计为可执行能力。

主要方法依据包括 rMATS 的[官方参数和输出说明](https://github.com/Xinglab/rmats-turbo/blob/master/README.md)、MAJIQ v2 的[方法论文](https://www.nature.com/articles/s41467-023-36585-y)、LeafCutter 的[Nature Genetics 论文](https://doi.org/10.1038/s41588-017-0004-9)、DEXSeq 的[Genome Research 论文](https://doi.org/10.1101/gr.133744.111)、SUPPA2 的[Genome Biology 论文](https://doi.org/10.1186/s13059-018-1417-1)、BRIE2 的[方法论文](https://pmc.ncbi.nlm.nih.gov/articles/PMC8393734/)、FLAIR 的[Nature Communications 论文](https://doi.org/10.1038/s41467-020-15171-6)及 10x Genomics 的[intronic/antisense reads 技术说明](https://www.10xgenomics.com/support/universal-three-prime-gene-expression/documentation/steps/sequencing/interpreting-intronic-and-antisense-reads-in-10-x-genomics-single-cell-gene-expression-data)。
