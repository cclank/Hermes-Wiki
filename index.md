# Wiki Index

> 内容目录。每个 wiki 页面按类型列出，附一行摘要。
> 查询前先读此文件找到相关页面。
> Last updated: 2026-05-06 | Total pages: 37 + 6 changelogs

## Entities

- [[aiagent-class]] — 核心对话循环类，管理 LLM 交互和工具调用
- [[memorystore-class]] — 记忆系统核心类，管理 MEMORY.md 和 USER.md

## Concepts

### 核心架构
- [[tool-registry-architecture]] — 中央工具注册系统，声明式注册+集中调度，循环导入安全
- [[auxiliary-client-architecture]] — 辅助 LLM 客户端路由器，多 provider 解析链+适配器模式+自动降级
- [[provider-transport-architecture]] — Transport ABC + ProviderProfile 插件系统（33 profiles）
- [[browser-tool-architecture]] — 多后端浏览器自动化，accessibility tree 文本表示+三层安全防护+Lightpanda
- [[web-tools-architecture]] — 多后端搜索/提取（per-capability backend+SearXNG），LLM 智能内容压缩
- [[skills-system-architecture]] — 渐进式披露架构、Curator 后台维护、Pin 仅防删除
- [[memory-system-architecture]] — 冻结快照模式、原子写入、Hindsight long-term memory plugin
- [[agent-loop-and-prompt-assembly]] — Agent 循环、系统提示构建、平台提示、执行指导
- [[skills-and-memory-interaction]] — Skills 与 Memory 的互补关系和决策树
- [[toolsets-system]] — 工具分组系统、递归解析、14+ 平台工具集
- [[session-search-and-sessiondb]] — FTS5 搜索 + LLM 摘要的跨会话回忆

### 性能与优化
- [[parallel-tool-execution]] — 智能并发安全检测，三层分类 + 路径冲突检测
- [[prompt-caching-optimization]] — Anthropic system_and_3 缓存策略，75% 成本节省
- [[fuzzy-matching-engine]] — 8 策略链模糊匹配，从精确到相似度匹配
- [[smart-model-routing]] — 智能模型路由，10级上下文长度解析链+ProviderProfile 插件
- [[large-tool-result-handling]] — 大型结果文件化、预飞行压缩、Surrogate 清理

### 安全与可靠性
- [[security-defense-system]] — 5 层防御体系，100+ 威胁模式检测
- [[interrupt-and-fault-tolerance]] — 中断传播、凭证池轮换、Fallback 模型链
- [[credential-pool-and-isolation]] — 多密钥自动轮换、Profile 隔离、global auth fallback
- [[multi-agent-architecture]] — 多 Agent 体系，子代理委派+批量处理+跨平台通信

### 平台与扩展
- [[cli-architecture]] — CLI 架构、斜杠命令补全、Skin 引擎
- [[configuration-and-profiles]] — 分层配置、Profile 隔离、自动迁移
- [[hook-system-architecture]] — Hook 系统（Gateway Hooks + Plugin System），事件驱动+工具注册+上下文注入
- [[mcp-and-plugins]] — MCP 集成、插件钩子系统、OAuth 支持
- [[terminal-backends]] — 7 种终端后端（含 Vercel Sandbox）、环境抽象
- [[cron-scheduling]] — 内置调度器、自然语言调度、多平台投递
- [[trajectory-and-data-generation]] — 轨迹保存、批量运行器、RL 训练环境
- [[prompt-builder-architecture]] — 系统提示模块化组装，注入防护+技能缓存+模型特定指导
- [[context-compressor-architecture]] — 自动上下文压缩，结构化摘要+迭代更新+工具对完整性保障
- [[model-tools-dispatch]] — 工具编排与调度，异步桥接+动态 schema 调整+参数类型强制
- [[gateway-session-management]] — 网关会话管理（含 X-Hermes-Session-Key for api_server）
- [[messaging-gateway-architecture]] — 消息网关架构、平台适配器插件化、per-platform 重启通知
- [[skin-engine]] — YAML 驱动的皮肤/主题系统
- [[worktree-isolation]] — Git Worktree 并行隔离模式
- [[code-execution-sandbox]] — execute_code 沙箱，UDS/File RPC 通信
- [[voice-mode-architecture]] — Push-to-talk 语音交互，STT/TTS multi-provider
- [[context-references]] — @file/@folder/@diff/@url/@git 引用系统

## Changelog
- [[2026-04-09-update]] — 59 commits（结构化错误分类、统一执行层）
- [[2026-04-10-update]] — 293 commits（Context Engine 插件化、WeChat、xAI）
- [[2026-04-17-update]] — 641 commits / v0.10.0（压缩 v3、Bedrock、Tool Gateway、Dashboard 插件）
- [[2026-04-18-update]] — 410 commits post-v0.10.0（Transport ABC、Shell Hooks、Delegate Orchestrator）
- [[2026-04-29-update]] — 182 commits / v2026.4.23（PlatformRegistry + IRC、Curator、Vercel Sandbox、元宝）
- [[2026-05-06-update]] — 211 commits（含 v0.12.0/v2026.4.30；Provider 插件化、Kanban、Checkpoints v2、SearXNG、Lightpanda、i18n、Hindsight）

