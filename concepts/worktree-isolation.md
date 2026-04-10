---
title: Git Worktree 隔离
created: 2026-04-10
updated: 2026-04-10
type: concept
tags: [git, worktree, isolation, parallel]
sources: [cli.py, hermes_cli/main.py, cli-config.yaml.example]
---

# Git Worktree 隔离

## 概述

Hermes 支持通过 git worktree 实现**多个 agent 并行操作同一个仓库而不冲突**。每个 agent 会话在独立的 worktree 分支中工作，文件修改互不影响。

## 使用方式

```bash
hermes -w              # 启动时创建隔离 worktree
hermes --worktree      # 同上
```

或在 config.yaml 中全局开启：
```yaml
worktree: true         # 每次在 git 仓库中启动都自动创建 worktree
```

## 工作原理

```text
hermes -w
    ↓
_setup_worktree()
    ↓
1. 检测当前目录是否在 git 仓库内（不在则报错）
2. 在 .worktrees/ 下创建新 worktree（git worktree add）
3. 创建分支 hermes/hermes-{8位随机ID}，基于 HEAD
4. 自动将 .worktrees/ 添加到 .gitignore
5. 复制 .worktreeinclude 中列出的文件（gitignored 但 agent 需要的）
6. 切换 CWD 到 worktree 目录
    ↓
agent 在隔离环境中工作
    ↓
会话结束 → _cleanup_worktree()
    ↓
删除 worktree 目录 + 分支（git worktree remove + git branch -D）
```

## .worktreeinclude 文件

某些文件被 .gitignore 忽略但 agent 需要（如 `.env`、`node_modules`）。在项目根目录创建 `.worktreeinclude`：

```text
# 每行一个路径，支持文件和目录
.env
node_modules
```

- 文件：`shutil.copy2` 复制
- 目录：创建 symlink（节省磁盘空间）
- 路径遍历攻击防护：源路径和目标路径都必须在各自根目录内

## 适用场景

- 多个 agent 同时修改同一个仓库的不同部分
- 保护主分支不被实验性修改污染
- 与多 Profile 搭配使用（不同 Profile + 不同 worktree = 完全隔离的并行开发）

## 相关页面

- [[configuration-and-profiles]] — 多 Profile 架构
- [[multi-agent-architecture]] — 多 Agent 协作

## 关键源码

- `cli.py` — `_setup_worktree()` / `_cleanup_worktree()`
- `hermes_cli/main.py` — `-w`/`--worktree` 参数解析
