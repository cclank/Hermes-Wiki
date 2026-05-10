# Wiki Log

> 所有 wiki 操作的按时间顺序记录。只追加，不修改。
> 格式：`## [YYYY-MM-DD] action | subject`
> Actions: ingest, update, query, lint, create, archive, delete
> 当此文件超过 500 条时，轮换：重命名为 log-YYYY.md，重新开始。

## [2026-04-07] create | Wiki initialized
- Domain: Hermes Agent — Skills System and Memory
- Structure created with SCHEMA.md, index.md, log.md
- Directory structure: raw/{articles,papers,transcripts,assets}, entities, concepts, comparisons, queries

## [2026-04-07] create | 批量创建 8 个 wiki 页面
基于对 hermes-agent 代码库的深入分析（814 个文件）：

**概念页 (6):**
- skills-system-architecture — 渐进式披露架构
- memory-system-architecture — 冻结快照模式
- agent-loop-and-prompt-assembly — Agent 循环和提示构建
- skills-and-memory-interaction — Skills 与 Memory 的互补关系
- toolsets-system — 工具分组系统
- session-search-and-sessiondb — FTS5 跨会话搜索
- messaging-gateway-architecture — 14+ 平台统一网关
- context-compression — 上下文压缩

**实体页 (2):**
- aiagent-class — AIAgent 核心类
- memorystore-class — MemoryStore 核心类

## [2026-04-08] create | 16 个专题系统分析
基于源码深入分析，完成 16 个专题：

**核心架构 (6):**
- skills-system-architecture — 渐进式披露架构
- memory-system-architecture — 冻结快照模式
- agent-loop-and-prompt-assembly — Agent 循环和提示构建
- skills-and-memory-interaction — Skills 与 Memory 的互补关系
- toolsets-system — 工具分组系统
- session-search-and-sessiondb — FTS5 跨会话搜索

**性能与优化 (5):**
- parallel-tool-execution — 智能并发安全检测
- prompt-caching-optimization — Anthropic 缓存策略
- fuzzy-matching-engine — 8 策略链模糊匹配
- model-metadata-and-routing — 模型元数据缓存
- large-tool-result-handling — 大型结果处理

**安全与可靠性 (4):**
- security-defense-system — 5 层防御体系
- interrupt-and-fault-tolerance — 中断传播与容错
- credential-pool-and-isolation — 凭证池与隔离
- iteration-budget-and-delegation — 迭代预算与委派

**平台与扩展 (7):**
- cli-architecture — CLI 架构
- gateway-multi-platform — 多平台网关
- configuration-and-profiles — 配置与 Profile
- mcp-and-plugins — MCP 与插件
- terminal-backends — 终端后端
- cron-scheduling — Cron 调度
- trajectory-and-data-generation — 轨迹保存

- index.md 更新为 24 页，按类别组织
- SCHEMA.md 已定义完整标签分类法

## [2026-04-08] update | Tool Registry 工具注册系统 wiki 页面创建
- 文件: concepts/tool-registry-architecture.md
- 源码: tools/registry.py (10KB/275行)
- 核心内容: 中央工具注册系统，声明式注册+集中调度，循环导入安全设计，__slots__ 内存优化，MCP 动态注销支持
- 创建 cron job: Hermes Wiki 专题编写（每小时一个），8 次重复
- index.md 更新为 25 页

## [2026-04-08] update | Auxiliary Client 辅助客户端 wiki 页面创建
- 文件: concepts/auxiliary-client-architecture.md
- 源码: agent/auxiliary_client.py (85KB/2127行)
- 核心内容: 辅助 LLM 客户端路由器，多 provider 解析链（8 级降级）、适配器模式（Codex/Anthropic 统一为 chat.completions 接口）、客户端缓存+事件循环安全、支付/配额耗尽自动降级、任务级独立配置
- index.md 更新为 26 页

## [2026-04-08] update | Browser Tool 浏览器自动化 wiki 页面创建
- 文件: concepts/browser-tool-architecture.md
- 源码: tools/browser_tool.py (84KB/2202行)
- 核心内容: 多后端浏览器自动化（本地/Cloud/CDP/Camofox），accessibility tree 文本化页面表示，三层安全防护（SSRF/注入/策略），并发会话隔离（独立 socket 目录），后台清理线程+atexit 双重保障
- index.md 更新为 27 页

