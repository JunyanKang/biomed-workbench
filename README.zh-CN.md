<p align="center">
  <img src="assets/biomed-workbench-mark.svg" width="112" alt="Biomed Workbench logo">
</p>

<h1 align="center">Biomed Workbench</h1>

<p align="center"><strong>面向 Codex 的生物医学科研助理插件：证据、分析、审查与科研交付的一体化工作台。</strong></p>

<p align="center">
  <a href="README.md">English</a> · <a href="README.zh-CN.md">中文</a>
</p>

<p align="center">
  <a href="https://github.com/JunyanKang/biomed-workbench/actions"><img alt="Quality" src="https://img.shields.io/github/actions/workflow/status/JunyanKang/biomed-workbench/quality.yml?branch=main&amp;label=quality"></a>
  <a href="LICENSE"><img alt="Apache-2.0 license" src="https://img.shields.io/badge/license-Apache--2.0-4388C7"></a>
  <img alt="Dynamic scientific modules" src="https://img.shields.io/badge/modules-dynamic-36A58B">
  <img alt="One Codex skill" src="https://img.shields.io/badge/Codex%20skills-1-E05A47">
</p>

<p align="center">
  <img src="assets/research-loop.png" width="100%" alt="Biomed Workbench research loop">
</p>

Biomed Workbench 是一个独立的 Codex 生物医学科研助理插件。它不是脚本集合，也不是把多个源库拼接起来的本地工作流镜像；它的目标是让 Codex 以一个统一入口理解科研问题，自动选择模块，组织串联、并联或混合研究计划，并把证据、分析、质控、假设修正和论文级交付放在同一个可追溯框架内。

用户只需要描述科研目标。工作台负责把问题转化为有科学依赖关系的研究程序：先确认问题和输入，再检索证据、检查格式和版本边界、调用或改写可执行模板、审查结果质量、保留不确定性，最后形成可复核的结果、图表、方法、审稿回复、专利或展示材料。

## 核心定位

Biomed Workbench 试图解决的是科研中的真实复杂性：一个项目往往同时需要文献和数据库证据、组学或单细胞分析、分子和结构解释、统计设计审查，以及最终的论文、审稿回复或转化材料。传统做法会把这些工作拆成很多工具和脚本，用户需要自己判断顺序和边界。

本插件将这些能力收敛为一个 Codex 入口：`biomed-workbench`。背后模块可以动态发现和组合，但用户不需要手动调用分散 skill，也不需要知道内部模块名。

## 研究闭环

1. **提出问题：** 明确生物学问题、实验单位、数据范围、证据现状和交付目标。
2. **制定计划：** 自动选择最小但科学上完整的模块集合，形成单步、串联、并联或混合 DAG。
3. **执行分析：** 基于真实项目输入检查格式、版本、参数和模板适配。
4. **质疑结果：** 检查混杂、缺失元数据、统计单位错误、质控失败和证据冲突。
5. **修正假设：** 当结果不支持原假设时，保留失败原因并更新分析路径。
6. **交付成果：** 输出结果表、图、方法、证据矩阵、审稿意见回复、专利披露或展示方案，同时保留未解决问题。

工作台不会把“程序运行成功”直接等同于“科学结论成立”。只有通过模块契约和质量门控的结果，才可以进入项目证据。

## 专业能力

| 能力方向 | 工作台协调的内容 |
| --- | --- |
| [证据与文献](docs/capabilities/evidence-and-literature.md) | NCBI、UniProt、Ensembl、dbSNP、gnomAD、HPO、GO、Reactome、cBioPortal、Open Targets、Crossref、Europe PMC、bioRxiv、PubChem、ClinicalTrials.gov、RCSB PDB、AlphaFold、证据新鲜度、引用和主张审查 |
| [组学与单细胞](docs/capabilities/omics-and-single-cell.md) | FASTQ/BAM/VCF/BED/表达矩阵流程、peak 和 motif、NMF、GWAS fine-mapping、单细胞 QC、ambient RNA、doublet、供体感知推断、整合、注释、通讯、轨迹、RegVelo、多组学和空间转录组 |
| [分子与结构生物学](docs/capabilities/molecular-and-structural.md) | 序列检查、ORF、PCR 引物、特异性筛查、CRISPR、限制性酶切、Golden Gate、结构证据、坐标质量、结构比较、docking 审查和化学过滤 |
| [临床与实验研究](docs/capabilities/clinical-and-experimental.md) | 队列、生存分析、biomarker、不良事件、临床边界、流式、qPCR、生长曲线、剂量反应、Western blot、biodistribution、xenograft、稳定性和实验定量 |
| [成像与可视化](docs/capabilities/imaging-and-visualization.md) | 图像 profiling、分割、共定位、追踪、定量审查、科学图和分子可视化 |
| [论文与转化交付](docs/capabilities/publication-and-translation.md) | 图表规格、稿件审查、引用审计、审稿人模拟、response matrix、修订谱系、专利准备、流程图和展示交付 |

