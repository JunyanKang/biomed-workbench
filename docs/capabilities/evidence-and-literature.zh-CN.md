# 证据、数据库与文献

语言：[中文](evidence-and-literature.zh-CN.md) · [English](evidence-and-literature.md)

## 科学角色

- NCBI Gene 同源记录可以在指定 Gene ID 和物种范围内提供有边界的源物种到目标物种映射；它仍属于数据库证据，不等同于功能等价性证据。
- 稳定 Gene ID 只在基因符号与物种精确匹配后解析；存在歧义的候选项保持未解决，不会被静默传入下游数据库调用。

这一能力方向在分析前、分析中和分析后持续建立证据全景。它把资料检索与标识符对齐、来源特异的解读、矛盾追踪、引用支持度检查和时效性复核结合起来。检索到的记录保持为来源证据，不会被自动提升为生物学结论。

## 已支持的能力

### 统一证据与数据库方案

对于范围较广的证据请求，工作台会先解析标识符和引用记录，再安排特定来源检索、派生证据、时效性检查和面向发表的引用审查。这可避免下游模块把基因符号、题名、DOI、rsID、通路 ID、研究 ID 或蛋白质 accession 默认为已经准确解析。

统一方案可组合 NCBI Entrez 与 Gene、UniProt 与 Ensembl 身份信息、dbSNP、gnomAD、HPO、GO、Reactome、cBioPortal、Open Targets、Crossref、Europe PMC、bioRxiv 或 medRxiv、PubChem、ClinicalTrials.gov、RCSB PDB、AlphaFold 以及蛋白质无序倾向证据。每个被选模块分别报告其输入契约、输出字段、兼容性行、质量门控、可选凭据和未解决状态。标识符未命中、候选歧义、上游中断、检索截断、记录过期和跨来源不一致都会保持可见。

### 文献与引用证据

- 在明确查询式和日期背景下检索并获取生物医学文献。
- 以 DOI 为中心，跨 Crossref 和 Europe PMC 解析引用记录，同时保留差异。
- 获取感知版本的 bioRxiv 和 medRxiv 历史，不合并预印本修订。
- 审查引用元数据、引用解析、陈述覆盖度与主张—证据匹配度。
- 针对规范 rs 标识符获取有边界的 dbSNP 参考变异身份证据，将临床、人群和基因组版本解读保留在身份记录之外。
- 获取固定字段的 gnomAD GRCh38 聚合基因约束背景，保留人群耗竭指标与临床或因果解读之间的区别。
- 获取一个精确的公开 cBioPortal 癌症基因组研究记录，保留研究身份、癌种、参考基因组和实验特异的队列计数，不将这些元数据当作患者层结果或临床证据。
- 针对一个指定基因和公开研究获取有边界的 cBioPortal 突变记录，明确解析突变 profile 和样本列表，保留坐标与基因组版本背景，并将受上限限制的结果标记为非穷尽。
- 通过必需的 POST 基因过滤获取有边界的 cBioPortal 离散拷贝数事件，保留分类事件语义，并将本地截断的记录标记为非穷尽。
- 根据声明的合格分母审查离散拷贝数队列覆盖；只有完整、未截断的来源证据才能进入串行的适配与审查路径，而结果仍是描述性的，不推断纯度、倍体、局灶性或临床意义。
- 区分以标识符为键的未命中、仅题名覆盖缺口、上游中断和真正的未解决记录。

代表性模块包括 `literature-evidence`、`citation-record-resolution`、`preprint-evidence`、`citation-audit`、`citation-resolution-adjudication` 和 `assertion-citation-coverage-audit`。

### 公共生物医学数据库

- 检索、汇总、获取并连接 NCBI Entrez 记录。
- 将精确基因符号解析为稳定 NCBI Gene ID，再建立基因、同源和变异证据，不抹去数据库身份或缺失记录。
- 从 PubChem 获取化学身份与描述符，并检查歧义。
- 按研究设计获取 ClinicalTrials.gov 研究，限定分页范围并明确标记截断。
- 检索 RCSB PDB，并获取条目、聚合物实体和结合配体证据。
- 获取 AlphaFold DB 模型覆盖与置信度元数据，同时区分预测与实验。
- 获取与 accession 绑定的 IUPred2A 无序倾向 profile，保留残基对齐、阈值策略以及预测与验证之间的严格边界。

代表性模块包括 `ncbi-search`、`ncbi-fetch`、`ncbi-link`、`gene-identifier-resolution`、`gene-evidence`、`gene-ortholog-evidence`、`variant-evidence`、`chemical-evidence`、`clinical-trial-evidence`、`structure-search`、`structure-evidence`、`alphafold-structure-evidence` 和 `protein-disorder-evidence`。

### 证据治理

- 评估一个来源是否仍处于声明的复核时间窗内，不把记录年龄误写成当前性证明。
- 审查时间关系、来源版本、取代链与因果顺序。
- 裁定支持、反驳、阴性、不合格和未解决证据。
- 使用溯源、逐类指标、支持门控和基线回归检查来评估分类金标准集。

代表性模块包括 `source-freshness-audit`、`temporal-integrity-audit`、`claim-evidence-integrity-audit` 和 `classification-gold-set-evaluation`。

## 质量门控

证据流程保留原始标识符、来源溯源、查询边界、分页状态、日期和未解决的歧义。检索被截断时禁止穷尽性主张；未评估上游漂移时禁止当前性主张；关联性证据不得推导因果主张；仅有引用标记不足以支持“文献支持该主张”。

## 典型交付物

证据地图、来源清单、矛盾表、目标档案、临床试验全景、引用审查、主张—证据矩阵、未解决证据队列，以及与可审查记录链接的文献章节。