## [2026-04-08] update | Web Tools 搜索/提取 wiki 页面创建
- 文件: concepts/web-tools-architecture.md
- 源码: tools/web_tools.py (85KB/2099行)
- 核心内容: 多后端搜索/提取/爬取（Firecrawl/Exa/Parallel/Tavily），LLM 智能内容压缩（单次+分块并行+合成），Firecrawl 双路径架构（直接 API + Nous Gateway），四层安全防护，标准化层统一输出格式
- index.md 更新为 28 页

## [2026-04-08] update | 双专题 wiki 页面创建（Prompt Builder + Context Compressor）
- 文件: concepts/prompt-builder-architecture.md
  - 源码: agent/prompt_builder.py (40KB/959行)
  - 核心内容: 系统提示模块化组装，上下文文件注入防护（10种威胁模式+11种不可见Unicode），技能索引缓存+快照持久化，平台提示适配，模型特定执行指导
- 文件: concepts/context-compressor-architecture.md
  - 源码: agent/context_compressor.py (30KB/696行)
  - 核心内容: 自动上下文压缩，结构化摘要模板（Goal/Progress/Decisions/Files/Next Steps），迭代更新，工具输出修剪，工具调用对完整性保障，失败冷却
- index.md 更新为 30 页

## [2026-04-08] update | 最后 2 专题 wiki 页面创建（Model Tools + Gateway Session）
- 文件: concepts/model-tools-dispatch.md
  - 源码: model_tools.py (22KB/577行，从 2400 行重构而来)
  - 核心内容: 工具编排与调度，异步桥接三种路径，动态 schema 调整（execute_code/browser_navigate），参数类型强制，Agent 级工具拦截，三层工具发现机制
- 文件: concepts/gateway-session-management.md
  - 源码: gateway/session.py (41KB/1081行)
  - 核心内容: 多平台会话管理，SessionSource 统一抽象，SessionKey 构建规则，PII 脱敏（Discord 例外），动态系统提示注入，双存储策略（SQLite+JSON），原子保存，会话重置策略
- index.md 更新为 32 页

## [2026-04-08] update | 多 Agent 体系 wiki 页面创建
- 文件: concepts/multi-agent-architecture.md
- 源码: tools/delegate_tool.py (40KB/978行), batch_runner.py (54KB/1285行), tools/send_message_tool.py (39KB/952行)
- 核心内容: 分层子代理委派（单任务/并行最多3个），安全沙箱（5类禁止工具+深度限制），凭证继承与池共享，ACP 异构 Agent 编排，批量处理引擎，跨平台消息投递
- index.md 更新为 35 页
## [2026-04-08] update | 三专题 wiki 页面创建（Prompt Caching + Smart Model Routing + Hook System）
- 文件: concepts/prompt-caching-optimization.md (updated)
  - 源码: agent/prompt_caching.py (2KB/72行)
  - 核心内容: Anthropic system_and_3 缓存策略，4断点滚动窗口，纯函数设计
- 文件: concepts/smart-model-routing.md
  - 源码: agent/model_metadata.py (36KB/941行), agent/models_dev.py (25KB/781行), hermes_cli/model_switch.py (32KB/927行)
  - 核心内容: 10级上下文长度解析链，models.dev 4000+模型数据库，本地服务器自动探测(4种)，别名系统，token估算
- 文件: concepts/hook-system-architecture.md
  - 源码: gateway/hooks.py (170行), hermes_cli/plugins.py (609行)
  - 核心内容: Gateway Hooks 事件驱动(8种事件+通配符)，Plugin System 三级来源(用户/项目/pip)，PluginContext API(工具注册/消息注入/CLI命令/钩子)，缓存友好上下文注入
- index.md 更新为 37 页

## [2026-05-10] update | 对齐 Hermes v0.12.0 + v0.13.0（1960 commits）
基于 `/tmp/hermes-agent` HEAD = cdb6e5e (2026-05-10) 的全量源码对照，新增/更新如下：

