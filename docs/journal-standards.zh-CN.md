# 期刊选择与稿件规范库

Biomed Workbench 的期刊能力由机器可读的正式规范库驱动，而不是由 Agent 临场回忆格式要求。当前版本 `2026.07.31` 收录 54 本生命医学高水平期刊，覆盖 Nature、Science、Cell Press、The Lancet、NEJM、JAMA、The BMJ、PNAS、EMBO Press、Genome Biology、Genome Research、Nucleic Acids Research、Bioinformatics、PLOS Biology 等期刊与期刊家族。

规范原始文件位于：

- 当前版本：`biomed_workbench/knowledge/journal_standards/v2026.07.31.json`
- 当前版本索引：`biomed_workbench/knowledge/journal_standards/index.json`
- 可复现构建程序：`tools/build_journal_standards.py`

## 当前收录期刊

下表与版本 `2026.07.31` 的 54 本期刊注册表一一对应。学科领域用于帮助读者快速浏览，正式推荐仍会读取每本期刊完整的读者、选题和研究设计字段。

指标口径统一为 **2026 Journal Citation Reports（2025 年数据）**。[Clarivate 于 2026 年 6 月 17 日发布该版本](https://clarivate.com/news/clarivate-releases-journal-citation-reports-2026/)；影响因子栏因此指 **2025 Journal Impact Factor（JIF）**，不是网页访问年份。JCR 分区按学科类别分别计算，同一本期刊可能对应多个类别与不同分区。只有期刊或出版社公开页面明确给出 2025 JIF，并给出足以确认分区的类别排名时，下表才登记数值或 `Q1`；其余条目标为“待机构版核验”。这表示最新数值尚不能从公开官方页面完整核实，不表示没有影响因子或不在 JCR 中。

<!-- journal-coverage-table:start -->
| 期刊 | 杂志社 / 出版机构 | 主要领域 | JCR 2026 分区 | 2025 JIF |
| --- | --- | --- | --- | ---: |
| [Nature](https://www.nature.com/nature/for-authors/formatting-guide) | Springer Nature · Nature Portfolio | 综合科学、机制生物学、概念性突破 | 待机构版逐类别核验 | [56.1](https://www.nature.com/nature/journal-impact) |
| [Nature Medicine](https://www.nature.com/nm/content) | Springer Nature · Nature Portfolio | 转化医学、临床医学、疾病机制 | 待机构版逐类别核验 | [52.5](https://www.nature.com/nm/journal-impact) |
| [Nature Biotechnology](https://www.nature.com/nbt/content) | Springer Nature · Nature Portfolio | 生物技术、技术开发、工程学 | 待机构版逐类别核验 | [44.5](https://www.nature.com/nbt/journal-impact) |
| [Nature Genetics](https://www.nature.com/ng/content) | Springer Nature · Nature Portfolio | 遗传学、基因组学、人类遗传学 | 待机构版逐类别核验 | [25.5](https://www.nature.com/ng/journal-impact) |
| [Nature Methods](https://www.nature.com/nmeth/content) | Springer Nature · Nature Portfolio | 研究方法、方法评测、技术开发 | 待机构版逐类别核验 | [28.3](https://www.nature.com/nmeth/journal-impact) |
| [Nature Neuroscience](https://www.nature.com/neuro/content) | Springer Nature · Nature Portfolio | 神经科学、脑科学、神经环路 | 待机构版逐类别核验 | [20.3](https://www.nature.com/neuro/journal-impact) |
| [Nature Immunology](https://www.nature.com/ni/content) | Springer Nature · Nature Portfolio | 免疫学、免疫机制、感染 | 待机构版逐类别核验 | [26.5](https://www.nature.com/ni/journal-impact) |
| [Nature Cancer](https://www.nature.com/natcancer/content) | Springer Nature · Nature Portfolio | 肿瘤学、临床肿瘤学、肿瘤生物学 | 待机构版逐类别核验 | [28.0](https://www.nature.com/natcancer/journal-impact) |
| [Nature Cell Biology](https://www.nature.com/ncb/content) | Springer Nature · Nature Portfolio | 细胞生物学、机制生物学、细胞器 | 待机构版逐类别核验 | [22.7](https://www.nature.com/ncb/journal-impact) |
| [Nature Microbiology](https://www.nature.com/nmicrobiol/content) | Springer Nature · Nature Portfolio | 微生物学、病原生物学、微生物组 | 待机构版逐类别核验 | [18.7](https://www.nature.com/nmicrobiol/journal-impact) |
| [Nature Metabolism](https://www.nature.com/natmetab/content) | Springer Nature · Nature Portfolio | 代谢研究、代谢性疾病、生理学 | 待机构版逐类别核验 | [27.5](https://www.nature.com/natmetab/journal-impact) |
| [Nature Biomedical Engineering](https://www.nature.com/natbiomedeng/submission-guidelines/aip-and-formatting) | Springer Nature · Nature Portfolio | 生物医学工程、医疗器械、诊断学 | 待机构版逐类别核验 | [26.3](https://www.nature.com/natbiomedeng/journal-impact) |
| [Nature Communications](https://www.nature.com/ncomms/submit/article) | Springer Nature · Nature Portfolio | 生物学、医学、研究方法 | 待机构版逐类别核验 | [18.9](https://www.nature.com/ncomms/journal-impact) |
| [Communications Biology](https://www.nature.com/commsbio/submission-guidelines) | Springer Nature · Nature Portfolio | 生物学、细胞生物学、基因组学 | 待机构版逐类别核验 | [5.8](https://www.nature.com/commsbio/journal-impact) |
| [Nature Structural & Molecular Biology](https://www.nature.com/nsmb/content) | Springer Nature · Nature Portfolio | 结构生物学、分子生物学、生物化学 | 待机构版逐类别核验 | [10.1](https://www.nature.com/nsmb/journal-impact) |
| [Scientific Data](https://www.nature.com/sdata/publish/submission-guidelines) | Springer Nature · Nature Portfolio | 科学数据资源、数据集、数据复用 | 待机构版逐类别核验 | [7.2](https://www.nature.com/sdata/journal-impact) |
| [Science](https://www.science.org/content/page/science-information-authors) | AAAS | 综合科学、概念性突破、生物学 | 待机构版逐类别核验 | 待机构版核验 |
| [Science Translational Medicine](https://www.science.org/journal/stm/information-for-authors) | AAAS | 转化医学、临床医学、治疗学 | 待机构版逐类别核验 | 待机构版核验 |
| [Science Immunology](https://www.science.org/journal/sciimmunol/information-for-authors) | AAAS | 免疫学、免疫机制、感染 | 待机构版逐类别核验 | 待机构版核验 |
| [Science Signaling](https://www.science.org/journal/signaling/information-for-authors) | AAAS | 信号转导、细胞通讯、激酶与通路 | 待机构版逐类别核验 | 待机构版核验 |
| [Science Advances](https://www.science.org/journal/sciadv/information-for-authors) | AAAS | 综合科学、生物学、医学 | 待机构版逐类别核验 | 待机构版核验 |
| [Cell](https://www.cell.com/cell/home) | Elsevier · Cell Press | 细胞生物学、机制生物学、综合生命科学 | 待机构版逐类别核验 | 待机构版核验 |
| [Cell Stem Cell](https://www.cell.com/cell-stem-cell/home) | Elsevier · Cell Press | 干细胞、发育生物学、再生医学 | 待机构版逐类别核验 | 待机构版核验 |
| [Cancer Cell](https://www.cell.com/cancer-cell/home) | Elsevier · Cell Press | 肿瘤学、临床肿瘤学、肿瘤生物学 | 待机构版逐类别核验 | 待机构版核验 |
| [Immunity](https://www.cell.com/immunity/home) | Elsevier · Cell Press | 免疫学、免疫机制、感染 | 待机构版逐类别核验 | 待机构版核验 |
| [Neuron](https://www.cell.com/neuron/home) | Elsevier · Cell Press | 神经科学、脑科学、神经环路 | 待机构版逐类别核验 | 待机构版核验 |
| [Molecular Cell](https://www.cell.com/molecular-cell/home) | Elsevier · Cell Press | 分子生物学、基因调控、染色质 | 待机构版逐类别核验 | 待机构版核验 |
| [Cell Metabolism](https://www.cell.com/cell-metabolism/home) | Elsevier · Cell Press | 代谢研究、生理学、营养学 | 待机构版逐类别核验 | 待机构版核验 |
| [Cell Host & Microbe](https://www.cell.com/cell-host-microbe/home) | Elsevier · Cell Press | 微生物学、感染、微生物组 | 待机构版逐类别核验 | 待机构版核验 |
| [Developmental Cell](https://www.cell.com/developmental-cell/home) | Elsevier · Cell Press | 发育生物学、细胞生物学、形态发生 | 待机构版逐类别核验 | 待机构版核验 |
| [Cell Reports Medicine](https://www.cell.com/cell-reports-medicine/home) | Elsevier · Cell Press | 医学、转化医学、临床研究 | 待机构版逐类别核验 | 待机构版核验 |
| [Current Biology](https://www.cell.com/current-biology/home) | Elsevier · Cell Press | 生物学、进化生物学、神经科学 | 待机构版逐类别核验 | 待机构版核验 |
| [The Lancet](https://www.thelancet.com/journals/lancet/home) | Elsevier · The Lancet Group | 临床医学、全球卫生、公共卫生 | 待机构版逐类别核验 | 待机构版核验 |
| [The Lancet Oncology](https://www.thelancet.com/journals/lanonc/home) | Elsevier · The Lancet Group | 临床肿瘤学、肿瘤治疗、临床试验 | [Q1（公开排名可核验）](https://info.thelancet.com/lanonc/request-access) | [33.7](https://info.thelancet.com/lanonc/request-access) |
| [The Lancet Neurology](https://www.thelancet.com/journals/laneur/home) | Elsevier · The Lancet Group | 神经病学、脑疾病、临床研究 | [Q1（公开排名可核验）](https://info.thelancet.com/laneur/request-access) | [54.6](https://info.thelancet.com/laneur/request-access) |
| [The Lancet Infectious Diseases](https://www.thelancet.com/journals/laninf/home) | Elsevier · The Lancet Group | 感染病学、病原生物学、流行病学 | [Q1（公开排名可核验）](https://info.thelancet.com/laninf/request-access) | [29.4](https://info.thelancet.com/laninf/request-access) |
| [The Lancet Digital Health](https://www.thelancet.com/journals/landig/home) | Elsevier · The Lancet Group | 数字健康、机器学习、临床人工智能 | 待机构版逐类别核验 | 待机构版核验 |
| [The Lancet Haematology](https://www.thelancet.com/journals/lanhae/home) | Elsevier · The Lancet Group | 血液学、血液病、临床试验 | [Q1（公开排名可核验）](https://info.thelancet.com/lanhae/request-access) | [20.4](https://info.thelancet.com/lanhae/request-access) |
| [The Lancet Respiratory Medicine](https://www.thelancet.com/journals/lanres/home) | Elsevier · The Lancet Group | 呼吸医学、肺疾病、临床研究 | [Q1（公开排名可核验）](https://info.thelancet.com/lanres/request-access) | [34.7](https://info.thelancet.com/lanres/request-access) |
| [The Lancet Gastroenterology & Hepatology](https://www.thelancet.com/journals/langas/home) | Elsevier · The Lancet Group | 胃肠病学、肝病学、临床研究 | [Q1（公开排名可核验）](https://info.thelancet.com/langas/request-access) | [39.1](https://info.thelancet.com/langas/request-access) |
| [New England Journal of Medicine](https://www.nejm.org/author-center/article-types) | Massachusetts Medical Society | 临床医学、临床试验、公共卫生 | [Q1（官方标明类别领先）](https://www.nejm.org/about-nejm/about-nejm) | [84.5](https://www.nejm.org/about-nejm/about-nejm) |
| [JAMA](https://jamanetwork.com/journals/jama/pages/instructions-for-authors) | American Medical Association | 临床医学、卫生政策、临床试验 | 待机构版逐类别核验 | 待机构版核验 |
| [The BMJ](https://www.bmj.com/about-bmj/resources-authors/article-types) | BMJ Group | 临床医学、公共卫生、证据综合 | 待机构版逐类别核验 | 待机构版核验 |
| [Proceedings of the National Academy of Sciences](https://www.pnas.org/author-center/submitting-your-manuscript) | National Academy of Sciences | 综合科学、生物学、医学 | 待机构版逐类别核验 | 待机构版核验 |
| [eLife](https://elifesciences.org/articles/research-article) | eLife Sciences Publications | 生物学、医学、研究方法 | 待机构版逐类别核验 | 待机构版核验 |
| [The EMBO Journal](https://www.embopress.org/page/journal/14602075/authorguide) | EMBO Press | 分子生物学、细胞生物学、机制生物学 | 待机构版逐类别核验 | 待机构版核验 |
| [Molecular Systems Biology](https://www.embopress.org/page/journal/17444292/authorguide) | EMBO Press | 系统生物学、计算生物学、网络生物学 | 待机构版逐类别核验 | 待机构版核验 |
| [Genome Biology](https://genomebiology.biomedcentral.com/submission-guidelines) | Springer Nature · BMC | 基因组学、单细胞组学、生物信息学 | 待机构版逐类别核验 | 待机构版核验 |
| [Genome Research](https://genome.cshlp.org/site/misc/ifora.xhtml) | Cold Spring Harbor Laboratory Press | 基因组学、功能基因组学、研究方法 | 待机构版逐类别核验 | 待机构版核验 |
| [Nucleic Acids Research](https://academic.oup.com/nar/pages/author-guidelines) | Oxford University Press | DNA、RNA、基因组学 | 待机构版逐类别核验 | 待机构版核验 |
| [Bioinformatics](https://academic.oup.com/bioinformatics/pages/author-guidelines) | Oxford University Press | 生物信息学、科学软件、算法 | 待机构版逐类别核验 | 待机构版核验 |
| [PLOS Biology](https://journals.plos.org/plosbiology/s/submission-guidelines) | Public Library of Science | 生物学、开放科学、研究方法 | 待机构版逐类别核验 | 待机构版核验 |
| [Blood](https://ashpublications.org/blood/pages/manuscript_types) | American Society of Hematology | 血液学、血液肿瘤学、免疫学 | 待机构版逐类别核验 | 待机构版核验 |
| [Circulation](https://www.ahajournals.org/circ/author-instructions) | American Heart Association | 心血管医学、心脏研究、临床试验 | 待机构版逐类别核验 | 待机构版核验 |
<!-- journal-coverage-table:end -->

影响因子与分区只用于描述期刊生态和辅助人工比较，不进入自动推荐评分，也不用于预测接收概率。真正开始投稿准备时，Agent 仍须在机构版 JCR 中逐类别确认分区和 JIF，并把核验日期与所用 JCR 版本写入项目记录。

## 每本期刊记录什么

每个期刊条目独立保存：

- 期刊面向的主要读者和学科范围；
- 常见且适合推荐的文章类型；
- 选题、研究设计与证据成熟度的适配信号；
- 摘要、正文、图表合计数、参考文献等已由官方公开的限制；
- 要求的文章组成、语言风格、图表原则和报告规范；
- 期刊或出版社的官方作者指南、文章类型说明、研究范围和图表指南；
- 标准版本、核查日期和规范文件校验值。

数值字段具有三种科学状态：

1. **期刊明确值**：可直接用于合规检查；
2. **出版社通用值**：适用于该出版体系，但目标期刊的文章类型说明可以覆盖它；
3. **官方未公开或尚未核实**：保持为空，并在交付前列为人工核实项。

第三种状态绝不转换成“没有限制”。任何未解决的必要核实项都会阻止系统给出“可投稿”结论。

## 推荐依据

`journal-targeting-and-compliance` 会把项目的科学问题、研究类型、主要方法、预期读者和证据成熟度与期刊条目比较，给出：

- 读者与主题匹配点；
- 文章类型匹配点；
- 当前不匹配或仍需编辑判断的部分；
- 绑定的标准版本、核查日期和官方来源。

推荐评分不使用影响因子，不预测接收概率，也不会因为期刊名气而覆盖研究范围、证据完整性或读者适配性。最终推荐仍需结合研究新颖性、机制深度、验证层级、样本设计、临床或转化价值以及作者的开放获取与时间要求作出编辑判断。

## 写作与交付门禁

确定目标期刊后，Agent 必须在开始结构化写作前绑定：

- 期刊标识；
- 文章类型；
- 规范版本；
- 规范文件校验值；
- 官方来源；
- 最近核查日期。

稿件审查逐项比较正文、摘要、图表、参考文献、必要组成和报告声明。只有所有明确要求通过、所有人工核实项解决，并在投稿前重新访问官方说明确认没有更新时，才能进入投稿交付。

## 版本更新策略

历史版本不可覆盖。某一本期刊更新时：

1. 重新访问该期刊的官方作者说明、文章类型和图表指南；
2. 只修改有官方证据支持的字段；
3. 为该期刊建立新版本并记录核查日期与来源；
4. 重新生成目录校验值；
5. 运行目录完整性、推荐稳定性和边界条件测试；
6. 保留旧版本，使既往稿件仍能说明当时依据的标准；
7. 将新版本设为当前版本前，复查至少一个推荐案例和一个合规案例。

Agent 可以在自然语言任务中接收“加入某期刊”或“更新某期刊规范”的请求。新增条目必须满足与现有条目相同的字段、来源和测试要求；不能只添加名称与网址。
