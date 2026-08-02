# 公共数据验收案例

公共数据案例用独立发表、来源稳定的数据检验封装流程。每个案例绑定数据来源和校验指纹、模块版本、兼容性组合、分析模板、实际运行环境、参数、质量门控、观察结果、结果重读和推断边界。

当前案例覆盖：

- PDF 证据提取；
- PBMC3k 单细胞基础流程、图谱注释、空液滴与环境 RNA；
- GSE96583 donor-aware pseudobulk、marker、doublet、参考注释、批次整合、细胞通讯与复杂设计；
- 小鼠原肠胚红系轨迹与 velocity；
- 10x PBMC multiome 与 PBMC1k ATAC peak calling；
- ENCODE ATAC-seq 与 DNase-seq、nf-core Ribo-seq/GRO-PRO-seq/iCLIP/WGBS/Hi-C；
- 公开 NET-seq、RIPSeeker PRC2 与 LACE-seq Ago2/IgG 实验专属流程；
- SeqFISH 空间统计；
- spacexr/RCTD 官方 Slide-seq 与 Tangram 官方仓库完整测试数据；
- 斑马鱼 RegVelo 与 CellRank；
- UCSC 坐标转换、NCBI 序列比对、基因身份和跨物种 ortholog；
- 多公共数据库合约；
- 细菌生长、CFU、生物膜和群体模型等定量案例。

每项案例的详细输入、观察数值和边界见 [English public-data case index](README.md)。案例只证明报告中记录的数据、模块版本、模板、运行环境、参数和门控；不能把同一阈值自动推广到另一项目。
