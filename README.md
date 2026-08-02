<p align="center">
  <img src="assets/biomed-workbench-mark.svg" width="104" alt="Biomed Workbench 标志">
</p>

<h1 align="center">Biomed Workbench</h1>

<p align="center"><strong>将生物医学问题编译为可执行、可审查、可演进的科学证据链</strong></p>

<p align="center">
  面向 Codex 的生物医学研究编排平台<br>
  Evidence · Analysis · Scientific Review · Publication
</p>

<p align="center">
  <a href="README.md">中文</a> · <a href="README.en.md">English</a>
</p>

<p align="center">
  <a href="https://github.com/JunyanKang/biomed-workbench/actions"><img alt="Quality" src="https://img.shields.io/github/actions/workflow/status/JunyanKang/biomed-workbench/quality.yml?branch=main&amp;label=quality"></a>
  <a href="LICENSE"><img alt="Apache-2.0 license" src="https://img.shields.io/badge/license-Apache--2.0-4388C7"></a>
  <img alt="194 scientific modules" src="https://img.shields.io/badge/scientific%20modules-194-36A58B">
  <img alt="One Codex entry" src="https://img.shields.io/badge/Codex%20entry-1-E05A47">
  <img alt="Versioned evidence maps" src="https://img.shields.io/badge/evidence%20maps-versioned-C7953E">
</p>

<p align="center">
  <img src="assets/readme/biomed-workbench-hero.png" width="100%" alt="从多源生物医学数据到证据网络和论文交付的概念图">
</p>

<p align="center"><sub>概念图：多源研究输入经科学编排、质量审查与证据追踪，形成可复核的研究交付；图中元素不代表实验观测。</sub></p>

复杂研究真正稀缺的，从来不只是某一个分析工具，而是贯穿整个项目的科学秩序：问题如何被拆解，方法为什么被选择，数据能否进入推断，结果是否经得起统计与生物学审查，以及每一项结论将把研究带向何处。

Biomed Workbench 把这种秩序带入 Codex。用户以自然语言描述研究目标，工作台据此组织证据检索、组学分析、单细胞与空间研究、分子设计、实验定量、图表与论文交付，并以显式依赖、质量门控和版本化证据地图维持项目的连续性。

它所交付的不是一串运行记录，而是一套能够回答四个问题的研究系统：

- **为什么做：** 科学依据、竞争性假设、实验单位与决策标准；
- **如何做：** 官方方法来源、输入输出契约、参数依据、适用条件与兼容组合；
- **结果意味着什么：** 技术、统计、生物学和稳健性四层评审；
- **下一步做什么：** 保留、带条件保留、重跑、换方法、补数据、调整假设或终止分支。

## 一个项目，而不是一串命令

Biomed Workbench 以统一入口理解完整研究目标，再从注册能力中选择科学上充分、范围上克制的模块集合。独立问题可以并行验证，存在数据依赖的步骤按序执行；每条分析路线及其评审结论都进入项目历史，持续为后续决策提供依据。

<p align="center">
  <img src="assets/readme/research-decision-loop.png" width="100%" alt="从科学问题、分析准入、执行和评审，到证据保留、方案修订和研究交付的闭环概念图">
</p>

<p align="center"><sub>概念图：青色路径表示通过评审后进入证据体系的结果，珊瑚色路径表示修订、补充或重新分析；所有分支都保留在项目历史中。</sub></p>

每个分析节点在执行前都需要说明方法适配性、可调参数、备选方案和证伪条件；每项产物在进入结论前都需要完成科学评审。运行成功只是计算状态，证据能支持多强的结论还取决于研究设计、数据质量和多方法稳健性。

## 科学证据地图

研究项目会随着新数据、新方法和新判断持续演进。Biomed Workbench 用两层结构保存这段演进史：

1. **项目主线图** 只呈现图组和关键数据之间的支持、削弱、冲突与依赖，让读者先看懂完整研究故事；
2. **单项证据展开图** 对每份数据或每个图组追踪前置结论、登记数据、作图数据、分析程序、排图程序、最终数据与图文件、图注、叙述来源和原始研究 DOI。

每个文件均绑定工作区内可跳转路径、媒体类型、大小和文件校验指纹；供系统核对的关系记录与阅读版地图同时生成。中英文报告只能读取一张已经通过验证的证据地图。独立版本、父版本记录和不可覆盖的历史目录共同保存科学解释的修订过程。

<p align="center">
  <img src="assets/readme/scientific-evidence-map.png" width="100%" alt="项目主线与单项文件来源追踪组成的两层科学证据地图概念图">
</p>

<p align="center"><sub>概念图：上层聚焦项目论证主线，下层追踪一份数据或一个图组的完整来源；正式关系由通过验证的项目证据地图定义。</sub></p>

详细设计：[中文](docs/scientific-evidence-map.zh-CN.md) · [English](docs/scientific-evidence-map.md)。

## 从分子到组织，从数据到论证

