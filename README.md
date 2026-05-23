# Hermes Agent Architecture Wiki

<p align="center">
  <img src="https://img.shields.io/badge/Wiki-Hermes_Agent-blue?style=for-the-badge&logo=markdown" alt="Wiki" height="28">
  <img src="https://img.shields.io/badge/Source-hermes--agent-green?style=for-the-badge&logo=github" alt="Source" height="28">
  <img src="https://img.shields.io/badge/Knowledge_Base-42_pages-orange?style=for-the-badge&logo=obsidian" alt="Knowledge Base" height="28">
  <img src="https://img.shields.io/badge/Version-v0.13.0-purple?style=for-the-badge" alt="Version" height="28">
  <img src="https://img.shields.io/badge/Verified-Source_Code-brightgreen?style=for-the-badge" alt="Verified" height="28">
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge" alt="License" height="28">
</p>

> 基于 Nous Research [Hermes Agent](https://github.com/NousResearch/hermes-agent) 源码的深度架构文档。
> 所有页面均经过**逐行源码验证**，确保准确性与时效性。


---

## 目录结构
### 核心架构

- [agent-loop-and-prompt-assembly](concepts/agent-loop-and-prompt-assembly.md): Agent 循环、系统提示构建、平台提示、执行指导
- [tool-registry-architecture](concepts/tool-registry-architecture.md): 中央工具注册系统，声明式注册+集中调度
- [model-tools-dispatch](concepts/model-tools-dispatch.md): 工具编排与调度，异步桥接+动态 schema 调整+参数类型强制
- [toolsets-system](concepts/toolsets-system.md): 工具分组系统、递归解析、20+ 平台工具集
- [prompt-builder-architecture](concepts/prompt-builder-architecture.md): 系统提示模块化组装，注入防护+技能缓存+模型特定指导
- [auxiliary-client-architecture](concepts/auxiliary-client-architecture.md): 辅助 LLM 客户端路由器，多 provider 解析链+自动降级
- [provider-transport-architecture](concepts/provider-transport-architecture.md): Provider Transport ABC，统一抽象 Anthropic/Chat Completions/Responses API/Bedrock 的数据路径
- [provider-profile-plugins](concepts/provider-profile-plugins.md): **NEW v0.13.0** Provider profile ABC + 30 个插件化 provider

### 记忆与会话

- [memory-system-architecture](concepts/memory-system-architecture.md): 三层架构（MemoryStore/MemoryManager/MemoryProvider），冻结快照模式
- [session-search-and-sessiondb](concepts/session-search-and-sessiondb.md): FTS5 搜索 + LLM 摘要的跨会话回忆，orphan 删除策略
- [context-compressor-architecture](concepts/context-compressor-architecture.md): 自动上下文压缩 v3
- [skills-and-memory-interaction](concepts/skills-and-memory-interaction.md): Skills 与 Memory 的互补关系和决策树
- [skills-system-architecture](concepts/skills-system-architecture.md): 渐进式披露架构 + Curator 后台维护（v0.13 新增 archive/prune/list-archived）

### 工具与能力

- [browser-tool-architecture](concepts/browser-tool-architecture.md): 多后端浏览器自动化
- [web-tools-architecture](concepts/web-tools-architecture.md): **v0.13.0 全量插件化** —— 7 个 plugins/web/ 后端，按 capability 独立选 provider
- [code-execution-sandbox](concepts/code-execution-sandbox.md): execute_code 沙箱，7 工具限制+UDS/File RPC 两种通信模式
- [voice-mode-architecture](concepts/voice-mode-architecture.md): Push-to-talk + TTS provider registry（Piper / xAI Custom Voices）
- [context-references](concepts/context-references.md): @file/@folder/@diff/@url/@git 引用系统
- [fuzzy-matching-engine](concepts/fuzzy-matching-engine.md): 8 策略链模糊匹配
- [large-tool-result-handling](concepts/large-tool-result-handling.md): 三层溢出防护

### 性能与优化

- [parallel-tool-execution](concepts/parallel-tool-execution.md): 智能并发安全检测
- [prompt-caching-optimization](concepts/prompt-caching-optimization.md): 冻结快照保护 prefix cache，75% 成本节省
- [smart-model-routing](concepts/smart-model-routing.md): 智能模型路由

### 安全与可靠性

- [security-defense-system](concepts/security-defense-system.md): 多层防御 + Redaction 默认 ON + Discord guild-scoped + post-write delta lint（v0.13.0 安全 wave）
- [interrupt-and-fault-tolerance](concepts/interrupt-and-fault-tolerance.md): 中断传播、Fallback 模型链
- [credential-pool-and-isolation](concepts/credential-pool-and-isolation.md): 多密钥自动轮换、Profile 隔离
- [checkpoints-architecture](concepts/checkpoints-architecture.md): **NEW v0.13.0** Checkpoint v2 共享 shadow git store

### 多 Agent

- [multi-agent-architecture](concepts/multi-agent-architecture.md): **5 类运行时机制** (Delegate / MoA / Background Review / Goal Loop / Kanban)
- [goal-loop-architecture](concepts/goal-loop-architecture.md): **NEW v0.13.0** `/goal` 持久目标 + Ralph 判官循环
- [kanban-architecture](concepts/kanban-architecture.md): **NEW v0.13.0** 持久多 profile 协作看板（旗舰功能）
- [configuration-and-profiles](concepts/configuration-and-profiles.md): 多 Profile 架构

### 平台与扩展

- [cli-architecture](concepts/cli-architecture.md): CLI 架构、斜杠命令（含 /goal、/kanban、/queue、/steer 等 v0.13 新增）
- [terminal-backends](concepts/terminal-backends.md): 7 种终端后端（含 Vercel Sandbox）
- [messaging-gateway-architecture](concepts/messaging-gateway-architecture.md): **20+ 平台**（Google Chat 为第 20）+ 平台适配器插件化（IRC/Teams/Line/Google Chat）
- [gateway-session-management](concepts/gateway-session-management.md): 网关会话管理 + resume_pending 重启自动接续
- [hook-system-architecture](concepts/hook-system-architecture.md): 双 Hook 系统 + `transform_llm_output`（v0.13.0 新 hook）
- [mcp-and-plugins](concepts/mcp-and-plugins.md): MCP 集成（SSE OAuth + MEDIA tag + lifecycle keepalive）+ 插件系统
- [skin-engine](concepts/skin-engine.md): YAML 驱动的皮肤/主题系统
- [worktree-isolation](concepts/worktree-isolation.md): Git Worktree 并行隔离模式
- [cron-scheduling](concepts/cron-scheduling.md): 内置调度器（含 `no_agent` 脚本守护模式）
- [trajectory-and-data-generation](concepts/trajectory-and-data-generation.md): 轨迹保存、批量运行器
- [i18n-localization](concepts/i18n-localization.md): **NEW v0.13.0** 静态消息本地化（16 个 locale catalog）

### 更新日志

- [2026-04-09-update](changelog/2026-04-09-update.md): 59 commits，结构化错误分类、统一执行层、三层溢出防护、BlueBubbles 等
- [2026-04-10-update](changelog/2026-04-10-update.md): 293 commits，Context Engine 插件化、watch_patterns、WeChat、xAI、Discord/Slack 增强
- [2026-04-17-update](changelog/2026-04-17-update.md): 641 commits (v0.10.0)，压缩 v3、Bedrock/Gemini/Ollama 新 Provider、Tool Gateway
- [2026-04-18-update](changelog/2026-04-18-update.md): 410 commits post-v0.10.0，Transport ABC 重构、Shell Hooks、Delegate Orchestrator
- [2026-04-29-update](changelog/2026-04-29-update.md): 182 commits (v2026.4.23)，平台适配器插件化（PlatformRegistry + IRC）、Curator 后台技能维护、MiniMax OAuth、Vercel Sandbox、腾讯元宝
- [2026-05-14-update](changelog/2026-05-14-update.md): **1,533 commits**（v0.12.0 + v0.13.0 + post-release），Kanban + /goal + Provider Profile 插件化 + Web 全量插件化 + i18n + Checkpoint v2 + post-write lint + Google Chat / Teams / Line 等

---

## 统计信息

- **概念页面**: 42 个
- **更新日志**: 6 个
- **源码覆盖**: 关键模块逐行验证
- **跟踪版本**: v0.13.0 (2026.5.7)
- **最后更新**: 2026-05-14


## 使用方式

- **GitHub 在线浏览**: 直接点击上方目录链接
- **Obsidian 本地知识库**: 
  ```bash
  git clone https://github.com/cclank/Hermes-Wiki.git ~/Hermes-Wiki
  ```
- **配合 Hermes Agent**: 在 config.yaml 中设置 `skills.config.wiki.path: ~/Hermes-Wiki`


---

*本文档基于 Hermes Agent 源码分析生成。*
