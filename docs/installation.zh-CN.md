# 安装与更新

语言：[中文](installation.zh-CN.md) · [English](installation.md)

## 从 GitHub 安装

将仓库加入 Codex marketplace 并安装插件：

```bash
codex plugin marketplace add JunyanKang/biomed-workbench --ref main
codex plugin add biomed-workbench@biomed-workbench
codex plugin list
```

marketplace 名称是 `biomed-workbench`，安装后的包名是 `biomed-workbench@biomed-workbench`。

安装完成后，请开启一个新的 Codex 任务。技能和工具是在任务启动时发现的，已经打开的旧任务通常不会自动加载新安装版本。

## 从完整 Git URL 安装

```bash
codex plugin marketplace add https://github.com/JunyanKang/biomed-workbench --ref main
codex plugin add biomed-workbench@biomed-workbench
```

## 本地开发安装

开发者可以将仓库 clone 到稳定目录，然后把该目录加入 marketplace：

```bash
mkdir -p ~/plugins
git clone https://github.com/JunyanKang/biomed-workbench ~/plugins/biomed-workbench
codex plugin marketplace add ~/plugins/biomed-workbench
codex plugin add biomed-workbench@biomed-workbench
codex plugin list
```

## 更新

拉取目标版本后，使用当前 Codex 版本支持的 plugin 命令重新安装或刷新 marketplace 包。更新后同样需要开启新的 Codex 任务，并确认 skill 列表中出现 `biomed-workbench`。

## 验证安装

`codex plugin list` 应显示 marketplace 和已安装插件。随后开启新任务，让 Codex 使用 Biomed Workbench 执行一个小型科学请求，例如检查 DNA 序列或规划文献检索。agent 在首次使用前会运行插件健康检查，并报告 manifest、统一 skill、模块注册表、路由和可选凭据策略是否就绪。

维护者可以直接运行同一个健康检查：

```bash
tools/workbench doctor --strict
```

插件核心需要 Python 3.10 或更新版本。启动器会发现兼容解释器，而不是假设系统默认 `python3` 一定合适。具体科学软件和命令版本属于模块级兼容性和 provenance 记录：健康检查不会宣称每个可选分析后端都已安装。

仓库级、发布级和隔离安装检查见：[开发与发布](development.md)。

## 凭据

大多数公共证据客户端不需要凭据。科学服务支持可选 API key 时，应通过用户环境或 Codex 认可的 secret surface 配置。凭据不能写入仓库、模块 manifest、示例、日志或研究产物。

## 常见问题

- **看不到 skill：** 安装或更新后开启新的 Codex 任务。
- **marketplace 无法解析：** 检查仓库 URL、分支和 marketplace 名称。
- **核心运行时不可用：** 安装 Python 3.10 或更新版本；workbench 启动器会自动选择。
- **科学后端不可用：** skill 仍可提供规划和路由，但执行证据必须等待兼容项目环境或已验证替代方案。
- **结果被阻断：** 检查提示中指出的输入、兼容性或科学质量门控；被阻断的证据不会被静默提升为结论。
