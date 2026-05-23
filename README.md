# Hermes Agent Architecture Wiki

<p align="center">
  <img src="https://img.shields.io/badge/Wiki-Hermes_Agent-blue?style=for-the-badge&logo=markdown" alt="Wiki" height="28">
  <img src="https://img.shields.io/badge/Source-hermes--agent-green?style=for-the-badge&logo=github" alt="Source" height="28">
  <img src="https://img.shields.io/badge/Knowledge_Base-37_pages-orange?style=for-the-badge&logo=obsidian" alt="Knowledge Base" height="28">
  <img src="https://img.shields.io/badge/Version-v2026.5.16-purple?style=for-the-badge" alt="Version" height="28">
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

- [browser-tool-architecture](concepts/browser-tool-architecture.md): 多后端浏览器自动化，accessibility tree+三层安全防护
- [web-tools-architecture](concepts/web-tools-architecture.md): 七大后端插件化搜索/提取/爬取（WebSearchProvider ABC + 注册表），LLM 智能内容压缩
- [code-execution-sandbox](concepts/code-execution-sandbox.md): execute_code 沙箱，7 工具限制+UDS/File RPC 两种通信模式
- [voice-mode-architecture](concepts/voice-mode-architecture.md): Push-to-talk 语音交互，STT（5 Provider）+ TTS（10 内置 Provider，含 Piper 本地神经 TTS）
- [context-references](concepts/context-references.md): @file/@folder/@diff/@url/@git 引用系统，安全沙箱+注入量限制
- [fuzzy-matching-engine](concepts/fuzzy-matching-engine.md): 8 策略链模糊匹配，从精确到相似度匹配
- [large-tool-result-handling](concepts/large-tool-result-handling.md): 三层溢出防护（工具内截断/单结果持久化/轮次聚合预算）

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

- [multi-agent-architecture](concepts/multi-agent-architecture.md): 5 种运行时机制（delegate_task/MoA/Background Review/send_message/Kanban worker）
- [multi-agent-kanban](concepts/multi-agent-kanban.md): SQLite 看板 + 心跳 + 死锁回收 + 自动分解 + Swarm 拓扑 + 诊断（v0.13.0）
- [goal-loop-and-steering](concepts/goal-loop-and-steering.md): `/goal` Ralph 循环 + `/steer` + `/queue` + `/handoff` 四种 session 级控制原语
- [configuration-and-profiles](concepts/configuration-and-profiles.md): 多 Profile 架构，完全隔离的 agent 实例

### 平台与扩展

- [cli-architecture](concepts/cli-architecture.md): CLI 架构、斜杠命令、hermes dump/proxy/kanban/curator/migrate
- [terminal-backends](concepts/terminal-backends.md): 7 种终端后端（含 Vercel Sandbox）、统一 spawn-per-call 执行模型
- [messaging-gateway-architecture](concepts/messaging-gateway-architecture.md): 22 平台统一网关（17 内置 + 5 插件：IRC/Teams/Google Chat/LINE/SimpleX），PlatformRegistry 插件化
- [gateway-session-management](concepts/gateway-session-management.md): 网关会话管理、state.db 唯一权威、startup 自动续约、`X-Hermes-Session-Key`
- [hook-system-architecture](concepts/hook-system-architecture.md): 双 Hook 系统 + Shell Hooks + Plugin System，register_command/dispatch_tool
- [mcp-and-plugins](concepts/mcp-and-plugins.md): MCP 集成（SSE + OAuth forwarding）、插件钩子系统、OAuth 支持
- [provider-plugin-system](concepts/provider-plugin-system.md): `ProviderProfile` ABC + `plugins/model-providers/` 29 内置（v0.13.0）
- [hermes-proxy](concepts/hermes-proxy.md): OAuth 提供方的 OpenAI 兼容本地代理（Codex/Aider/Cline 复用 Claude Pro / SuperGrok）（v0.14.0）
- [lsp-integration](concepts/lsp-integration.md): post-write 语义诊断、git-workspace 门控、delta only（v0.14.0）
- [i18n-and-locales](concepts/i18n-and-locales.md): 薄切片国际化、16 个 YAML 区域、7 个生产语言（v0.13.0）
- [skin-engine](concepts/skin-engine.md): YAML 驱动的皮肤/主题系统
- [worktree-isolation](concepts/worktree-isolation.md): Git Worktree 并行隔离模式
- [cron-scheduling](concepts/cron-scheduling.md): 内置调度器、自然语言调度、多平台投递、`no_agent` 脚本-only 模式（v0.13.0）、webhook 直送（v0.11.0）
- [trajectory-and-data-generation](concepts/trajectory-and-data-generation.md): 轨迹保存、批量运行器、RL 训练环境

