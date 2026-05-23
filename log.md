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

## [2026-05-21] update | 同步 hermes-agent v0.12.0 / v0.13.0 / v0.14.0（~2700 commits 增量）
- 对比基准: 上次跟踪 v2026.4.23（v0.11.0），最新 main 跑到 v2026.5.16（v0.14.0）+ 5 天补丁
- 新建 3 个 changelog（按 release 切分，所有引用 file:line 经源码核对）:
  - **changelog/2026-04-30-update.md** — v0.12.0 Curator Release（1096 commits）
    - 验证: agent/curator.py(1781行), hermes_cli/curator.py(598行), tools/lazy_deps.py, plugins/platforms/teams, gateway/platforms/yuanbao*.py, agent/lmstudio_reasoning.py, tools/environments/vercel_sandbox.py(654行)
  - **changelog/2026-05-07-update.md** — v0.13.0 Tenacity Release（864 commits, 13 P0/36 P1 closures）
    - 验证: hermes_cli/kanban.py(2677行)+kanban_db.py(6286行), tools/kanban_tools.py:547-580, hermes_cli/goals.py(762行), agent/system_prompt.py:34,120 KANBAN_GUIDANCE, providers/base.py:39 ProviderProfile ABC, plugins/model-providers/, plugins/platforms/google_chat/, tools/checkpoint_manager.py:340-362 v2 layout, gateway/run.py:3543,3565 auto-resume, tools/cronjob_tools.py:322-372 no_agent mode, hermes_cli/config.py:4439,4482 redaction ON, gateway/platforms/discord.py:508 dm_role_auth_guild
  - **changelog/2026-05-16-update.md** — v0.14.0 Foundation Release（808 commits, 12 P0/50 P1 closures）
    - 验证: pyproject.toml:6 hermes-agent PyPI, tools/lazy_deps.py(613行), hermes_cli/auth.py:201 SuperGrok OAuth, agent/model_metadata.py:217 grok-4.3 1M, hermes_cli/proxy/, tools/x_search_tool.py, tools/microsoft_graph_*.py, plugins/platforms/{teams,line,simplex}, agent/lsp/(11 modules), tools/clarify_gateway.py, gateway/platforms/discord.py:3683 history backfill
- 更新 14 个核心 concept 页面（按影响度排序）:
  - messaging-gateway-architecture: 22 平台（+Teams/Google Chat/LINE/SimpleX）, allowlist 全平台, Discord guild-scoped, WhatsApp dm_policy, [[as_document]], clarify 按钮
  - multi-agent-architecture: 新增第 4/5 机制 —— 持久化 Kanban + /goal Ralph loop；/handoff/steer/queue 控制面
  - skills-system-architecture: Curator 升格为后台 agent（12 子命令）+ bump_use 多调用路径 + consolidated vs pruned 分类
  - smart-model-routing: GMI/Azure Foundry/LM Studio/Tencent Tokenhub/MiniMax OAuth(v0.12) + xAI SuperGrok OAuth/grok-4.3 1M/NovitaAI/Codex app-server/Qwen Cloud rename(v0.14) + hermes proxy + Pareto min_coding_score
  - prompt-caching-optimization: prompt_caching.cache_ttl 配置, 跨 session 1h Claude prefix cache
  - security-defense-system: v0.13 8 P0 closures + v0.14 sudo brute-force/dangerous-command bypass/tool error sanitization
  - web-tools-architecture: SearXNG, Brave free, DDGS, 按能力拆分 backend, x_search, video_analyze, vision_analyze pixel passthrough, video_generate 可插拔
  - browser-tool-architecture: 180x CDP 持久 WebSocket, cloud metadata SSRF 硬拒
  - voice-mode-architecture: TTS provider registry + Piper 本地, xAI Custom Voices voice cloning
  - mcp-and-plugins: MCP SSE transport + OAuth forwarding, transform_llm_output hook, ctx.llm + tool_override
  - cron-scheduling: no_agent watchdog 模式, prompt-injection 扫描
  - interrupt-and-fault-tolerance: Checkpoints v2 (1638行, max_snapshots pruning, disk guardrails), gateway auto-resume
  - cli-architecture: hermes -z / proxy / acp / curator{archive,prune,list-archived} / kanban 子命令，/goal /subgoal /handoff /steer /queue /reload /reload-skills /mouse 斜杠，PyPI + Windows beta + OSC8 + 16 locale i18n
  - terminal-backends: lazy-install Modal/Daytona/Vercel SDK
  - code-execution-sandbox: Delta lint(v0.13) → LSP 语义诊断(v0.14, agent/lsp/ 11 modules) → file-mutation footer 三层后写校验
  - provider-transport-architecture: ProviderProfile ABC + plugins/model-providers/ 20+ provider 插件化
  - auxiliary-client-architecture: auxiliary.curator 统一配置, auxiliary.prompt_caching.cache_ttl
- README.md: badge 升级 v2026.5.16, changelog 索引 5→8, 跟踪版本 v2026.4.23→v2026.5.16, 最后更新日期 2026-04-29→2026-05-21
- 验证基线: /tmp/hermes-agent clone at 2026-05-21（HEAD 0ce12a9），git tag v2026.5.16 / v2026.5.7 / v2026.4.30 三个 release notes 全文核对
