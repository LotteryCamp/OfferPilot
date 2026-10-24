# CONTRIBUTING

本指南旨在帮助开发者了解如何在 OfferPilot 项目中贡献代码、文档、测试与反馈。我们欢迎所有形式的贡献，
无论是大型功能开发、小型修复、文档改进还是测试。我们相信每一个贡献都是推动项目前进的重要一环。

## Setup

```bash
git clone https://github.com/LotteryCamp/OfferPilot.git
cd OfferPilot
```

## Environment

（待定）

## Commit Rules

我们参考 Angular 规范。每条 Commit Message 应当按照如下格式编写：

```
<type>(<scope>): <subject>
```

- `type` 说明 Commit 的类别，只允许 `feat`、`fix`、`docs`、`refactor`、`test` 和 `chore`。
- `scope` 说明 Commit 影响的范围，可选项。
- `subject` 是 Commit 目的的简短描述，不超过 50 个字符。以动词开头，使用第一人称现在时。

## Pull Request

我们借鉴了 GitFlow 模式：

- `main` 分支作为主分支，同时也是开发分支。
- `main` 分支代表了最新的开发进度，其他分支都从这里分支出去，最终 PR 合并回这里。
- `feat` 分支用于开发新功能，应当命名为 `feat/<feature-name>`
- `fix` 分支用于修复问题，应当命名为 `fix/<fix-name>`

为了提交 PR：

- 从 `main` 分支创建一个新分支，此分支服务于你。
- 提交更改到你的分支。
- 在最终提交 PR 前，检查 `main` 分支更新。确保你的分支始终同步远程最新开发进度。
- 打开一个 PR，将提交从你的分支提交到 `main` 分支。

确保你的 PR 包含：

- 对 PR 实现的功能/修改的清晰描述。
- 如果存在与 PR 处理的问题相关的 issue，建议引用，如 `Resolved #10`。

PR 将由其他维护者进行审查。当项目测试体系建立后，你的 PR 可能经过：

- 自动化测试
- GitHub Copilot Agent 审查
- 维护者审查