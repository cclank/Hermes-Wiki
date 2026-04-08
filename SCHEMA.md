# Wiki Schema

## Domain
Hermes Agent — AI Agent 框架的架构与实现细节，重点关注 Skills System（技能系统）、Memory System（记忆系统）、Tool System（工具系统）、以及它们之间的交互机制。覆盖 Nous Research 的 hermes-agent 开源项目。

## Conventions
- 文件名：小写 + 连字符，无空格（如 `skills-system.md`）
- 每个 wiki 页面必须以 YAML frontmatter 开头
- 使用 wiki 双向链接（如 [[tool-registry-architecture]]）连接页面（每页至少 2 个出站链接）
- 更新页面时必须更新 `updated` 日期
- 新页面必须添加到 `index.md` 对应分类下
- 每个操作必须追加到 `log.md`

## Frontmatter
```yaml
---
title: 页面标题
created: YYYY-MM-DD
updated: YYYY-MM-DD
type: entity | concept | comparison | query | summary
tags: [来自下方分类法]
sources: [raw/articles/来源文件名.md]
---
```

## Tag Taxonomy
- **架构**: architecture, module, component, interface, reliability, fault-tolerance, interrupt, extensibility
- **Skills**: skill, skill-sync, skill-management, skill-lifecycle, skills-guard
- **Memory**: memory, memory-provider, session-search, user-profile, session-store
- **Tools**: tool, toolset, tool-registry, terminal-tool, browser-tool, terminal, environments
- **Agent**: agent, agent-loop, prompt-builder, context-compression, delegation
- **Gateway**: gateway, platform, telegram, discord, messaging, multi-platform
- **CLI**: cli, command, setup, config, ux, profile
- **Meta**: comparison, architecture-diagram, code-pattern, best-practice
- **性能**: performance, concurrency, cost-optimization, caching, model-routing, fuzzy-matching
- **安全**: security, injection-defense, credentials, isolation
- **数据**: data-generation, training, trajectory
- **运维**: cron, automation, scheduling, mcp, plugins, configuration
- **上下文**: context-management
- **模型**: anthropic

## Page Thresholds
- **创建页面**：当实体/概念在 2+ 源码中出现，或是某个源码的核心内容
- **更新已有页面**：当源码提到已覆盖的内容时
- **不创建页面**：对于偶然提及、次要细节或超出领域的内容
- **拆分页面**：超过 ~200 行时拆分为子主题并交叉链接
- **归档页面**：内容被完全取代时移至 `_archive/`，从 index 中移除

## Entity Pages
每个实体一页。包括：
- 概述 / 是什么
- 关键事实（文件路径、类名、关键函数）
- 与其他实体的关系（使用 wiki 双向链接）
- 源码引用

## Concept Pages
每个概念一页。包括：
- 定义 / 解释
- 当前知识状态
- 开放问题或争议
- 相关概念（使用 wiki 双向链接）

## Comparison Pages
对比分析。包括：
- 对比什么及为什么
- 对比维度（推荐表格形式）
- 结论或综合
- 源码

## Update Policy
当新信息与已有内容冲突时：
1. 检查日期 — 较新源码通常覆盖旧源码
2. 如果确实矛盾，同时记录两种说法并注明日期和来源
3. 在 frontmatter 中标记：`contradictions: [page-name]`
4. 在 lint 报告中标记供用户审核
