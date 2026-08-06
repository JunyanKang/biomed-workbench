# 期刊选择与稿件规范库

Biomed Workbench 的期刊能力由机器可读的正式规范库驱动，而不是由 Agent 临场回忆格式要求。当前版本 `2026.08.03` 收录 100 本生命医学高水平期刊，覆盖综合生命科学、基础与机制生物学、组学与计算方法、肿瘤、免疫、神经、代谢、心血管、感染、公共卫生和主要临床专科。清单按 2025 JIF 从高到低展示；JIF 不进入期刊适配评分。

规范原始文件位于：

- 当前版本：`biomed_workbench/knowledge/journal_standards/v2026.08.03.json`
- 当前版本索引：`biomed_workbench/knowledge/journal_standards/index.json`
- 可复现构建程序：`tools/build_journal_standards.py`

## 当前收录期刊

下表与版本 `2026.08.03` 的 100 本期刊注册表一一对应。学科领域用于帮助读者快速浏览，正式推荐仍会读取每本期刊完整的读者、选题和研究设计字段。

指标口径统一为 **2026 Journal Citation Reports（2025 年数据）**。[Clarivate 于 2026 年 6 月 17 日发布该版本](https://clarivate.com/news/clarivate-releases-journal-citation-reports-2026/)；影响因子栏因此指 **2025 Journal Impact Factor（JIF）**，不是网页访问年份。JCR 分区按学科类别分别登记，同一本期刊可以对应多个类别和不同分区。

<!-- journal-coverage-table:start -->
| 期刊 | 出版机构 | JCR 学科类别 | JCR 2026 分区 | 2025 JIF |
| --- | --- | --- | --- | ---: |
| [CA: A Cancer Journal for Clinicians](https://acsjournals.onlinelibrary.wiley.com/journal/15424863) | American Cancer Society · Wiley | 肿瘤学 (SCIE) | 肿瘤学: Q1 | 685.2 |
| [Nature Reviews Molecular Cell Biology](https://www.nature.com/nrm/content) | Springer Nature · Nature Portfolio | 细胞生物学 (SCIE) | 细胞生物学: Q1 | 118.0 |
| [The Lancet](https://www.thelancet.com/journals/lancet/home) | Elsevier · The Lancet Group | 综合与内科医学 (SCIE) | 综合与内科医学: Q1 | 109.0 |
| [Nature Reviews Microbiology](https://www.nature.com/nrmicro/content) | Springer Nature · Nature Portfolio | 微生物学 (SCIE) | 微生物学: Q1 | 104.6 |
| [Nature Reviews Clinical Oncology](https://www.nature.com/nrclinonc/content) | Springer Nature · Nature Portfolio | 肿瘤学 (SCIE) | 肿瘤学: Q1 | 94.6 |
| [Nature Reviews Drug Discovery](https://www.nature.com/nrd/content) | Springer Nature · Nature Portfolio | 生物技术与应用微生物学 (SCIE)<br>药理学与药学 (SCIE) | 生物技术与应用微生物学: Q1<br>药理学与药学: Q1 | 91.2 |
| [New England Journal of Medicine](https://www.nejm.org/author-center/article-types) | Massachusetts Medical Society | 综合与内科医学 (SCIE) | 综合与内科医学: Q1 | 84.5 |
| [Signal Transduction and Targeted Therapy](https://www.nature.com/sigtrans/) | Springer Nature | 生物化学与分子生物学 (SCIE)<br>细胞生物学 (SCIE) | 生物化学与分子生物学: Q1<br>细胞生物学: Q1 | 81.2 |
| [Annals of Oncology](https://www.annalsofoncology.org/content/authorinfo) | European Society for Medical Oncology · Elsevier | 肿瘤学 (SCIE) | 肿瘤学: Q1 | 80.4 |
| [Nature Reviews Disease Primers](https://www.nature.com/nrdp/content) | Springer Nature · Nature Portfolio | 综合与内科医学 (SCIE) | 综合与内科医学: Q1 | 79.8 |
| [World Psychiatry](https://onlinelibrary.wiley.com/page/journal/20515545/homepage/forauthors.html) | World Psychiatric Association · Wiley | 精神病学 (SCIE, SSCI) | 精神病学: Q1 | 79.5 |
| [JAMA](https://jamanetwork.com/journals/jama/pages/instructions-for-authors) | American Medical Association | 综合与内科医学 (SCIE) | 综合与内科医学: Q1 | 65.4 |
| [Nature Reviews Cancer](https://www.nature.com/nrc/content) | Springer Nature · Nature Portfolio | 肿瘤学 (SCIE) | 肿瘤学: Q1 | 60.7 |
| [Cancer Cell](https://www.cell.com/cancer-cell/home) | Elsevier · Cell Press | 细胞生物学 (SCIE)<br>肿瘤学 (SCIE) | 细胞生物学: Q1<br>肿瘤学: Q1 | 56.1 |
| [Nature](https://www.nature.com/nature/for-authors/formatting-guide) | Springer Nature · Nature Portfolio | 综合科学 (SCIE) | 综合科学: Q1 | 56.1 |
| [The BMJ](https://www.bmj.com/about-bmj/resources-authors/article-types) | BMJ Group | 综合与内科医学 (SCIE) | 综合与内科医学: Q1 | 55.1 |
| [The Lancet Neurology](https://www.thelancet.com/journals/laneur/home) | Elsevier · The Lancet Group | 临床神经病学 (SCIE) | 临床神经病学: Q1 | 54.6 |
| [Nature Medicine](https://www.nature.com/nm/content) | Springer Nature · Nature Portfolio | 生物化学与分子生物学 (SCIE)<br>细胞生物学 (SCIE)<br>实验与研究医学 (SCIE) | 生物化学与分子生物学: Q1<br>细胞生物学: Q1<br>实验与研究医学: Q1 | 52.5 |
| [Nature Reviews Genetics](https://www.nature.com/nrg/content) | Springer Nature · Nature Portfolio | 遗传学与遗传 (SCIE) | 遗传学与遗传: Q1 | 51.4 |
| [Nature Reviews Cardiology](https://www.nature.com/nrcardio/content) | Springer Nature · Nature Portfolio | 心脏与心血管系统 (SCIE) | 心脏与心血管系统: Q1 | 50.2 |
| [Science](https://www.science.org/content/page/science-information-authors) | AAAS | 综合科学 (SCIE) | 综合科学: Q1 | 47.3 |
| [Nature Reviews Immunology](https://www.nature.com/nri/content) | Springer Nature · Nature Portfolio | 免疫学 (SCIE) | 免疫学: Q1 | 47.1 |
| [European Heart Journal](https://academic.oup.com/eurheartj/pages/General_Instructions) | European Society of Cardiology · Oxford University Press | 心脏与心血管系统 (SCIE) | 心脏与心血管系统: Q1 | 45.3 |
| [Cell](https://www.cell.com/cell/home) | Elsevier · Cell Press | 生物化学与分子生物学 (SCIE)<br>细胞生物学 (SCIE) | 生物化学与分子生物学: Q1<br>细胞生物学: Q1 | 45.1 |
| [Journal of Clinical Oncology](https://ascopubs.org/jco/authors/manuscript-guidelines) | American Society of Clinical Oncology | 肿瘤学 (SCIE) | 肿瘤学: Q1 | 44.7 |
| [Nature Biotechnology](https://www.nature.com/nbt/content) | Springer Nature · Nature Portfolio | 生物技术与应用微生物学 (SCIE) | 生物技术与应用微生物学: Q1 | 44.5 |
| [Nature Reviews Bioengineering](https://www.nature.com/natrevbioeng/content) | Springer Nature | 生物医学工程 (SCIE)<br>材料科学：生物材料 (SCIE) | 生物医学工程: Q1<br>材料科学：生物材料: Q1 | 42.7 |
| [Molecular Cancer](https://molecular-cancer.biomedcentral.com/submission-guidelines) | Springer Nature · BMC | 生物化学与分子生物学 (SCIE)<br>肿瘤学 (SCIE) | 生物化学与分子生物学: Q1<br>肿瘤学: Q1 | 42.2 |
| [Circulation](https://www.ahajournals.org/circ/author-instructions) | American Heart Association · Wolters Kluwer | 心脏与心血管系统 (SCIE)<br>外周血管疾病 (SCIE) | 心脏与心血管系统: Q1<br>外周血管疾病: Q1 | 41.3 |
| [Journal of Hepatology](https://www.journal-of-hepatology.eu/content/authorinfo) | European Association for the Study of the Liver · Elsevier | 胃肠病学与肝病学 (SCIE) | 胃肠病学与肝病学: Q1 | 40.1 |
| [Nature Reviews Endocrinology](https://www.nature.com/nrendo/content) | Springer Nature · Nature Portfolio | 内分泌与代谢 (SCIE) | 内分泌与代谢: Q1 | 39.1 |
| [The Lancet Gastroenterology & Hepatology](https://www.thelancet.com/journals/langas/home) | Elsevier · The Lancet Group | 胃肠病学与肝病学 (SCIE) | 胃肠病学与肝病学: Q1 | 39.1 |
| [Nature Nanotechnology](https://www.nature.com/nnano/content) | Springer Nature · Nature Portfolio | 综合材料科学 (SCIE)<br>纳米科学与纳米技术 (SCIE) | 综合材料科学: Q1<br>纳米科学与纳米技术: Q1 | 37.5 |
| [Cell Metabolism](https://www.cell.com/cell-metabolism/home) | Elsevier · Cell Press | 细胞生物学 (SCIE)<br>内分泌与代谢 (SCIE) | 细胞生物学: Q1<br>内分泌与代谢: Q1 | 37.0 |
| [The Lancet Diabetes & Endocrinology](https://www.thelancet.com/journals/landia/home) | Elsevier · The Lancet Group | 内分泌与代谢 (SCIE) | 内分泌与代谢: Q1 | 36.3 |
| [Physiological Reviews](https://journals.physiology.org/author-info.physrev) | American Physiological Society | 生理学 (SCIE) | 生理学: Q1 | 35.7 |
| [The Lancet Respiratory Medicine](https://www.thelancet.com/journals/lanres/home) | Elsevier · The Lancet Group | 重症医学 (SCIE)<br>呼吸系统 (SCIE) | 重症医学: Q1<br>呼吸系统: Q1 | 34.7 |
| [Nature Reviews Rheumatology](https://www.nature.com/nrrheum/content) | Springer Nature · Nature Portfolio | 风湿病学 (SCIE) | 风湿病学: Q1 | 33.7 |
| [The Lancet Oncology](https://www.thelancet.com/journals/lanonc/home) | Elsevier · The Lancet Group | 肿瘤学 (SCIE) | 肿瘤学: Q1 | 33.7 |
| [Molecular Plant](https://www.cell.com/molecular-plant/home) | Elsevier · Cell Press | 生物化学与分子生物学 (SCIE)<br>植物科学 (SCIE) | 生物化学与分子生物学: Q1<br>植物科学: Q1 | 32.7 |
| [Nature Reviews Neurology](https://www.nature.com/nrneurol/content) | Springer Nature · Nature Portfolio | 临床神经病学 (SCIE) | 临床神经病学: Q1 | 31.2 |
| [Cell Research](https://www.nature.com/cr/authors-and-referees) | Springer Nature | 细胞生物学 (SCIE) | 细胞生物学: Q1 | 31.1 |
| [Immunity](https://www.cell.com/immunity/home) | Elsevier · Cell Press | 免疫学 (SCIE) | 免疫学: Q1 | 30.6 |
| [Gastroenterology](https://www.gastrojournal.org/content/authorinfo) | American Gastroenterological Association · Elsevier | 胃肠病学与肝病学 (SCIE) | 胃肠病学与肝病学: Q1 | 29.7 |
| [Cancer Discovery](https://aacrjournals.org/cancerdiscovery/pages/instructions-for-authors) | American Association for Cancer Research | 肿瘤学 (SCIE) | 肿瘤学: Q1 | 29.5 |
| [The Lancet Infectious Diseases](https://www.thelancet.com/journals/laninf/home) | Elsevier · The Lancet Group | 感染病学 (SCIE) | 感染病学: Q1 | 29.4 |
| [European Urology](https://www.europeanurology.com/content/authorinfo) | European Association of Urology · Elsevier | 泌尿学与肾脏学 (SCIE) | 泌尿学与肾脏学: Q1 | 29.1 |
| [Nature Reviews Neuroscience](https://www.nature.com/nrn/content) | Springer Nature · Nature Portfolio | 神经科学 (SCIE) | 神经科学: Q1 | 29.0 |
| [Cancer Communications](https://onlinelibrary.wiley.com/page/journal/25233548/homepage/forauthors.html) | AAAS | 肿瘤学 (SCIE) | 肿瘤学: Q1 | 28.4 |
| [Nature Methods](https://www.nature.com/nmeth/content) | Springer Nature · Nature Portfolio | 生化研究方法 (SCIE) | 生化研究方法: Q1 | 28.3 |
| [Nature Cancer](https://www.nature.com/natcancer/content) | Springer Nature · Nature Portfolio | 肿瘤学 (SCIE) | 肿瘤学: Q1 | 28.0 |
| [Nature Metabolism](https://www.nature.com/natmetab/content) | Springer Nature · Nature Portfolio | 内分泌与代谢 (SCIE) | 内分泌与代谢: Q1 | 27.5 |
| [Nature Immunology](https://www.nature.com/ni/content) | Springer Nature · Nature Portfolio | 免疫学 (SCIE) | 免疫学: Q1 | 26.5 |
| [The Lancet Public Health](https://www.thelancet.com/journals/lanpub/home) | Elsevier · The Lancet Group | 公共、环境与职业健康 (SCIE, SSCI) | 公共、环境与职业健康: Q1 | 26.5 |
| [JAMA Internal Medicine](https://jamanetwork.com/journals/jamainternalmedicine/pages/instructions-for-authors) | American Medical Association | 综合与内科医学 (SCIE) | 综合与内科医学: Q1 | 26.3 |
| [Nature Biomedical Engineering](https://www.nature.com/natbiomedeng/submission-guidelines/aip-and-formatting) | Springer Nature · Nature Portfolio | 生物医学工程 (SCIE) | 生物医学工程: Q1 | 26.3 |
| [Nature Genetics](https://www.nature.com/ng/content) | Springer Nature · Nature Portfolio | 遗传学与遗传 (SCIE) | 遗传学与遗传: Q1 | 25.5 |
| [The Lancet Digital Health](https://www.thelancet.com/journals/landig/home) | Elsevier · The Lancet Group | 医学信息学 (SCIE)<br>综合与内科医学 (SCIE) | 医学信息学: Q1<br>综合与内科医学: Q1 | 25.5 |
| [Trends in Cell Biology](https://www.cell.com/trends/cell-biology/home) | Elsevier · Cell Press | 细胞生物学 (SCIE) | 细胞生物学: Q1 | 25.3 |
| [Nature Aging](https://www.nature.com/nataging/content) | Springer Nature | 细胞生物学 (SCIE)<br>老年医学与老年学 (SCIE)<br>神经科学 (SCIE) | 细胞生物学: Q1<br>老年医学与老年学: Q1<br>神经科学: Q1 | 25.0 |
| [Blood](https://ashpublications.org/blood/pages/manuscript_types) | American Society of Hematology | 血液学 (SCIE) | 血液学: Q1 | 23.9 |
| [Cellular & Molecular Immunology](https://www.nature.com/cmi/authors-and-referees) | Chinese Society for Immunology · Springer Nature | 免疫学 (SCIE) | 免疫学: Q1 | 23.9 |
| [JAMA Oncology](https://jamanetwork.com/journals/jamaoncology/pages/instructions-for-authors) | American Medical Association | 肿瘤学 (SCIE) | 肿瘤学: Q1 | 23.9 |
| [JAMA Neurology](https://jamanetwork.com/journals/jamaneurology/pages/instructions-for-authors) | American Medical Association | 临床神经病学 (SCIE) | 临床神经病学: Q1 | 23.6 |
| [Cell Stem Cell](https://www.cell.com/cell-stem-cell/home) | Elsevier · Cell Press | 细胞与组织工程 (SCIE)<br>细胞生物学 (SCIE) | 细胞与组织工程: Q1<br>细胞生物学: Q1 | 23.3 |
| [Cell Host & Microbe](https://www.cell.com/cell-host-microbe/home) | Elsevier · Cell Press | 微生物学 (SCIE)<br>寄生虫学 (SCIE)<br>病毒学 (SCIE) | 微生物学: Q1<br>寄生虫学: Q1<br>病毒学: Q1 | 23.2 |
| [Nature Cell Biology](https://www.nature.com/ncb/content) | Springer Nature · Nature Portfolio | 细胞生物学 (SCIE) | 细胞生物学: Q1 | 22.7 |
| [Cancer Research](https://aacrjournals.org/cancerres/pages/instructions-for-authors) | American Association for Cancer Research | 肿瘤学 (SCIE) | 肿瘤学: Q1 | 22.6 |
| [The Lancet Global Health](https://www.thelancet.com/journals/langlo/home) | Elsevier · The Lancet Group | 公共、环境与职业健康 (SCIE, SSCI) | 公共、环境与职业健康: Q1 | 22.5 |
| [Journal of the American College of Cardiology](https://www.jacc.org/author-center) | American College of Cardiology · Elsevier | 心脏与心血管系统 (SCIE) | 心脏与心血管系统: Q1 | 22.3 |
| [The Lancet Microbe](https://www.thelancet.com/journals/lanmic/home) | Elsevier · The Lancet Group | 感染病学 (SCIE)<br>微生物学 (SCIE) | 感染病学: Q1<br>微生物学: Q1 | 21.9 |
| [Trends in Cancer](https://www.cell.com/trends/cancer/home) | Elsevier · Cell Press | 肿瘤学 (SCIE) | 肿瘤学: Q1 | 21.6 |
| [The Lancet Psychiatry](https://www.thelancet.com/journals/lanpsy/home) | Elsevier · The Lancet Group | 精神病学 (SCIE, SSCI) | 精神病学: Q1 | 21.1 |
| [The Lancet Planetary Health](https://www.thelancet.com/journals/lanplh/home) | Elsevier · The Lancet Group | 环境科学 (SCIE)<br>公共、环境与职业健康 (SCIE, SSCI) | 环境科学: Q1<br>公共、环境与职业健康: Q1 | 20.5 |
| [The Lancet Haematology](https://www.thelancet.com/journals/lanhae/home) | Elsevier · The Lancet Group | 血液学 (SCIE) | 血液学: Q1 | 20.4 |
| [Nature Neuroscience](https://www.nature.com/neuro/content) | Springer Nature · Nature Portfolio | 神经科学 (SCIE) | 神经科学: Q1 | 20.3 |
| [Nature Microbiology](https://www.nature.com/nmicrobiol/content) | Springer Nature · Nature Portfolio | 微生物学 (SCIE) | 微生物学: Q1 | 18.7 |
| [Nature Communications](https://www.nature.com/ncomms/submit/article) | Springer Nature · Nature Portfolio | 综合科学 (SCIE) | 综合科学: Q1 | 18.1 |
| [npj Digital Medicine](https://www.nature.com/npjdigitalmed/submission-guidelines) | Springer Nature · Nature Portfolio | 卫生保健科学与服务 (SCIE)<br>医学信息学 (SCIE) | 卫生保健科学与服务: Q1<br>医学信息学: Q1 | 18.0 |
| [Neuron](https://www.cell.com/neuron/home) | Elsevier · Cell Press | 神经科学 (SCIE) | 神经科学: Q1 | 16.9 |
| [Science Immunology](https://www.science.org/journal/sciimmunol/information-for-authors) | AAAS | 免疫学 (SCIE) | 免疫学: Q1 | 16.4 |
| [Molecular Cell](https://www.cell.com/molecular-cell/home) | Elsevier · Cell Press | 生物化学与分子生物学 (SCIE)<br>细胞生物学 (SCIE) | 生物化学与分子生物学: Q1<br>细胞生物学: Q1 | 16.0 |
| [Science Translational Medicine](https://www.science.org/journal/stm/information-for-authors) | AAAS | 细胞生物学 (SCIE)<br>实验与研究医学 (SCIE) | 细胞生物学: Q1<br>实验与研究医学: Q1 | 15.6 |
| [Nucleic Acids Research](https://academic.oup.com/nar/pages/author-guidelines) | Oxford University Press | 生物化学与分子生物学 (SCIE) | 生物化学与分子生物学: Q1 | 15.0 |
| [Cell Reports Medicine](https://www.cell.com/cell-reports-medicine/home) | Elsevier · Cell Press | 细胞生物学 (SCIE)<br>实验与研究医学 (SCIE) | 细胞生物学: Q1<br>实验与研究医学: Q1 | 14.0 |
| [Science Advances](https://www.science.org/journal/sciadv/information-for-authors) | AAAS | 综合科学 (SCIE) | 综合科学: Q1 | 13.9 |
| [Nature Structural & Molecular Biology](https://www.nature.com/nsmb/content) | Springer Nature · Nature Portfolio | 生物化学与分子生物学 (SCIE)<br>生物物理学 (SCIE)<br>细胞生物学 (SCIE) | 生物化学与分子生物学: Q1<br>生物物理学: Q1<br>细胞生物学: Q1 | 10.1 |
| [Proceedings of the National Academy of Sciences](https://www.pnas.org/author-center/submitting-your-manuscript) | National Academy of Sciences | 综合科学 (SCIE) | 综合科学: Q1 | 9.5 |
| [Developmental Cell](https://www.cell.com/developmental-cell/home) | Elsevier · Cell Press | 细胞生物学 (SCIE)<br>发育生物学 (SCIE) | 细胞生物学: Q1<br>发育生物学: Q1 | 9.2 |
| [Genome Biology](https://genomebiology.biomedcentral.com/submission-guidelines) | Springer Nature · BMC | 生物技术与应用微生物学 (SCIE)<br>遗传学与遗传 (SCIE) | 生物技术与应用微生物学: Q1<br>遗传学与遗传: Q1 | 9.2 |
| [The EMBO Journal](https://www.embopress.org/page/journal/14602075/authorguide) | Springer Nature | 生物化学与分子生物学 (SCIE)<br>细胞生物学 (SCIE) | 生物化学与分子生物学: Q1<br>细胞生物学: Q1 | 8.4 |
| [Current Biology](https://www.cell.com/current-biology/home) | Elsevier · Cell Press | 生物化学与分子生物学 (SCIE)<br>生物学 (SCIE)<br>细胞生物学 (SCIE) | 生物化学与分子生物学: Q1<br>生物学: Q1<br>细胞生物学: Q1 | 7.7 |
| [Scientific Data](https://www.nature.com/sdata/publish/submission-guidelines) | Springer Nature · Nature Portfolio | 综合科学 (SCIE) | 综合科学: Q1 | 7.2 |
| [Science Signaling](https://www.science.org/journal/signaling/information-for-authors) | AAAS | 生物化学与分子生物学 (SCIE)<br>细胞生物学 (SCIE) | 生物化学与分子生物学: Q1<br>细胞生物学: Q1 | 7.0 |
| [PLOS Biology](https://journals.plos.org/plosbiology/s/submission-guidelines) | Public Library of Science | 生物化学与分子生物学 (SCIE)<br>生物学 (SCIE) | 生物化学与分子生物学: Q1<br>生物学: Q1 | 6.9 |
| [Molecular Systems Biology](https://www.embopress.org/page/journal/17444292/authorguide) | Springer Nature | 生物化学与分子生物学 (SCIE) | 生物化学与分子生物学: Q1 | 6.7 |
| [Genome Research](https://genome.cshlp.org/site/misc/ifora.xhtml) | Cold Spring Harbor Laboratory Press | 生物化学与分子生物学 (SCIE)<br>生物技术与应用微生物学 (SCIE)<br>遗传学与遗传 (SCIE) | 生物化学与分子生物学: Q1<br>生物技术与应用微生物学: Q1<br>遗传学与遗传: Q1 | 6.3 |
| [Communications Biology](https://www.nature.com/commsbio/submission-guidelines) | Springer Nature · Nature Portfolio | 生物学 (SCIE) | 生物学: Q1 | 5.8 |
| [Bioinformatics](https://academic.oup.com/bioinformatics/pages/author-guidelines) | Oxford University Press | 生化研究方法 (SCIE)<br>生物技术与应用微生物学 (SCIE)<br>数学与计算生物学 (SCIE) | 生化研究方法: Q1<br>生物技术与应用微生物学: Q1<br>数学与计算生物学: Q1 | 5.5 |
| [eLife](https://elifesciences.org/articles/research-article) | eLife Sciences Publications | 生物学 (ESCI) | 生物学: Not ranked | 未获分配 |
<!-- journal-coverage-table:end -->

影响因子与分区只用于描述期刊生态和辅助人工比较，不进入自动推荐评分，也不用于预测接收概率。

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

新增期刊必须具备与现有条目相同的完整记录，不能只添加名称与网址。稿件始终绑定所选规范版本，后续说明变化不会静默改写早期审查结论。