### 更新日志

- [2026-04-09-update](changelog/2026-04-09-update.md): 59 commits，结构化错误分类、统一执行层、三层溢出防护、BlueBubbles 等
- [2026-04-10-update](changelog/2026-04-10-update.md): 293 commits，Context Engine 插件化、watch_patterns、WeChat、xAI、Discord/Slack 增强
- [2026-04-17-update](changelog/2026-04-17-update.md): 641 commits (v0.10.0)，压缩 v3、Bedrock/Gemini/Ollama 新 Provider、Tool Gateway、插件命名空间技能、钉钉 QR 认证、Dashboard 插件
- [2026-04-18-update](changelog/2026-04-18-update.md): 410 commits post-v0.10.0，Transport ABC 重构、Shell Hooks、Delegate Orchestrator、Step Plan/AI Gateway/xAI STT/KittenTTS、WeCom QR、Subagent 观测性
- [2026-04-29-update](changelog/2026-04-29-update.md): 182 commits (v2026.4.23)，平台适配器插件化（PlatformRegistry + IRC 参考实现）、Curator 后台技能维护、MiniMax OAuth、Vercel Sandbox、腾讯元宝、`on_session_switch`、`/reload-skills`
- [2026-04-30-update](changelog/2026-04-30-update.md): 1096 commits (**v0.12.0 Curator Release**)，自治 Curator（7 天周期、12 个子命令、`bump_use()`/`_pinned_guard()`）、self-improvement loop class-first 重写、GMI Cloud / Azure AI Foundry / LM Studio / MiniMax OAuth / Tencent Tokenhub、Spotify + Google Meet、TTS provider registry + Piper、`hermes -z`、冷启动 ~57%↓、prompt cache TTL 可配
- [2026-05-07-update](changelog/2026-05-07-update.md): 864 commits (**v0.13.0 Tenacity Release**)，**多 Agent Kanban 持久协作板**（heartbeat/reclaim/zombie/max_retries）、`/goal` Ralph Loop + `/subgoal`、`/handoff` `/steer` `/queue`、Checkpoints v2、Gateway auto-resume、`no_agent` cron 模式、ProviderProfile ABC 插件化、MCP SSE transport、`transform_llm_output` hook、Google Chat（20 平台）、7+ i18n locale、8 P0 closures
- [2026-05-16-update](changelog/2026-05-16-update.md): 808 commits (**v0.14.0 Foundation Release**)，PyPI wheel、Native Windows beta、lazy-deps debloat、xAI SuperGrok OAuth + grok-4.3 1M context、`hermes proxy` OpenAI-compatible 本地代理、`x_search` / `vision_analyze` 像素直传 / `video_generate` 可插拔、LSP 语义诊断、file-mutation verifier footer、180x CDP、Microsoft Teams 端到端、LINE + SimpleX（22 平台）、Codex app-server、Pareto router `min_coding_score`、12 P0 + 50 P1 closures

---

## 统计信息

- **概念页面**: 37 个
- **更新日志**: 8 个
- **源码覆盖**: 关键模块逐行验证
- **跟踪版本**: v2026.5.16
- **最后更新**: 2026-05-21


## 使用方式

- **GitHub 在线浏览**: 直接点击上方目录链接
- **Obsidian 本地知识库**: 
  ```bash
  git clone https://github.com/cclank/Hermes-Wiki.git ~/Hermes-Wiki
  ```
- **配合 Hermes Agent**: 在 config.yaml 中设置 `skills.config.wiki.path: ~/Hermes-Wiki`


---

*本文档基于 Hermes Agent 源码分析生成。*
