# CONTRIBUTING

本指南旨在帮助开发者了解如何在 OfferPilot 项目中贡献代码、文档、测试与反馈。我们欢迎所有形式的贡献，无论是大型功能开发、小型修复、文档改进还是测试。我们相信每一个贡献都是推动项目前进的重要一环。

## Setup

```bash
git clone https://github.com/LotteryCamp/OfferPilot.git
cd OfferPilot
```

## Environment

为了开发 OfferPilot，你需要准备以下开发工具：

（待定）

## Commit Rules

我们参考 Angular 规范。每条 Commit message 应当按照如下格式编写：

```
<type>(<scope>): <subject>

<body>
```

- `type` 说明 Commit 的类别，允许 `feat`、`fix`、`docs`、`refactor`、`test`、`chore` 等。
- `scope` 说明 Commit 影响的范围，可选项。
- `subject` 是 Commit 目的的简短描述，不超过 50 个字符。以动词开头，使用第一人称现在时。
- `body` 是 Commit 的具体说明，可选项。

贡献者应当遵循此规范。

## Pull Request

我们借鉴了 GitFlow 模式：

- `main` 分支作为主分支，同时也是开发分支。其代表最新的开发进度，其他分支都从 `main` 分叉出去，最终合并回这里。
- 功能性分支的类型参考 Commit Rules 的 `type`，比如 `feat` 分支代表新功能。命名规范遵循 `<type>/<name>`。

由于 `main` 分支的重要性，所有希望向 `main` 分支贡献的开发者都应该执行 Pull Request。为了提交 PR：

- 从 `main` 分支创建一个新分支，此分支服务于你。
- 提交更改到你的分支。
- 在最终提交 PR 前，检查 `main` 分支更新。将 `main` 分支的提交 `rebase` 到你的分支，确保始终同步远程最新开发进度。
- 打开一个 PR，将提交从你的分支提交到 `main` 分支。

确保你的 PR 包含：

- 对 PR 实现的功能/修改的清晰描述。
- 如果存在与 PR 处理的问题相关的 issue，建议引用，如 `Resolved #10`。

## Code Review

> 本节同时供审查者参考。

PR 由其他维护者进行审查。当项目测试体系建立后，一个 PR 可能经过：

- 自动化测试
- GitHub Copilot 等 Agent 审查
- 维护者人工审查

PR 需要解决测试和审查过程中抛出的问题，在对应的分支上修复代码，并推送新的提交。

审查者需要及时给予 Comments 和 Review，提出疑问和改进建议。当然，如果你没什么可以说的，LGTM (Look Good To Me) 即可。

审查者应当：

1. 关注自动化测试与可能的 Agent 审查情况

2. 如果 PR 与 base branch 冲突，要求 PR 提交者解决

3. 使用 Squash and merge，将 PR 合并到主分支。这意味着你 approve 了这个 PR :)

4. 仅在确认 PR 存在更符合要求的解决方案，且双方沟通后，才能 Close PR