# Wiki Index

> 内容目录。每个 wiki 页面按类型列出，附一行摘要。
> 查询前先读此文件找到相关页面。
> Last updated: 2026-05-09 | Total pages: 37 + 6 changelog | Tracked: hermes-agent v0.13.0 (v2026.5.7) + post-release

## Entities

- [[aiagent-class]] — 核心对话循环类，管理 LLM 交互和工具调用
- [[memorystore-class]] — 记忆系统核心类，管理 MEMORY.md 和 USER.md

## Concepts

### 核心架构
- [[tool-registry-architecture]] — 中央工具注册系统，声明式注册+集中调度，循环导入安全
- [[auxiliary-client-architecture]] — 辅助 LLM 客户端路由器，多 provider 解析链+适配器模式+自动降级
- [[browser-tool-architecture]] — 多后端浏览器自动化，accessibility tree 文本表示+三层安全防护+并发隔离
- [[web-tools-architecture]] — 多后端搜索/提取/爬取，LLM 智能内容压缩（分块+合成），四层安全防护
- [[skills-system-architecture]] — 渐进式披露架构，技能发现、条件激活、密钥管理
- [[memory-system-architecture]] — 冻结快照模式、原子写入、安全扫描
- [[agent-loop-and-prompt-assembly]] — Agent 循环、系统提示构建、平台提示、执行指导
- [[skills-and-memory-interaction]] — Skills 与 Memory 的互补关系和决策树
- [[toolsets-system]] — 工具分组系统、递归解析、14+ 平台工具集
- [[session-search-and-sessiondb]] — FTS5 搜索 + LLM 摘要的跨会话回忆

### 性能与优化
- [[parallel-tool-execution]] — 智能并发安全检测，三层分类 + 路径冲突检测
- [[prompt-caching-optimization]] — Anthropic system_and_3 缓存策略，75% 成本节省
- [[fuzzy-matching-engine]] — 8 策略链模糊匹配，从精确到相似度匹配
- [[smart-model-routing]] — 智能模型路由 + ProviderProfile 插件化（28 个 bundled provider，v0.13.0+）
- [[large-tool-result-handling]] — 大型结果文件化、预飞行压缩、Surrogate 清理

### 安全与可靠性
- [[security-defense-system]] — 5 层防御 + v0.13.0 8 个 P0 闭环（secret redaction default、guild scope、TOCTOU、SSRF floor）
- [[interrupt-and-fault-tolerance]] — 中断传播、凭证池轮换、Fallback 模型链
- [[credential-pool-and-isolation]] — 多密钥自动轮换、Profile 隔离
- [[multi-agent-architecture]] — 多 Agent 体系，delegate/MoA/Background Review/send_message + Kanban 持久化看板（v0.13.0+）

### 平台与扩展
- [[cli-architecture]] — CLI 架构、`/goal`/`/sessions`/`/queue`/`/steer` 等命令、销毁性命令二次确认
- [[configuration-and-profiles]] — 分层配置、Profile 隔离、自动迁移
- [[hook-system-architecture]] — Gateway Hooks + Plugin System，含 `transform_llm_output`/`pre_gateway_dispatch`/approval observer hook（v0.13.0+）
- [[mcp-and-plugins]] — MCP 集成（含 SSE transport）、插件钩子系统、OAuth 支持
- [[terminal-backends]] — 7 种终端后端（含 Vercel Sandbox）、环境抽象、持久化 Shell
- [[cron-scheduling]] — 内置调度器、`no_agent` 看门狗模式、watchers skill、deliver=all
- [[trajectory-and-data-generation]] — 轨迹保存、批量运行器、RL 训练环境
- [[prompt-builder-architecture]] — 系统提示模块化组装，注入防护+技能缓存+模型特定指导
- [[context-compressor-architecture]] — 自动上下文压缩，结构化摘要+迭代更新+工具对完整性保障
- [[model-tools-dispatch]] — 工具编排与调度，异步桥接+动态 schema 调整+参数类型强制
- [[provider-transport-architecture]] — Provider Transport ABC + ProviderProfile 协作
- [[gateway-session-management]] — 网关会话管理，多平台会话隔离+PII 脱敏+重置策略
- [[messaging-gateway-architecture]] — 20+ 平台网关，含 Google Chat/Teams/MS Graph (v0.13.0+)、`allowed_*` 白名单、`[[as_document]]`、auto-resume
- [[browser-tool-architecture]] — 多后端浏览器自动化 + Lightpanda 引擎（v0.13.0+）
- [[web-tools-architecture]] — 多后端搜索/提取，含 SearXNG/Brave/DDGS（v0.13.0+） + per-capability backend 拆分
- [[skin-engine]] — YAML 驱动的皮肤/主题系统
- [[worktree-isolation]] — Git Worktree 并行隔离
- [[code-execution-sandbox]] — 代码执行沙箱
- [[context-references]] — @file/@diff/@url 引用系统
- [[voice-mode-architecture]] — 语音模式（Push-to-talk → STT → TTS）

### 更新日志
- [[changelog/2026-04-09-update]] — 59 commits, 错误分类 + 三层溢出 + BlueBubbles
- [[changelog/2026-04-10-update]] — 293 commits, Context Engine 插件化 + watch_patterns + WeChat/xAI/Discord/Slack 增强
- [[changelog/2026-04-17-update]] — 641 commits (v0.10.0)，压缩 v3 + 新 Provider + Tool Gateway + 钉钉 QR + Dashboard 插件
- [[changelog/2026-04-18-update]] — 410 commits post-v0.10.0，Transport ABC + Shell Hooks + Step Plan + xAI STT + KittenTTS
- [[changelog/2026-04-29-update]] — 182 commits (v2026.4.23)，平台适配器插件化 + Curator + MiniMax OAuth + Vercel Sandbox + 元宝
- [[changelog/2026-05-09-update]] — 1100 commits (v0.13.0 + post-release)，**Provider 插件 + Kanban 持久化看板 + `/goal` Ralph + Checkpoints v2 + Google Chat/Teams/MS Graph + SearXNG/Brave/DDGS + Lightpanda + cron no_agent + 5 新 hook + 8 P0 安全闭环 + i18n 7 语言 + Windows beta**

