# 公共生命科学证据检索与综合

[中文](public-research-evidence.zh-CN.md) · [English](public-research-evidence.md) · [返回能力地图](README.zh-CN.md)

工作台以明确的科学问题访问公共数据库。当前新增的统一入口覆盖 GWAS Catalog、ChEMBL、PRIDE、BioStudies、ENCODE、Human Protein Atlas 和 MGnify，并与已有的 NCBI、Ensembl、UniProt、Open Targets、gnomAD、cBioPortal、Reactome、QuickGO、PubChem、RCSB PDB、AlphaFold DB 等能力共同使用。

每个数据库只开放已经登记的查询类型。例如，GWAS Catalog 可以按性状发现研究或按基因查看关联，ChEMBL 可以检索化合物或指定化合物的活性记录，PRIDE、BioStudies、ENCODE 和 MGnify 用于发现可复用的数据集，Human Protein Atlas 提供人体表达背景。用户不能把任意网址或任意接口路径传给这个入口。

检索结果会保留数据库、查询方式、实际记录、返回是否截断、官方接口说明和该来源能够支持的证据类型。随后 `public-evidence-synthesis` 会核对实体是否一致，并把遗传关联、表达背景、扰动、结构、药理和机制证据分开，而不是把异质记录压成一个看似精确的总分。

公共数据库记录首先服务于候选发现、背景核对、数据集选择和证据补充。进入正式结论前仍需检查物种、基因组版本、样本与研究设计、化学实体、数据库版本、原始论文或数据文件，以及它与本项目观察的对应关系。未检索到记录通常表示当前查询没有返回证据，不能自动解释为该生物学关系不存在。
