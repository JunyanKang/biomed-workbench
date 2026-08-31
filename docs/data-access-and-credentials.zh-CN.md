# 公共数据库访问与凭据

版本：`2026.08.31`
适用范围：当前 Biomed Workbench 实际实现并列入允许访问清单的公共服务端点。

“一个数据库是否需要 API key”必须具体到服务与端点。数据库网站可能同时包含公开检索、登录后的个人功能、付费接口或私有部署；工作台只声明自身当前调用的端点，不用一个结论代替整个数据库生态。

## 当前结论

- **必须提供 API key 才能运行的当前数据库模块：无。**
- **可选 API key：`NCBI_API_KEY`。** 同一密钥可用于 NCBI E-utilities 和 NCBI Datasets，提高请求容量；没有密钥时仍可访问公开端点。
- **需要网页账号的分析服务：AlphaFold Server。** 它使用 Google 账号在官方网页交互登录，不提供工作台可调用的公开提交 API。工作台生成官方 JSON 提交包，用户核对后手动上传和提交；只记录访问状态，不保存账号密码、OAuth 令牌、cookie 或浏览器会话。
- **可能需要机构登录的全文来源：出版平台与图书馆入口。** 用户在官方或机构页面完成登录与安全检查；工作台只记录取得了 PDF、HTML 全文、摘要或元数据，以及文件核对结果，不接收登录凭据或浏览器会话。
- **当前未启用的付费或私有凭据：** Crossref Metadata Plus token、私有 cBioPortal 的 OAuth/token 等。它们不能被误写成当前公开客户端的必要条件。
- 其他当前客户端使用官方公开端点，不接收凭据；访问仍受服务条款、合理请求频率、版本变化和数据许可约束。

## 服务级访问清单

| 服务 | 工作台当前用途 | 当前端点凭据状态 | 需要注意 |
| --- | --- | --- | --- |
| NCBI E-utilities | PubMed、Gene、dbSNP、ClinVar 等检索和摘要 | `NCBI_API_KEY` 可选 | 官方限制通常为无 key 每秒 3 次、有 key 每秒 10 次；Agent 仍需退避和限速 |
| NCBI Datasets v2 | Gene ortholog 记录 | `NCBI_API_KEY` 可选 | 官方默认每秒 5 次，有 key 每秒 10 次；工作台已支持同一 NCBI key |
| Crossref REST | DOI 元数据 | 当前公开访问无需 token | 推荐提供联系邮箱进入 polite pool；邮箱不是密钥。Metadata Plus token 属于付费服务，当前客户端不使用 |
| Europe PMC REST | 文献元数据与开放内容状态 | 当前公开端点无需 key | 全文访问仍取决于开放获取状态 |
| 出版平台与机构图书馆入口 | 用户已获授权的论文全文 | 可能需要用户在网页交互登录；不是工作台 API key | 遇到登录、验证码或安全检查时由用户完成；只保留访问结果和文件核对信息 |
| bioRxiv API | 预印本元数据 | 当前公开端点无需 key | 预印本必须保留未同行评议标记 |
| ClinicalTrials.gov API v2 | 试验记录 | 当前公开端点无需 key | 数据结构和版本会更新，应记录 API 数据时间戳 |
| UniProt REST / ID Mapping | 蛋白记录与标识符映射 | 当前公开端点无需 key | 批量任务使用异步作业和合理轮询 |
| Ensembl REST | 基因身份、坐标与注释信息 | 当前公开端点无需 key | 记录 assembly 与 annotation release |
| Reactome Content/Analysis | 通路记录与富集上下文 | 当前公开端点无需 key | 记录数据库 release；旧 REST 已由 Content Service 取代 |
| Open Targets GraphQL | target–disease 证据 | 当前公开端点无需 key | 大规模查询应转向官方数据下载或 BigQuery |
| gnomAD GraphQL | 基因约束等公开汇总 | 当前公开端点无需 key | 记录数据版本、参考基因组和人群范围 |
| cBioPortal 公共门户 | 研究、突变、拷贝数和覆盖记录 | `www.cbioportal.org` 公共 API 无需认证 | 私有 cBioPortal 可以配置 OAuth/token；当前客户端不会把公共凭据自动用于私有实例 |
| PubChem PUG REST | 化合物与结构信息 | 不提供 API key 或白名单 | 官方要求合理限速，典型动态上限为每秒 5 次 |
| RCSB PDB Data/Search | 结构记录与检索 | 当前公开端点无需 key | 结构记录并不自动证明生理构象或功能 |
| AlphaFold DB API | 公开预测结构记录 | 当前公开端点无需 key | 保留模型版本和置信度；预测不是实验结构 |
| AlphaFold Server | 蛋白、核酸、配体复合物结构预测 | 需要 Google 账号网页登录；不是 API key | 用户手动提交；非商业用途；序列和结果可能被长期保留；Server 输出不得用于自动化配体/肽对接或互作预测 |
| QuickGO | GO 术语记录 | 当前公开端点无需 key | 记录 ontology release 与证据代码 |
| Enrichr | 基因集目录与成员 | 当前公开端点无需 key | 记录库名称和检索时间；库更新会改变结果 |
| ARCHS4 | 公开表达上下文 | 当前公开端点无需 key | 汇总表达只能作为背景证据，不能替代项目统计设计 |
| HPO API | 表型术语 | 当前公开端点无需 key | 记录术语版本与映射状态 |
| IUPred2A | 蛋白无序倾向 | 当前公开端点无需 key | 记录算法模式与版本；结果是计算预测 |
| GWAS Catalog REST v2 | 按性状发现研究、按映射基因检索关联 | 当前公开端点无需 key | 顶级关联与邻近或映射基因不是完整汇总统计，也不自动确定效应基因 |
| ChEMBL Data Web Services | 化合物身份和生物活性记录 | 当前公开端点无需 key | 活性记录需按 assay、endpoint、单位和置信度分别复核 |
| PRIDE Archive | 蛋白质组公共项目发现 | 当前公开端点无需 key | 复用前核对原始文件、样本设计、物种和处理流程 |
| BioStudies / ArrayExpress | 多组学及历史 ArrayExpress 数据集发现 | 当前公开端点无需 key | 检索命中后需进入 accession 级文件与设计审查 |
| ENCODE Portal | 功能基因组实验与文件发现 | 当前公开端点无需 key | 核对 biosample、assay、control、assembly、处理层级与 portal audit 状态 |
| Human Protein Atlas | 人体组织和细胞表达背景 | 当前公开端点无需 key | 表达与抗体记录是背景观察，不直接证明功能或疾病机制 |
| MGnify | 微生物组研究和 biome 发现 | 当前公开端点无需 key | 比较前核对提取、测序、宿主去除、分类数据库和 biome 定义 |

