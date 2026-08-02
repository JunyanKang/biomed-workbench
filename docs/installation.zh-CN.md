# 安装与更新

语言：[中文](installation.zh-CN.md) · [English](installation.md)

## 从 GitHub 安装

直接告诉 Codex 或其他兼容智能体：

> 从 `JunyanKang/biomed-workbench` GitHub 仓库安装 Biomed Workbench。使用当前主版本，核对插件身份和科学模块注册表，并向我报告实际安装的版本、来源修订和验证结果。

智能体应当完成仓库来源登记、插件安装和一致性核对。marketplace 名称为 `biomed-workbench`，安装后的包名为 `biomed-workbench@biomed-workbench`。

安装完成后，请开启一个新的 Codex 任务。技能和工具是在任务启动时发现的，已经打开的旧任务通常不会自动加载新安装版本。

## 从完整 Git URL 安装

如果仓库简称不可用，让智能体改用完整地址 `https://github.com/JunyanKang/biomed-workbench`，保持用户指定的分支或发行版本，并执行相同的身份与注册表核对。

## 本地开发安装

开发时，向智能体提供一个稳定的本地目录，让它在该目录使用或克隆仓库、登记这个确切目录、安装插件，并同时报告源码修订和实际加载的插件修订。智能体必须保留工作区内与安装无关的修改，不得用远程分支静默覆盖本地开发版本。

## 更新

拉取目标版本后，使用当前 Codex 版本支持的 plugin 命令重新安装或刷新 marketplace 包。更新后同样需要开启新的 Codex 任务，并确认 skill 列表中出现 `biomed-workbench`。

## 验证安装

让智能体确认 marketplace 与已安装插件均可见，然后开启新任务，使用 Biomed Workbench 执行一个小型科学请求，例如检查 DNA 序列或规划文献检索。智能体在首次使用前运行严格健康检查，并报告插件清单、统一技能入口、模块注册表、路由、凭据策略和生成报告是否一致。

插件核心需要 Python 3.10 或更新版本。启动器会发现兼容解释器，而不是假设系统默认 `python3` 一定合适。具体科学软件和命令版本属于模块级兼容性和 provenance 记录：健康检查不会宣称每个可选分析后端都已安装。

仓库级、发布级和隔离安装检查见：[开发与发布](development.md)。

## 凭据

凭据需求按实际访问端点判断。当前公共模块无需 API key；`NCBI_API_KEY` 对已经实现的 NCBI E-utilities 和 Datasets 请求是可选项，仅用于提高服务容量，不改变科学解释。

用户可以让智能体检查凭据状态、通过隐藏输入配置 NCBI key、只显示仓库外的保存位置、轮换凭据或删除凭据。值不会进入命令参数、模块输入、日志、报告、研究产物或科学证据地图。集群、容器和机构密钥管理方案见[数据访问与凭据](data-access-and-credentials.zh-CN.md)。

## 常见问题

- **看不到 skill：** 安装或更新后开启新的 Codex 任务。
- **marketplace 无法解析：** 检查仓库 URL、分支和 marketplace 名称。
- **核心运行时不可用：** 安装 Python 3.10 或更新版本；workbench 启动器会自动选择。
- **科学后端不可用：** skill 仍可提供规划和路由，但执行证据必须等待兼容项目环境或已验证替代方案。
- **结果被阻断：** 检查提示中指出的输入、兼容性或科学质量门控；被阻断的证据不会被静默提升为结论。