**新增 changelog (1):**
- changelog/2026-05-10-update.md — 覆盖 v0.12.0 (v2026.4.30) + v0.13.0 (v2026.5.7)，逐条标注源码行号

**新增 concept 页面 (2):**
- concepts/kanban-multi-agent.md — 持久化多 Agent 协作板
  - 源码: hermes_cli/kanban.py(2228), kanban_db.py(4740), kanban_diagnostics.py(649), tools/kanban_tools.py(1130), plugins/kanban/
  - 核心: SQLite 任务表 + heartbeat/reclaim/zombie 检测 + workspace 隔离(scratch/worktree/dir) + 幻觉防护 + per-task max_retries + 多板跨 profile
- concepts/goal-and-ralph-loop.md — `/goal` Ralph 循环
  - 源码: hermes_cli/goals.py(593)
  - 核心: GoalState dataclass, JUDGE_SYSTEM_PROMPT, SessionDB state_meta 持久化, consecutive_parse_failures 防死循环, /resume/pause/clear

**更新 concept 页面 (13):**
- multi-agent-architecture — 第 5 种机制 Kanban
- messaging-gateway-architecture — 20+ 平台、Google Chat/Teams/LINE 插件、`[[as_document]]` 指令、auto-resume
- security-defense-system — v0.13.0 八个 P0 修复（redaction 默认/CVSS 8.1 Discord/WhatsApp 拒陌生人/TOCTOU/SSRF 地板/cron prompt-injection/debug share redact）
- voice-mode-architecture — xAI Custom Voices 声音克隆、Piper 本地 TTS、TTS Provider Registry、`video_analyze` 工具
- smart-model-routing — Provider 全面插件化、29 个 bundled 插件、LM Studio 一等公民、GMI/Azure Foundry/Tencent Tokenhub、Remote model catalog manifest、native multimodal image routing
- hook-system-architecture — `transform_llm_output` 钩子、PluginContext 新增 register_platform/register_image_gen_provider/register_context_engine/register_skill
- mcp-and-plugins — MCP SSE transport、OAuth 转发、stale-pipe retry、image → MEDIA tag、keepalive、TOCTOU 修复
- cron-scheduling — `no_agent` watchdog 模式
- prompt-caching-optimization — `cache_ttl: "1h"` 可配
- web-tools-architecture — 7 个后端、SearXNG/Brave Free/DDGS、按 capability 选 backend
- provider-transport-architecture — ProviderProfile ABC + plugins/model-providers/ 29 个
- skills-system-architecture — Curator 子命令扩展（archive/prune/list-archived）、active-update bias、class-first prompt、bump_use 钩入
- cli-architecture — `/goal`/`/kanban`/`/curator`/`/steer`/`/queue`/`/reload-skills`/`/clear`/`hermes -z` 一次性模式

**根目录更新:**
- index.md — 39 页，新增多 Agent 分类条目
- README.md — badge 改 v0.13.0 (v2026.5.7)、39 pages、6 changelogs、Kanban + Goal 上链
- log.md — 本条日志

**源码核对锚点（全部对照 /tmp/hermes-agent）:**
- hermes_cli/kanban.py:189,2181 / kanban_db.py:781,843 / kanban_diagnostics.py
- hermes_cli/goals.py:108,148,282,391-410,546
- tools/vision_tools.py:1167 (video_analyze), 1375 schema
- tools/tts_tool.py:113 (Piper), 874 (xAI TTS+voice clone)
- cron/jobs.py:498 / cron/scheduler.py:1040 (no_agent)
- agent/redact.py:67 (HERMES_REDACT_SECRETS=true 默认)
- agent/prompt_caching.py:43,58 (cache_ttl)
- agent/transports/{anthropic,bedrock,chat_completions,codex}.py
- providers/__init__.py / providers/base.py:25 / plugins/model-providers/ (29 bundled)
- plugins/platforms/{google_chat,irc,line,teams}/
- gateway/platforms/api_server.py:727 (X-Hermes-Session-Key)
- gateway/run.py:3192 (auto-resume) / 9928 ([[as_document]])
- hermes_cli/plugins.py:136 (transform_llm_output)
- tools/mcp_tool.py:33,201 (SSE)