官方入口包括：[NCBI E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25497/)、[NCBI Datasets API keys](https://www.ncbi.nlm.nih.gov/datasets/docs/v2/api/api-keys/)、[Crossref access and authentication](https://crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/)、[Europe PMC REST](https://europepmc.org/RestfulWebService)、[ClinicalTrials.gov API](https://clinicaltrials.gov/data-api/api)、[UniProt programmatic access](https://www.uniprot.org/help/programmatic_access)、[Reactome Content Service](https://reactome.org/dev/content-service)、[Open Targets GraphQL](https://platform-docs.opentargets.org/data-access/graphql-api)、[GWAS Catalog API](https://www.ebi.ac.uk/gwas/rest/api/v2/docs)、[ChEMBL Web Services](https://chembl.gitbook.io/chembl-interface-documentation/web-services/chembl-data-web-services)、[PRIDE Archive API](https://www.ebi.ac.uk/pride/ws/archive/v2/docs/api-guide.html)、[BioStudies API](https://www.ebi.ac.uk/biostudies/help)、[ENCODE REST API](https://www.encodeproject.org/help/rest-api/)、[Human Protein Atlas downloads](https://www.proteinatlas.org/about/download)、[MGnify API](https://www.ebi.ac.uk/metagenomics/api/v1/docs/)、[cBioPortal public API](https://www.cbioportal.org/api/swagger-ui/index.html)、[cBioPortal private token authentication](https://docs.cbioportal.org/deployment/authorization-and-authentication/authenticating-users-via-tokens/)、[PubChem PUG REST](https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest)、[AlphaFold Server](https://alphafoldserver.com/)、[输出使用条款](https://alphafoldserver.com/output-terms) 和 [隐私说明](https://alphafoldserver.com/privacy)。

## 如何配置

推荐直接对 Codex 或其他受信任的智能体说：

> 检查这个项目要访问的公共数据库及当前凭据状态。如果 NCBI 任务需要更高请求容量，请在隐藏输入中引导我配置 NCBI API key；不要让我把密钥贴进聊天、项目文件或报告，并在配置后只告诉我凭据来源和是否生效。

> 检查 AlphaFold Server 访问状态。若未登录、登录错误、会话过期、无权限、额度用尽或尚未确认条款，请告诉我具体状态并打开官方登录页面；不要保存或复述我的 Google 密码。先生成提交包，待我逐项核对后再手动提交。

智能体应先说明是否真的需要凭据，再打开隐藏输入。AlphaFold Server 的 Google 登录必须在官方网页完成；智能体只记录可用、登录错误、会话过期、无权限、额度用尽或条款未确认等状态和检查时间。用户不需要编写命令。

### 可选择的保存方式

1. **本次任务临时使用**：适合集群、自动化和短期任务，由安全的环境变量或作业密钥注入；任务结束后失效。
2. **本机用户级保存**：适合个人工作站。智能体通过隐藏输入把密钥保存到项目目录之外的用户配置文件，并限制文件权限。
3. **机构密钥管理器**：适合服务器或团队环境。智能体读取机构批准的安全凭据，不复制密钥到项目。

本机用户级文件位于操作系统的用户配置目录，优先级低于本次任务的安全环境变量。状态检查只显示“已配置／未配置”和来源，不显示值。

## 轮换、删除与审计

可以直接告诉智能体：

- “检查 NCBI key 是否生效，但不要显示它。”
- “把 NCBI key 换成新的，确认旧值不再被读取。”
- “删除本机保存的 NCBI key，保留项目数据。”
- “审计仓库、报告和证据地图，确认没有凭据残留。”

密钥不得进入聊天文本、版本库、项目文件、样本表、运行日志、图表、报告或科学证据地图。账号密码、OAuth 令牌、浏览器 cookie 与恢复信息也不得进入工作台的访问状态记录。