当前注册表包含 **194 个科学模块**，覆盖研究从知识建构到成果交付的主要层级：证据、数据库与文献用于界定已知、争议和知识缺口；数据分析连接 bulk、single-cell、spatial 与跨尺度研究；分子与结构、临床与实验、成像与可视化分别承载机制推演、实验测量和形态空间证据；论文与转化交付则把经过审查的结果组织成面向特定读者、期刊与应用场景的研究叙事。

其中，数据分析层再按数据尺度、测量家族和工具角色细分。靶标、抗体、内部参照、特异性处理和归一化属于具体实验或分析设计，不会被误列为独立的组学门类。模块注册表示相应科学契约已经建立；能够据此主张的实际能力，仍由公共数据案例中登记的后端、版本、研究设计以及重新读取的产物共同界定。

| 研究层级 | 已发布的代表性能力 |
| --- | --- |
| [证据、数据库与文献](docs/capabilities/evidence-and-literature.md) | NCBI、UniProt、Ensembl、gnomAD、HPO、GO、Reactome、Open Targets、Europe PMC、Crossref、bioRxiv、ClinicalTrials.gov、证据新鲜度、引用与主张审查 |
| [Bulk 测序与分子测量](docs/capabilities/bulk-sequencing-assays.zh-CN.md) | bulk RNA-seq；ChIP-seq、CUT&RUN、CUT&Tag；DRIP-seq/DRIPc-seq、qDRIP-seq、R-ChIP、MapR 等 R-loop 测量；ATAC-seq、DNase-seq；RIP-seq、eCLIP/iCLIP/HITS-CLIP/PAR-CLIP、LACE-seq；Ribo-seq；GRO-seq、PRO-seq、TT-seq、NET-seq；WGBS/RRBS/EM-seq；Hi-C/Micro-C；MeRIP/m6A-seq |
| [单细胞、轨迹与跨系统整合](docs/capabilities/single-cell-integration-reference-cross-species.md) | Scanpy/Seurat、scVI/scANVI、Harmony、CCA/RPCA、FastMNN、scIB、WNN、MOFA+；公共 PBMC 多组学数据验收的 MultiVI；Hydra–涡虫跨物种数据验收的 SAMap |
| [空间组学](docs/capabilities/trajectory-spatial-complete-analysis.md) | Visium 与 Xenium 数据结构；Xenium–SpatialData–Squidpy 图像/分割流程；Slide-seq 上验收的 RCTD、公共数据验收的 Tangram；PASTE 多切片对齐与三维坐标重建 |
| [跨尺度通用分析](docs/capabilities/omics-and-single-cell.md) | 文件与读段质控、差异表达和差异可及性、DEqMS、GO/KEGG、GSEA、WGCNA、NMF、motif、网络分析、JSD、统一统计审查与作图规范 |
| [分子与结构生物学](docs/capabilities/molecular-and-structural.md) | 序列、ORF、PCR、CRISPR、克隆设计、结构质量、结构比较、docking 审查、化学过滤与实验验证设计 |
| [临床与实验研究](docs/capabilities/clinical-and-experimental.md) | 队列与生存、biomarker、流式、qPCR、剂量反应、Western blot、biodistribution、xenograft、稳定性与实验定量 |
| [成像与科学可视化](docs/capabilities/imaging-and-visualization.md) | 图像 profiling、分割、共定位、追踪、组织图像配准、统一绘图规格、图组编排与视觉质量审查 |
| [论文与转化交付](docs/capabilities/publication-and-translation.md) | 54 本生命医学高水平期刊的版本化规范、期刊推荐、逐项稿件审查、图表规格、引用审计、审稿模拟、回复矩阵、修订谱系、专利准备与展示材料 |

<p align="center">
  <img src="assets/readme/multiscale-omics.png" width="100%" alt="跨尺度多组学、空间、轨迹和出版图组的概念图">
</p>

<p align="center"><sub>概念图：样本感知的多模态数据围绕组织与细胞层级被协调分析；图中分布、结构和组织形态均为示意。</sub></p>

完整能力地图：[中文](docs/capabilities/README.zh-CN.md) · [English](docs/capabilities/README.md)。

## 严谨性进入运行时

科学质量并非交付前的附加检查，而是模块契约的一部分。

- **实验单位优先：** 条件推断回到 donor、sample、animal、organoid 或独立制备样本；单个细胞不被提升为生物学重复。
- **原始证据保全：** 单细胞与多组学整合保留原始计数；差异推断在与设计匹配的统计层级完成。
- **参数有据可查：** 默认值只是候选值，关键参数需要结合数据特征、官方 API、方法论文和敏感性结果作出选择。
- **质量门控驱动交付：** 只有满足预先声明的输入、执行、统计与生物学标准，结果才会进入正式结论和下游分析。
- **完整研究轨迹：** 支持、削弱、冲突与待验证结果均进入事件账本，保证每次方法调整都有可复核的科学依据。
- **产物可重验：** 实际软件版本、随机种子、参数、代码和文件校验指纹随结果登记，序列化对象在交付前重新读取。
- **图与文字同源：** 图中各部分、图注、结果段落和 DOI 从同一张证据地图派生，降低不同交付物之间的叙述漂移。

