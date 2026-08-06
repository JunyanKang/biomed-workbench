# 成像与科学可视化

语言：[中文](imaging-and-visualization.zh-CN.md) · [English](imaging-and-visualization.md)

## 科学角色

- 通过有边界的整数平移对齐等尺寸二维图像，并给出明确的重叠和 MSE 诊断；这是基线对齐检查，不是仿射或非刚性配准。

这一能力方向支持定量图像分析与忠实的科学传达。分析性图像产物保持与源数组及其声明的测量语义绑定；传播性素材则与产生证据的分析明确分离。

## 定量成像

- 检查科学图像数组，汇总维度、通道和强度特征。
- 使用明确参数分割图像组分，并返回可测量的组分产物。
- 测量双通道共定位，同时保留方法假设和通道配对。
- 跨帧追踪已声明的点，并保留轨迹层结果。
- 将已校准轨迹转换为路径长度、净位移、速度和方向性，同时保留轨迹长度排除和主张边界。

代表性模块包括 `image-profile`、`image-segment`、`image-colocalization`、`point-tracking` 和 `cell-migration-metrics`。

## 科学可视化

- 从科学主张、图中各部分、数据来源、视觉编码和验证需求定义科学图。
- 通过 Codex 原生图像生成，根据机器可读的简报生成或编辑边界明确的科学插图，并检查实际输出。
- 创建与溯源绑定的交互式蛋白质结构视图。
- 从静态传播素材中移除经过特意设置的均一色键背景，并验证格式与边缘质量。

代表性模块包括 `figure-specification`、`scientific-illustration-generation`、`structure-interactive-visualization` 和 `image-chroma-key-remove`。

## 质量门控

渲染后的传播素材不得取代原始测量。色键输出不作为分割、形态、定位、强度或共定位证据。图像生成不得虚构科学观察。科学图规格必须保留每个已绘主张的方向、不确定性、统计单位和数据来源。

当前注册表提供通用图像分析和科学可视化模块。空间转录组分析见 `single-cell-spatial-analysis` 中的专用组学流程（文档见 [spatial-analysis.md](spatial-analysis.md)）。显微镜文件流程仍有明确范围：工作台聚焦于稳健的测定特异证据流程（profiling、mask、共定位、轨迹和图件），不声称完整覆盖各显微镜厂商的原生 reader 生态。

## 典型交付物

图像 profile、mask 与组分表、共定位统计、点轨迹、分子查看器、科学图规格、插图简报、通过验证的传播素材和图与主张的审查记录。
