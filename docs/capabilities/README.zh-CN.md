# 专业能力地图

语言：[中文](README.zh-CN.md) · [English](README.md) · 根目录：[中文](../../README.md) · [English](../../README.en.md)

Biomed Workbench 按科研决策组织能力，而不是按脚本目录展示能力。用户提出研究问题并提供数据后，工作台会组合必要模块，把任务从问题界定、证据检索、分析执行、结果质疑、假设修正推进到科研交付。

## 能力方向

| 方向 | 科学角色 | 详细文档 |
| --- | --- | --- |
| 证据与文献 | 建立“已知、争议、缺失、是否过时”的证据底座 | [查看](evidence-and-literature.zh-CN.md) |
| Bulk 测量 | 分析混合样本中的 RNA、染色质、蛋白结合、翻译、新生转录和基因组三维结构，同时严格区分实验方法、靶标、对照与归一化策略 | [Bulk 测序方法](bulk-sequencing-assays.zh-CN.md)；[染色质 peak 分析](bulk-chromatin-peak-calling.md) |
| 单细胞测量 | 在保留细胞层级结构的同时处理样本设计、整合、注释、轨迹、多组学与跨物种投射 | [通用与单细胞分析](omics-and-single-cell.zh-CN.md)；[整合、参考映射与跨物种规范](single-cell-integration-reference-cross-species.zh-CN.md) |
| 空间测量 | 连接分子状态、物理坐标、组织图像、参考映射、空间区域、通讯、多切片对齐与三维结构 | [轨迹与空间完整分析规范](trajectory-spatial-complete-analysis.zh-CN.md)；[空间解卷积与投射方法](spatial-deconvolution-projection-methods.md) |
| 通用分析与项目方法 | 为适用的研究尺度提供格式核查、实验设计、统计、富集、网络、作图规范与科学评审 | [查看](omics-and-single-cell.zh-CN.md) |
| 分子与结构生物学 | 连接序列、互作网络、化学、对接和结构证据，形成可实验检验的分子假设 | [中文指南](molecular-and-structural.zh-CN.md) · [English](molecular-and-structural.md)；STRING PPI；HADDOCK3/DockQ/PRODIGY；AlphaFold 3；MSBio2/Metascape/Cytoscape |
| 成像与可视化 | 对图像进行定量分析，并产出忠实、可审查的科学视觉材料 | [查看](imaging-and-visualization.zh-CN.md) |
| 临床与实验研究 | 将队列、实验测量和统计解释连接为可判断的研究证据 | [查看](clinical-and-experimental.zh-CN.md) |
| 论文与转化交付 | 根据项目证据推荐期刊，并将证据链转化为符合目标期刊规范的稿件、回复、专利、图表和展示材料 | [查看](publication-and-translation.zh-CN.md)；[版本化期刊规范](../journal-standards.zh-CN.md) |

## 编排模型

每个项目会被表示为一张保留前后依赖的研究图。相互独立的证据源可以并行检查；依赖上游结果的分析会依次执行；复杂项目可以混合两种模式。工作台记录假设、证据、数据与图表、决策、质量检查和修订原因，使后续智能体能够继续项目而不会丢失科学逻辑。

用户始终通过同一个 `biomed-workbench` 入口提出问题。简单数据库问题可以路由到一个模块；复杂转化研究可以组合研究设计、多个分析分支、机制证据、图表、稿件、审稿人模拟和回复矩阵。

## 当前范围

注册表目前包含 **198 个可独立发现的模块**。精确的执行与公共数据验收状态由对应版本的发布证据登记，不从“模块已注册”这一事实推断。Bulk 层现已覆盖 RNA-seq；ChIP-seq、CUT&RUN 与 CUT&Tag；DRIP-seq、DRIPc-seq、sDRIP/ssDRIP-seq、qDRIP-seq、R-ChIP、MapR 和传感器明确的 CUT&Tag 等 R-loop 测量；RIP-seq、eCLIP、iCLIP、HITS-CLIP、PAR-CLIP 与 LACE-seq；带多种 ORF 识别工具比较的 Ribo-seq；GRO-seq、PRO-seq、TT-seq 与 NET-seq；ATAC-seq 与 DNase-seq；WGBS、RRBS 与 EM-seq；Hi-C、Micro-C、Capture-C、HiChIP、PLAC-seq 与 ChIA-PET；以及 MeRIP-seq/m6A-seq。具体可据此主张的后端、版本、数据设计与产物范围，以对应公共数据案例为准。

CUT&Tag 是实验方法；S9.6 是靶标或抗体身份；外源内参是可选归一化方案；RNase H 处理提供特异性证据。这四者分别登记，任何一项都不会被错误提升为与 CUT&Tag 并列的实验类型。

单细胞和空间模块保留平台与方法专属契约；通用模块承担可跨尺度复用的设计、统计、富集、网络、证据评审、作图与发表支持。论文能力提供基于研究范围、读者、文章类型和证据成熟度的期刊定位，以及逐项稿件规范审查。

## 可扩展机制

后期新增工具不是新增一个用户要手动调用的 skill，而是新增一个符合契约的科学模块。一个合格模块需要包括：

- 清晰的科学目的和适用边界；
- 输入、输出、格式和参数契约；
- 兼容性策略和实际执行时的版本记录；
- 至少一份无需修改源文件、通过参数和输入契约运行的高质量实现；
- 模块级质量门控、失败处理和限制说明；
- 正常、边界和失败场景测试；
- 面向用户的能力说明。

模块通过中央注册表自动发现。只要新模块满足契约，router 就可以在合适的问题中选择它，并与已有模块组合成单步、串联、并联或混合工作流。

## 科学质量边界

Biomed Workbench 的设计目标是拒绝虚假确定性。它会区分：

- 有数据和数据足够；
- 技术重复和独立生物学样本；
- 相关性和因果证据；
- 数据库检索和生物学解释；
- 预测置信度和实验验证；
- 有引用和引用真正支持主张；
- 计算完成和科学结论成立。

当输入、后端、质量阈值或证据链缺失时，对应结论保持未解决。失败的质量门控可以触发假设和计划修正，而不是被隐藏在最终结果中。
