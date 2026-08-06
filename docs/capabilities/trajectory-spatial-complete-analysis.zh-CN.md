# 轨迹与空间分析能力契约

语言：[中文](trajectory-spatial-complete-analysis.zh-CN.md) · [English](trajectory-spatial-complete-analysis.md)

## 范围与证据层级

工作台严格区分已注册方法、可执行项目模板和已观察的端到端执行。仅有命令、参数或输出 schema，不足以将某个后端标记为已验证。

| 能力 | 已注册实现 | 进入生物学解读前必需的证据 |
|---|---|---|
| Visium / Visium HD | 官方 SpatialData-IO reader；Space Ranger 几何与图像溯源 | 代表性厂商 bundle、spot/bin 计数、组织分配、图像变换重载 |
| Stereo-seq | 官方 SpatialData-IO `stereoseq` reader | 代表性厂商 bundle、bin 尺寸/单位、矩阵与坐标对账 |
| Slide-seq | 坐标显式的 AnnData adapter | bead 位置溯源、物理单位、bead/矩阵标识符对账 |
| Xenium | 官方 SpatialData-IO `xenium` reader | 细胞/转录本/边界对账、阴性对照、未分配转录本和图像变换 |
| CosMx | 官方 SpatialData-IO `cosmx` reader | 细胞/转录本/边界对账、阴性对照、panel 检出和图像变换 |
| MERFISH / MERSCOPE | 官方 SpatialData-IO `merscope` reader 或坐标显式 adapter | 细胞/转录本/边界对账、blank/阴性对照和 panel 检出 |
| 图像分割 | 已有边界、Squidpy watershed 或显式 Cellpose | overlay 复核、边界有效性、形态与转录本分配 |
| 图像配准 | SpatialData 命名变换/标志点或 VALIS | 配准前后 overlay、目标配准误差、往返和形变诊断 |
| 解卷积/映射 | cell2location、RCTD、Tangram 和 SPOTlight 作为相互独立的原生分支 | 参考 signature、共享基因、不确定性/残差、held-out 基因、参考下采样和方法不一致 |
| 空间区域 | BayesSpace、SpaGCN 和 STAGATE 作为独立 benchmark 分支 | 至少三个 seed、不使用标签的稳定性、连贯性、碎片化、运行时间和不一致区域 |
| 空间通讯 | COMMOT 强制使用物理距离截止；spatial CellChat 可作为独立敏感性分支 | 跨样本边数为零、数据库/版本、异源复合体策略、距离敏感性、全局多重性和生物学样本支持 |
| 多切片/三维 | PASTE 用于广泛重叠，PASTE2 用于局部重叠；科学上合理时使用基于图像的 STalign/VALIS | 顺序/间距溯源、coupling/变换、重叠/误差诊断、已校准 xyz 和顺序敏感性 |
| 跨样本空间推断 | `lme4` 模型，section 嵌套于生物学样本 | 每个条件的重复、收敛、非奇异性、效应不确定性和多重性 |

任何解卷积或空间区域方法都不会因为与已复核解剖标签一致而被自动选中。方法原生输出分别保存。当科学上有充分理由构建 consensus 时，必须将其标记为派生的敏感性汇总，且不得取代方法间不一致性报告。

## 统一轨迹与空间图件清单

`biomed_workbench.visualization` 1.2.0 版定义最终尺寸下的字体、线条、符号、坐标轴、图例、色彩与导出规则，并为以下分析声明必需图件清单：

- 轨迹拓扑；
- velocity；
- 命运映射；
- 调控 velocity；
- 平台 QC；
- 核心空间统计；
- 空间解卷积；
- 空间区域 benchmark；
- 距离约束通讯；
- 图像/分割/配准分析；
- 多切片与三维分析。

当任一必需 plot ID 缺少源数据时，R renderer 会拒绝将 profile 标记为完整。它会导出单图和组合 PDF/SVG，以及 600-dpi LZW TIFF，同时记录样式版本、输入 manifest digest 和每个输出 digest。

## 主要实现依据

- SpatialData-IO readers：<https://spatialdata.scverse.org/projects/io/en/stable/api.html>
- 10x Space Ranger：<https://www.10xgenomics.com/support/software/space-ranger/latest>
- 10x Xenium outputs：<https://www.10xgenomics.com/support/software/xenium-ranger/latest/tutorials/outputs/XR-output-overview>
- Squidpy segmentation：<https://squidpy.readthedocs.io/en/stable/api/squidpy.im.segment.html>
- SpatialData transformations：<https://spatialdata.scverse.org/en/latest/api/transformations.html>
- cell2location：<https://www.nature.com/articles/s41587-021-01139-4>
- RCTD：<https://www.nature.com/articles/s41587-021-00830-w>
- Tangram：<https://www.nature.com/articles/s41592-021-01264-7>
- SPOTlight manual：<https://www.bioconductor.org/packages/devel/bioc/manuals/SPOTlight/man/SPOTlight.pdf>
- BayesSpace：<https://www.nature.com/articles/s41587-021-00935-2>
- SpaGCN code：<https://github.com/jianhuupenn/SpaGCN>
- STAGATE：<https://www.nature.com/articles/s41467-022-29439-6>
- spatial-domain benchmark：<https://www.nature.com/articles/s41592-024-02215-8>
- COMMOT：<https://doi.org/10.1038/s41592-022-01728-4>
- VALIS：<https://www.nature.com/articles/s41467-023-40218-9>
- PASTE：<https://www.nature.com/articles/s41592-022-01459-6>
- PASTE2 code：<https://github.com/raphael-group/paste2>
- SPACEL：<https://www.nature.com/articles/s41467-023-43220-3>
- STalign：<https://www.nature.com/articles/s41467-023-43915-7>
- GPSA：<https://www.nature.com/articles/s41592-023-01972-2>
- Nature figure construction guide：<https://research-figure-guide.nature.com/figures/building-and-exporting-figure-panels/>

## 当前已观察执行边界

2026-08-02，Tangram 1.0.4 以 cluster mode 在官方仓库完整测试对上执行参考映射：26,431 个参考细胞、18 个参考类别、9,852 个空间位置和 249 个共享基因。当前模板、基于 RNA count 的 density prior、固定 seed、归一化 projection 和原生 mapping object 均与校验值绑定，并在验收前重新读取。通用坐标显式 H5AD 平台路径、完整 R 空间图件包、缺失图件阻断门控和非奇异跨样本层级模型均已执行并重新读取。所选机器运行时还在官方 Slide-seq vignette 数据上执行了 spacexr/RCTD 2.2.1。其他原生后端保留各自的兼容性和公共数据证据状态；Tangram 或 RCTD 的验收不会转移给其他方法。
