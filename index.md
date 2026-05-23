# Wiki Index

> 内容目录。每个 wiki 页面按类型列出，附一行摘要。
> 查询前先读此文件找到相关页面。
> Last updated: 2026-05-14 | Total pages: 42 | 跟踪版本: v0.13.0 (2026.5.7)

## Entities

- [[aiagent-class]] — 核心对话循环类，管理 LLM 交互和工具调用
- [[memorystore-class]] — 记忆系统核心类，管理 MEMORY.md 和 USER.md

## Concepts

### 核心架构
- [[tool-registry-architecture]] — 中央工具注册系统，声明式注册+集中调度，循环导入安全
- [[auxiliary-client-architecture]] — 辅助 LLM 客户端路由器，多 provider 解析链+适配器模式+自动降级
- [[browser-tool-architecture]] — 多后端浏览器自动化，accessibility tree 文本表示+三层安全防护+并发隔离
- [[web-tools-architecture]] — Web 搜索/提取/爬取 7 个 plugin 后端，按 capability 独立选 provider
- [[skills-system-architecture]] — 渐进式披露 + Curator 后台维护（archive/prune/list-archived）
- [[memory-system-architecture]] — 冻结快照模式、原子写入、安全扫描
- [[agent-loop-and-prompt-assembly]] — Agent 循环、系统提示构建、平台提示、执行指导
- [[skills-and-memory-interaction]] — Skills 与 Memory 的互补关系和决策树
- [[toolsets-system]] — 工具分组系统、递归解析、20+ 平台工具集
- [[session-search-and-sessiondb]] — FTS5 搜索 + LLM 摘要的跨会话回忆
- [[provider-transport-architecture]] — Provider Transport ABC（Anthropic / Chat / Responses / Bedrock）
- [[provider-profile-plugins]] — **新** ProviderProfile ABC + 30 个 plugin（v0.13.0）

### 性能与优化
- [[parallel-tool-execution]] — 智能并发安全检测，三层分类 + 路径冲突检测
- [[prompt-caching-optimization]] — 冻结快照保护 prefix cache，75% 成本节省
- [[fuzzy-matching-engine]] — 8 策略链模糊匹配
- [[smart-model-routing]] — 智能模型路由，10级上下文长度解析链
- [[large-tool-result-handling]] — 三层溢出防护

### 安全与可靠性
- [[security-defense-system]] — 多层防御 + Redaction 默认 ON + Discord guild-scoped + post-write delta lint
- [[interrupt-and-fault-tolerance]] — 中断传播、Fallback 模型链
- [[credential-pool-and-isolation]] — 多密钥自动轮换、Profile 隔离
- [[checkpoints-architecture]] — **新** Checkpoint v2 共享 shadow git store

### 多 Agent
- [[multi-agent-architecture]] — **5 类机制**：Delegate / MoA / Background Review / Goal Loop / Kanban
- [[goal-loop-architecture]] — **新** `/goal` 持久目标 + Ralph 判官循环
- [[kanban-architecture]] — **新** 持久多 profile 协作看板（v0.13.0 旗舰）

### 平台与扩展
- [[cli-architecture]] — CLI 架构、斜杠命令（含 /goal、/kanban、/queue、/steer）
- [[configuration-and-profiles]] — 分层配置、Profile 隔离
- [[hook-system-architecture]] — Hook 系统（含 `transform_llm_output` v0.13.0 新 hook）
- [[mcp-and-plugins]] — MCP（SSE OAuth、MEDIA tag 升级）+ 插件系统
- [[terminal-backends]] — 7 种终端后端
- [[cron-scheduling]] — 内置调度器（含 `no_agent` 模式）
- [[trajectory-and-data-generation]] — 轨迹保存、批量运行器
- [[prompt-builder-architecture]] — 系统提示模块化组装
- [[context-compressor-architecture]] — 自动上下文压缩 v3
- [[model-tools-dispatch]] — 工具编排与调度
- [[gateway-session-management]] — 网关会话管理（含 resume_pending 重启接续）
- [[messaging-gateway-architecture]] — 20+ 消息平台（Google Chat 为第 20）+ 平台适配器插件化
- [[skin-engine]] — YAML 驱动的皮肤/主题
- [[worktree-isolation]] — Git Worktree 并行隔离
- [[i18n-localization]] — **新** 静态消息本地化（16 个 locale）
- [[voice-mode-architecture]] — 语音模式（含 xAI Custom Voices + Piper + TTS provider registry）
- [[context-references]] — @file/@folder/@diff/@url/@git 引用系统
- [[code-execution-sandbox]] — execute_code 沙箱

### 更新日志
- [[2026-04-09-update]] — 59 commits
- [[2026-04-10-update]] — 293 commits
- [[2026-04-17-update]] — 641 commits (v0.10.0)
- [[2026-04-18-update]] — 410 commits post-v0.10.0
- [[2026-04-29-update]] — 182 commits (v2026.4.23)
- [[2026-05-14-update]] — **新** 1,533 commits（v0.12.0 + v0.13.0 + post-release）
