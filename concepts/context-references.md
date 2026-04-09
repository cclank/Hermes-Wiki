---
title: Context References（@ 引用系统）
created: 2026-04-10
updated: 2026-04-10
type: concept
tags: [context, references, input, architecture]
sources: [agent/context_references.py, cli.py]
---

# Context References（@ 引用系统）

## 概述

Hermes 支持在用户输入中使用 `@` 前缀引用外部内容，系统会在发送给 LLM 前自动展开为实际内容并注入到消息中。

## 支持的引用类型

| 语法 | 作用 | 示例 |
|------|------|------|
| `@file:路径` | 注入文件内容 | `@file:src/main.py` |
| `@file:路径:行号` | 注入文件指定行 | `@file:main.py:10-50` |
| `@folder:路径` | 注入目录结构 | `@folder:src/` |
| `@diff` | 注入当前 git diff | `看看 @diff 有什么问题` |
| `@staged` | 注入 git staged 变更 | `检查 @staged 的代码` |
| `@url:地址` | 抓取网页内容注入 | `@url:https://example.com` |
| `@git:引用` | 注入 git 对象内容 | `@git:HEAD~1` |

## 处理流程

```text
用户输入: "帮我看看 @file:main.py 和 @diff 有什么问题"
    ↓
parse_context_references() — 正则匹配所有 @ 引用
    ↓
_expand_reference() — 逐个展开为实际内容
    ↓
安全检查:
  - 路径必须在 cwd 或 allowed_root 内（防止路径逃逸）
  - 拒绝敏感文件（.ssh/*, .env, .netrc 等）
  - 注入总量不超过上下文窗口 50%（硬限制），超 25% 告警
    ↓
注入到消息末尾的 "--- Attached Context ---" 块
    ↓
发送给 LLM（@ 引用标记从原文中移除）
```

## 安全机制

**敏感文件拦截**：以下路径会被拒绝注入：
- `~/.ssh/*`（密钥、config）
- `~/.bashrc`, `~/.zshrc`, `~/.profile`（shell 配置）
- `~/.netrc`, `~/.pgpass`, `~/.npmrc`, `~/.pypirc`（凭证文件）
- `skills/.hub/`（技能仓库内部文件）

**注入量限制**：
- 硬限制：注入内容不超过模型上下文窗口的 **50%**
- 软限制：超过 **25%** 时打印警告
- 超过硬限制时整个引用操作被拒绝（`blocked=True`）

**路径安全**：引用路径被解析为绝对路径后，必须在 `cwd` 或 `allowed_root` 范围内，防止 `@file:../../etc/passwd` 类型的路径遍历攻击。

## 与 Context Files 的区别

| | Context References（@引用） | Context Files（AGENTS.md 等） |
|---|---|---|
| 触发方式 | 用户主动在输入中写 `@` | 系统自动加载 |
| 注入位置 | 用户消息末尾 | system prompt |
| 内容来源 | 文件/diff/URL/git | 固定文件名 |
| 生命周期 | 单轮 | 整个会话 |

## 相关页面

- [[prompt-builder-architecture]] — Context Files（AGENTS.md 等）的加载机制
- [[security-defense-system]] — 安全检查体系

## 关键源码

| 文件 | 职责 |
|------|------|
| `agent/context_references.py` | 引用解析、展开、安全检查 |
| `cli.py` | 调用 `preprocess_context_references()` 的入口 |