## 在 Codex 中开始研究

安装后，直接描述项目目标。用户无需记忆模块名称，也无需手工拼接内部 skill。

> 从原始数据和样本设计开始，建立 donor-aware 的单细胞与空间组学研究程序。比较整合、注释、解卷积、轨迹和通讯方案；每一步给出方法依据、质量门控、图组计划和进入下一步的判定标准。

> 对这批 bulk CUT&Tag 数据进行分析：靶标/抗体为 S9.6，先核实内部参照材料及加入阶段，再决定是否进行外源参照校正；把 RNase H 作为特异性验证，完成峰、差异和转录证据联动，并把每个图组登记到版本化科学证据地图。

> 对 Ribo-seq 与配对 RNA-seq 建立翻译研究流程：检查读长、P-site 和三核苷酸周期性，分别运行并比较 Ribo-TISH、Ribotricer 与适用的额外 ORF caller，保留方法分歧，再进行翻译效率和功能解释。

> 为 TP53 建立跨文献、基因、变异、通路、结构和临床试验的证据地图，区分直接证据、关联、冲突与缺口，并提出最能改变当前判断的验证实验。

工作台会先检查真实项目文件和研究设计，再编译计划、执行适用模块、审查产物并形成下一步决策。使用指南：[中文](docs/using-biomed-workbench.zh-CN.md) · [English](docs/using-biomed-workbench.md)。

## 在 Codex 或其他 Agent 中安装

把这个 GitHub 项目链接交给 Codex 或支持插件安装的 Agent，请它安装最新版 Biomed Workbench、核对统一研究入口和模块注册表，并在完成后开启一个新的研究任务加载最新能力。更新时可以用同样的自然语言要求 Agent 拉取新版本、完成发布完整性检查并重新加载。

面向不同 Agent 的支持环境、更新与验证说明：[中文](docs/installation.zh-CN.md) · [English](docs/installation.md)。

## 公共数据库访问

当前实现的公开端点都可以匿名访问；`NCBI_API_KEY` 可选用于提高 NCBI E-utilities 与 NCBI Datasets 的请求容量。Crossref 的联系邮箱、付费 Metadata Plus token、私有 cBioPortal 的 OAuth/token 和 PubChem 不提供 key 的规则均分别记录，不能用一条结论概括整个数据库。

用户可以直接要求 Agent 检查项目需要哪些数据库，并在确有必要时通过隐藏输入配置凭据。密钥不会进入聊天、项目文件、Git、报告或证据地图。完整服务清单与多种配置方式：[中文](docs/data-access-and-credentials.zh-CN.md) · [English](docs/data-access-and-credentials.md)。

## 文档索引

- 发布说明与版本验收：[中文](docs/releases/README.zh-CN.md) · [English](docs/releases/README.md)
- 科学证据地图与双语报告：[中文](docs/scientific-evidence-map.zh-CN.md) · [English](docs/scientific-evidence-map.md)
- 能力地图：[中文](docs/capabilities/README.zh-CN.md) · [English](docs/capabilities/README.md)
- Bulk 测序分类与流程：[中文](docs/capabilities/bulk-sequencing-assays.zh-CN.md) · [English](docs/capabilities/bulk-sequencing-assays.md)
- 期刊选择与稿件规范库：[中文](docs/journal-standards.zh-CN.md) · [English](docs/journal-standards.md)
- 公共数据库访问与凭据：[中文](docs/data-access-and-credentials.zh-CN.md) · [English](docs/data-access-and-credentials.md)
- 使用指南：[中文](docs/using-biomed-workbench.zh-CN.md) · [English](docs/using-biomed-workbench.md)
- 安装与更新：[中文](docs/installation.zh-CN.md) · [English](docs/installation.md)
- 可重复性：[中文](docs/reproducibility.zh-CN.md) · [English](docs/reproducibility.md)
- 公共数据验证案例：[中文](docs/cases/README.zh-CN.md) · [English](docs/cases/README.md)
- 成熟度与证据等级：[中文](docs/maturity.zh-CN.md) · [English](docs/maturity.md)
- 架构与模块扩展：[中文](docs/architecture.zh-CN.md) · [English](docs/architecture.md)
- 格式契约：[中文](docs/format-contracts.zh-CN.md) · [English](docs/format-contracts.md)
- 开发与发布：[中文](docs/development.zh-CN.md) · [English](docs/development.md)

## 研究可信度

Biomed Workbench 以证据等级约束结论强度，以项目状态保存研究语境，以版本谱系记录解释变化。探索性结果保持探索性标记；涉及临床、伦理、专利与法规的判断进入相应专业审查环节；对外发布的材料只携带复现所需且适宜公开的科学信息。

新增方法通过独立模块进入系统，并声明输入输出 artifact、工具与格式兼容性、参数空间、质量门控、验证证据和成熟度。统一入口由此保持稳定，研究能力则可以持续扩展而不牺牲可追溯性。

发布安全的兼容性证据、执行就绪审计和公共数据案例见 [`reports/`](reports/)。

许可证：[Apache-2.0](LICENSE)。