完整能力地图见：[中文](docs/capabilities/README.zh-CN.md) · [English](docs/capabilities/README.md)。

## 单细胞和组学深度

单细胞项目可以被组织为完整研究程序，而不是零散预处理脚本。工作台可以协调 h5ad、10x HDF5、Matrix Market、Seurat 对象读取和验证，ambient RNA、doublet、Scanpy/Seurat 基础流程、Harmony/Scanorama/BBKNN、scVI/scANVI、CellTypist、Azimuth、popV、Cell Ontology 约束注释、pseudobulk、混合模型、CellChat、NicheNet、LIANA、CellPhoneDB、SCENIC/SCENIC+、RegVelo、RNA+ATAC、CITE-seq、WNN、MOFA+、peak calling、chromVAR 和空间转录组。

需要强调的是：计划不是证据。Codex 必须检查用户真实文件，适配项目代码，记录实际工具和依赖版本，重新读取输出，并通过质量门控后，结果才可以进入科学解释和论文交付。

## 在 Codex 中使用

安装后，开启一个新的 Codex 任务，直接用自然语言描述科研目标即可。例如：

> 比较 TP53 在文献、基因、变异、通路、结构和临床试验中的证据，指出冲突、缺失证据和下一步最关键实验。

> 从输入验证开始，设计并执行一个供体感知的单细胞和空间转录组研究流程，完成技术伪影审查、注释、多组学整合、通讯、轨迹、调控分析、假设修正和论文级结果交付。

> 审查这套分子设计方案，包括序列和结构质量、引物特异性、CRISPR 设计、docking pose、化学过滤和实验验证计划。

使用说明见：[中文](docs/using-biomed-workbench.zh-CN.md) · [English](docs/using-biomed-workbench.md)。

## 安装

将 GitHub 仓库加入 Codex marketplace 并安装：

```bash
codex plugin marketplace add JunyanKang/biomed-workbench --ref main
codex plugin add biomed-workbench@biomed-workbench
codex plugin list
```

安装或更新后，请开启一个新的 Codex 任务，让 `biomed-workbench` skill 被重新加载。安装和更新说明见：[中文](docs/installation.zh-CN.md) · [English](docs/installation.md)。

## 文档

- 能力地图：[中文](docs/capabilities/README.zh-CN.md) · [English](docs/capabilities/README.md)
- 使用指南：[中文](docs/using-biomed-workbench.zh-CN.md) · [English](docs/using-biomed-workbench.md)
- 安装与更新：[中文](docs/installation.zh-CN.md) · [English](docs/installation.md)
- 可重复性与兼容性：[中文](docs/reproducibility.zh-CN.md) · [English](docs/reproducibility.md)
- [公共数据验证案例](docs/cases/README.md)
- [能力成熟度与证据](docs/maturity.md)
- [架构和模块扩展](docs/architecture.md)
- [格式契约](docs/format-contracts.md)
- [开发与发布](docs/development.md)

## 边界和信任

Biomed Workbench 是科研助理，不是基础设施管理器、临床决策系统、法律意见工具，也不是自动生成科学真相的机器。它不 vendor 外部研究项目，不依赖本地开发过程文件，也不会把私有路径、凭据或审计账本作为公开产品的一部分。

后续新增科研方法时，应该作为独立模块接入：声明 manifest、输入输出 artifact、兼容性策略、模板、质量门控、测试和文档。用户入口仍然保持为 `biomed-workbench`，这样未来增加新工具时，Codex 仍然通过同一套研究闭环自动路由和编排。

[`reports/`](reports/) 中发布的是 release-safe 的兼容性证据、公共数据库检查、模板覆盖、安装验证和公共数据案例。可选 API key 由用户在仓库外配置，不能写入代码、报告、示例或研究产物。

许可证：[Apache-2.0](LICENSE)。
