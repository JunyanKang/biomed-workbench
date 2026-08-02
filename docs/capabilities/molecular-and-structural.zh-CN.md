# 分子与结构生物学

语言：[中文](molecular-and-structural.zh-CN.md) · [English](molecular-and-structural.md)

## 科学角色

这一能力层把序列、化学、互作网络和三维结构证据连接为可检验的分子假设。设计计算、数据库记录、预测结构、实验结构、对接结果与验证实验分别登记，避免把某一层的置信度误写成另一层的证据。

## 序列、构建与分子证据

工作台覆盖序列检查与比对、ORF、引物与 PCR、CRISPR、限制性内切酶与 Golden Gate、GenBank CDS 提取、糖基化位点、酶动力学、ITC、UniProt、PubChem、RCSB PDB、AlphaFold DB 与蛋白无序倾向证据。每项结果保留分子身份、方向、坐标、算法版本、参数与适用范围。

## 结构质量与比较

`structure-quality-assessment` 检查坐标完整性、替代构象、占有率以及 B-factor 或 pLDDT 的正确语义；`structure-chain-comparison` 记录链对应、序列覆盖、刚体变换和独立核对的 RMSD；`protein-secondary-structure` 通过实际 DSSP 运行分配二级结构；`structure-interactive-visualization` 生成带来源记录的交互视图。结构相似性用于形成假设，不直接等于功能等价。

## 蛋白互作网络

`protein-interaction-network-evidence` 通过 STRING 12.0 进行标识符映射，明确区分功能关联网络和物理互作子网络，记录映射损失、各证据通道得分以及提交蛋白集合的互作富集。交付包含节点表、边表、Cytoscape 样式、PDF/SVG/600-dpi PNG 和带文件指纹的复绘清单。STRING 网络适合候选优先级和系统背景分析，不能单独证明直接结合。

## 复合物预测与分子对接

- `protein-complex-docking` 使用 HADDOCK3 执行闭合的约束驱动复合物对接流程，严格区分小型集成测试和研究级采样。完整保留模型、簇、HADDOCK score、需要参考结构的 DockQ 指标和 PRODIGY 亲和力估计，并输出界面接触、残基坐标、标准化模型评分、PyMOL 可编辑场景与发表级图件。
- `alphafold3-complex-prediction` 为蛋白、RNA、DNA 和配体建立官方 AlphaFold 3 输入；在用户具备合规权重、版本化数据库和 Linux GPU 环境时连接本地推理，或审查已有官方输出。结果包含排序与置信度表、模型文件及 PDF/SVG/600-dpi PNG。项目不打包权重，也不通过未公开接口自动操作公共服务器。

AlphaFold 3 更适合提出共同折叠的复合物构象并评价模型置信度；HADDOCK3 更适合在明确的物理或实验约束下采样结合模式。二者一致可提高验证优先级，但仍需生化、生物物理或细胞实验确认互作、亲和力和功能。

## MSBio2、Metascape 与 Cytoscape

`metascape-msbio-network-analysis` 可以调用用户合规持有的本地 MSBio2 包装程序，也可以核查已有的完整 Metascape 结果目录。模块统一核对富集工作簿、GO/PPI 网络、MCODE 组分、报告和图件；配套 Cytoscape renderer 通过 CyREST 导入通过核查的 XGMML，应用固定样式和布局，输出可编辑 `.cys` 会话以及 PDF/SVG/PNG。许可证、私有路径和用户结果不会进入公开仓库。若 Cytoscape 由本次任务启动，任务在保存会话并核验全部导出后必须正常退出该进程并确认其消失；用户原本已经打开的 Cytoscape 会话不会被关闭。

## 发表级结构图与自主复绘

结构与对接模块遵循统一的终稿尺寸规范：色盲友好的链颜色，5–7 pt 字号，至少 0.5 pt 线宽，坐标、距离和置信度单位完整，分子视图图例置于图外，PDF/SVG 保留可编辑文字，并同时输出 600-dpi PNG。标准图组包括复合物总览、界面残基接触图、完整模型质量概览，以及在数据允许时提供的置信度或 PAE 图。每个图件都绑定精确的复绘表、源文件指纹、样式版本和可编辑分子场景；用户可以自行重画，工作台也会直接生成可用于稿件排版的基础图组。

## 科学门控

对接分数不等于亲和力，pLDDT 不等于实验确定性，B-factor 与预测置信度不能混用，网络边不自动等于直接互作，漂亮的复合物视图也不是机制证据。缺失原子、链映射错误、非标准残基、参考结构不匹配、采样不足、分数语义不明和结果目录不完整都会阻止对应结论进入科学证据地图。

## 典型交付

序列与构建设计、分子身份档案、STRING 节点/边证据、结构清单与质量报告、链比较、AlphaFold 3 置信度审查、HADDOCK3 模型与界面账本、Metascape 富集和 Cytoscape 会话、发表级结构图与复绘数据、机制假设及优先验证实验。
