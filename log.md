# Wiki Log

> 所有 wiki 操作的按时间顺序记录。只追加，不修改。
> 格式：`## [YYYY-MM-DD] action | subject`
> Actions: ingest, update, query, lint, create, archive, delete
> 当此文件超过 500 条时，轮换：重命名为 log-YYYY.md，重新开始。

## [2026-05-29] sync | hermes-agent 963d22c → 689ef5e2（275 commits, v0.15.0 + v0.15.1）
- 同步范围：hermes-agent/main `963d22c`（2026-05-27）→ `689ef5e2`（2026-05-29），275 个 commit
- 验证基线：`/tmp/hermes-src` blobless clone @ `689ef5e2`，逐 commit + git grep + Read 实证
- 新增文件：`changelog/2026-05-29-update.md`（374 行）
- 更新文件：
  - `README.md` — 版本徽章 `v0.14.0 (963d22c) → v0.15.1 (689ef5e2)`、新增 changelog 徽章、web-tools 行修正（crawl 已移除）、changelog 列表新增 2026-05-29 条目
  - `index.md` — 顶部 tracking 字段、changelog 列表新增 2026-05-29 条目
  - `concepts/web-tools-architecture.md` — 顶部 banner 说明 web_crawl 工具及 crawl backend 描述均为历史信息（#33824 移除）
  - `concepts/mcp-and-plugins.md` — 顶部 banner 加入 mTLS 客户端证书（#33721）+ 工具渐进式披露扩展到 MCP/插件工具
  - `concepts/session-search-and-sessiondb.md` — 顶部 banner 加入 `hermes_state.py:3267 optimize_fts` / `:3306 vacuum` + `hermes sessions optimize` CLI
  - `concepts/smart-model-routing.md` — 顶部 banner 加入 claude-opus-4-8 + gemini-3.5-flash + step-3.7-flash 模型目录更新
  - `concepts/memory-system-architecture.md` — 顶部 banner 加入 `sync_turn` 新增 `messages` 参数（`agent/memory_provider.py:115-133`）
  - `concepts/kanban-multi-agent-board.md` — 顶部加入 2026-05-29 可靠性 wave（terminate 端点 + per-profile 并发 + SQLite 抗撕裂 + close-FD 等）
  - `log.md` — 本条记录
- 核心结论（均经源码验证）：
  - 双版本发布 v0.15.0（`0c859a1c0` #34008）+ v0.15.1（`e71a2bd11` #34222），`pyproject.toml:7 version = "0.15.1"`
  - claude-opus-4-8/4-8-fast：`agent/anthropic_adapter.py:98` / `agent/model_metadata.py:144-145` / `agent/usage_pricing.py:92,104` / `hermes_cli/models.py:35-36,144`
  - 工具渐进式披露扩展到 MCP+插件：`tools/tool_search.py` + 5 个伴随文件（`369075dc9`）
  - MCP mTLS：`tools/mcp_tool.py:573-625 _resolve_client_cert`（`87e5b2fae` #33721）
  - web_crawl 移除：23 文件改动（`5e1f793430` #33824），非测试 `*.py` 已无 `web_crawl` 引用
  - SessionDB optimize_fts + vacuum：`hermes_state.py:3267,3306` + `hermes_cli/main.py:13414,13596`（`38695254f`）
  - Kanban terminate：`plugins/kanban/dashboard/plugin_api.py:1317`（`9d4fda995`），完整路径 `/api/plugins/kanban/runs/{run_id}/terminate`
  - Memory `sync_turn` 加 `messages` 参数：`agent/memory_provider.py:115-133`（`5a95fb2e1`），非新增独立 hook
  - Context Engine pluggable ABC：`agent/context_engine.py:32 class ContextEngine(ABC)`（`9b5dae17a`），plugin 目录 `plugins/context_engine/<name>/`
  - Krea 2：进入 `tools/image_generation_tool.py` 的 `FAL_MODELS`（`6d947e4d7` #33506）；既有 `plugins/image_gen/krea/` 直连后端早在上一次 sync 已存在
  - FAL 视频经 Nous 网关：`plugins/video_gen/fal/__init__.py:326-331`（`d04b3c193`）
  - Skills：skills.sh 858→19,932（sitemap，#34025）、ClawHub 200→20k+（#33748）、NVIDIA tap、新增 `optional-skills/autonomous-ai-agents/{antigravity-cli,grok}/`
  - Docker s6：persist-across-processes（#20561）+ 孤儿回收，config `terminal.docker_persist_across_processes`
  - 安全：Nous 仅 JWT、AWS 子进程凭据剥离、code-exec 审批旁路回归簇（`108397726`/`21aeefe5f`/`655090b3d`/`4bdae3477`）、`API_SERVER_KEY` 必填

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

## [2026-05-23] update | 合并 21 个 daily sync 分支 + 清理重复命名

合并所有 claude/kind-gates-* 定时任务分支到 master（2026-05-02 ~ 2026-05-22 共 21 次 daily sync）：
- 策略: `git merge --no-ff -X theirs`（newer 分支胜出，对齐 hermes-agent 最新源码）
- 保留 21 个 merge commits，每个对应一次日常 snapshot

清理重复命名（同一概念多种文件名 → 保留最新版本）：
- Ralph Loop: 6 个变体 → `goal-and-ralph-loop.md`（删除 persistent-goals-ralph-loop / persistent-goals / goals-and-ralph-loop / goal-loop-architecture / goal-loop-and-steering）
- Kanban: 8 个变体 → `kanban-multi-agent-board.md`（删除 kanban-multi-profile-board / kanban-collaboration-board / kanban-multi-agent / kanban-architecture / kanban-system / kanban-orchestration / multi-agent-kanban）
- i18n: 2 个变体 → `i18n-and-locales.md`（删除 i18n-localization）
- Provider plugin: 2 个变体 → `provider-plugin-system.md`（删除 provider-profile-plugins）

新增页面（来自定时任务，已源码核对仍然有效）:
- tool-loop-guardrails (v0.12.0)
- checkpoints-architecture (v0.13.0)
- lsp-integration (v0.14.0)
- i18n-and-locales (v0.13.0)
- provider-plugin-system (v0.13/v0.14)
- hermes-proxy (v0.14)
- kanban-multi-agent-board (v0.13+)
- goal-and-ralph-loop (v0.13/v0.14)

最终状态：45 概念页 + 2 实体页 + 26 changelog，跟踪 hermes-agent v0.14.0

## [2026-05-24] update | 同步 hermes-agent/master HEAD `186bf25`（84 commits daily delta）

- 对比基准: wiki master HEAD `4a950eb`（2026-05-23 sync at `874c2b1`），hermes-agent/master HEAD `186bf25`（2026-05-24 04:33 -0700）
- 跨度 ~24 小时，**84 个 commit**（45 fix / 9 feat / 12 test / 5 docs / 5 chore / 3 refactor / 5 security），版本仍为 v0.14.0；验证基线 `/tmp/hermes-agent` clone @ `186bf25`
- **新建 changelog/2026-05-24-update.md**（11 章 + 文件矩阵），所有 file:line 引用经 grep / Read 落地
  - 安全 Wave 2（17 个 commit 时间集中在 04:24–04:54 -0700）—— Webhook fail-closed + Svix + 403、Dashboard WebSocket 强制 loopback、Docker dashboard 默认 loopback、Feishu/QQBot/Discord/DingTalk/MSGraph 审批授权链、API server placeholder secret、`response_store.db` + `webhook_subscriptions.json` 0o600、CodeQL 日志最小化
  - ntfy 第 23 平台（3 提交链：feat → refactor 为 plugin → robust 加固）
  - Plugin `register_auxiliary_task()` 新 hook API
  - 跨 Profile 文件写入软护栏（`agent/file_safety.classify_cross_profile_target` + 三层接入）
  - Streaming 完成可见性三连（guardrail halt 推到 stream / `response_transformed` 编辑 in-place / partial-stream `finish_reason=length`）
  - Kanban `promote` 子命令（含 `--ids` bulk）+ `promoted_manual` 事件类型
  - Skills AST 深度诊断（`audit --deep` / `inspect`）—— diagnostic hints 不影响 install gate
  - Bitwarden EU + 自托管 server URL 支持
  - `config.yaml model.provider` 单一 source of truth（删 `HERMES_INFERENCE_PROVIDER` env override）
  - 平台/Tooling 修复簇（WeCom flush race / WeCom-callback token refresh / DingTalk finalize streaming / Telegram group slash / TUI viewport resize / Windows taskkill /T /F / browser 进程树终止 / mcp stdio ImportError / `.env` null-byte / Qwen refresh / TUI slash dropdown / TTS indicator / tool failure suffix / todo fraction / `tool_progress` 与 verbose 解耦）
- **更新 12 个 concept 页面**：
  - security-defense-system — 末尾追加"v0.14 增量安全 wave 2"，覆盖 17 个安全 commit + 跨 profile 软护栏（引 `webhook.py:383-395, 690+ + feishu.py:3293-3306 + msgraph_webhook.py:133-145, 316 + web_server.py:3296-3305 + auth.py:553-560 + api_server.py:337-385 + qqbot/adapter.py + base.py:4-7 + file_safety.py:312-373`）
  - messaging-gateway-architecture — 22→23 平台（ntfy 插件），加 2026-05-24 平台细节修复簇章节
  - hook-system-architecture — 顶部加 `register_auxiliary_task` API 引用；v2026.5.x 节追加详细说明（`hermes_cli/plugins.py:703-784`）
  - auxiliary-client-architecture — 加"Plugin 注册新 auxiliary task slot"小节（含 `gateway/run.py:780-820` 桥接代码）
  - kanban-multi-agent-board — 顶部加 2026-05-23 更新 note；CLI 表加 `promote` 子命令（含 `--ids` / `--force` / `--dry-run` / `--json`）
  - skills-system-architecture — 末尾加 AST 深度诊断节（`tools/skills_ast_audit.py:84` + 与 Skills Guard 职责分离说明）
  - cli-architecture — 工具调用预览段加失败具体错误 + todo 分数；新表 `hermes kanban promote` / `hermes skills audit --deep`；新增"安全/UX 微调"节
  - terminal-backends — 加 `background=true` 静默 hint + Windows `taskkill /T /F` 章节
  - interrupt-and-fault-tolerance — 加"Streaming 完成可见性三连"章节（guardrail halt + response_transformed 链 + partial-stream finish_reason）
  - mcp-and-plugins — v0.13.0 表后加 v0.14.0 stdio SDK ImportError 修复
  - context-compressor-architecture — 加 ABC 合规修复节（`total_tokens` / `api_mode` / 31 处 logger 切换）
  - smart-model-routing — 加 `config.yaml model.provider` 单一 source of truth 章节
  - agent-loop-and-prompt-assembly — 加 3 节：跨 Profile 软护栏 / Plugin `transform_llm_output` 流式抗冲突 / Background reviewer 允许改 pinned
- **README.md / index.md / log.md**：跟踪 HEAD `874c2b1` → `186bf25`，最后更新 2026-05-23 → 2026-05-24，changelog 27 → 28
- 验证策略: 每条结论都至少一条 grep / Read 命中 `/tmp/hermes-agent`；每个 file:line 引用现行 source 实际行号；功能描述对照对应 PR 标题 + commit body + 实际 hunk

## [2026-05-23] update | 同步 hermes-agent/master HEAD `874c2b1`（49 commits daily delta）

- 对比基准: wiki master HEAD `2c31589`（2026-05-22 evening sync），hermes-agent/master HEAD `874c2b1`（2026-05-23 13:31 -0500）
- 跨度 ~24 小时，49 commits，版本仍为 v0.14.0（未跨 minor）；验证基线 `/tmp/hermes-agent` clone @ `874c2b1`
- **新建 changelog/2026-05-23-update.md**（按主题分 10 章 + 文件矩阵），所有 file:line 经 grep / Read 核对
  - Nous Portal 一等公民（PR #30860, b4cf5b6）
  - Kanban DB 抗污染（#30858 + #30862 + #30949 + #30952）
  - Memory.md/USER.md 外部漂移防护（#30877 / #26045）
  - 审批"沉默 ≠ 同意"契约（#30879 / #24912）
  - TLS FD 回收三层防御（#29507）
  - GHSA-5qr3-c538-wm9j 第二段 Plugin RCE（#29156）
  - Gateway/Provider/平台细节修复簇（webhook INSECURE_NO_AUTH、telegram in-place edit、whatsapp JID/LID、qqbot intent+op7/9+SILK、opencode-go reasoning、xAI OAuth WKE）
  - TUI 三连（composer burst / lifecycle log / late thinking deltas）
  - Skills guard `--force` 文案纠偏
- **更新 6 个 concept 页面**：
  - cli-architecture.md — 新增 `hermes setup --portal` + `hermes portal` 三子命令章节 + 子命令表 + 文件索引；引 `portal_cli.py:39-181` + `setup.py:3063-3173` + `main.py:11877-11880`
  - kanban-multi-agent-board.md — 新增"DB 抗污染"+"Scratch workspace 可见性"两节；引 `kanban_db.py:1010-1132`（`KanbanDbCorruptError` + `_guard_existing_db_is_healthy`）+ `:1029-1074` 备份硬化 + `:3109-3181` scratch tip
  - memory-system-architecture.md — 安全扫描前插入"外部漂移防护"小节；引 `memory_tool.py:482-530 _detect_external_drift` 双信号 + `:108-130 _drift_error` + 三 mutator 拒绝路径
  - security-defense-system.md — 末尾追加"v0.14 增量安全 wave (2026-05-23)" 4 小节（silence 契约 / Plugin RCE 双保险 / webhook 动态路由 INSECURE_NO_AUTH / skills_guard 文案）；引 `approval.py:1301-1330` + `web_server.py:4050,4547` + `webhook.py:329-339`
  - interrupt-and-fault-tolerance.md — 新增"TLS FD 回收竞态三层防御"章节；引 `agent_runtime_helpers.py` shutdown-only + `chat_completion_helpers.py:97-141,1312-1345` thread-aware close
  - messaging-gateway-architecture.md — Telegram 段加 `send_or_update_status` in-place edit；WhatsApp 段加 JID/LID alias；QQBot 段加 intent/op7-9/SILK 修复簇
  - provider-plugin-system.md — 加 OpenCode Go reasoning controls 小节
- **README.md / index.md** badge & changelog 索引：26 → 27 changelogs，"最后更新" 2026-05-22 → 2026-05-23，跟踪 HEAD 标注为 `874c2b1`
- 验证策略: 每条结论都至少一条 grep / Read 命中源码；功能描述对照对应 PR 标题 + commit body + 实际 hunk 内容

## [2026-05-25] ingest | 跨日同步 hermes-agent 175 commits（`186bf25` → `b62af47`）
- 输入: `git clone NousResearch/hermes-agent` @ `b62af47`（`2026-05-25 19:30 -0700`，msg "drop stale line-number reference in PRIORITY path comment"）
- 范围: 自 wiki HEAD `9ea95c0` = hermes `186bf25` 起 175 个新 commit（90 `fix`、22 `test`、19 `chore`、18 `feat`、9 `docs`、3 `ci`、1 `perf`、1 `refactor`、1 `harden`），跨 2026-05-23 ~ 2026-05-25 三天，其中 79 commits 集中在 05-25
- 新增 1 个 changelog 页面：
  - changelog/2026-05-25-update.md（约 350 行）—— 主题：**Docker s6-overlay PID 1 BREAKING + 容器化运行时监管**、**安全 wave 3**（25 commits：symlink/`.env`/`/proc/*`/YOLO frozen/GHSA-rhgp-j443-p4rf 二次合规/凭据持久化 ×7）、**`hermes security audit` OSV.dev 一次性供应链扫描**（feat）、**CLI 冷启动 -63%**（Bitwarden 磁盘 L2 cache）、**`register_tts_provider()` / `register_transcription_provider()` plugin hook**（feat ×2）、**`openai-api` 新 Provider**（`/v1/models` 直拉 + gpt-5.5-pro）、**CredentialPool 周配额轮换正确性**（fix）、**Gateway 在飞子 Agent 抗 busy-mode 中断**（PR #30170）、**Mattermost 迁移为 bundled plugin**、**MCP OAuth 无头 paste-back 三连**、**Codex Responses-API TTFB watchdog + 上下文 token 估算修复**、**mid-tool-call partial-stream-stub 走 `finish_reason=length` 续传**、**Auxiliary 统一 main-model fallback**（PR #31845）、**Nous OAuth 401 actionable guidance**、**`/resume` 编号选择 + recap 调优键**、**`/q` 改属 `/queue`**
- 源码已验证存在：
  - `hermes_cli/security_audit.py` 576 行（`OSV_BATCH_URL` line 35，severity ord、Component dataclass）
  - `hermes_cli/security_advisories.py` 451 行
  - `agent/tts_registry.py` 133 行（`_BUILTIN_NAMES` = `{edge,elevenlabs,openai,minimax,xai,mistral,gemini,neutts,kittentts,piper}` line 48）
  - `agent/transcription_registry.py` 122 行（`_BUILTIN_NAMES` = `{local,local_command,groq,openai,mistral,xai}` line 40）
  - `hermes_cli/service_manager.py` 886 行（`ServiceManager(Protocol)` line 54、`S6ServiceManager` line 536、`_seed_supervise_skeleton` line 351-440 解决非特权 EACCES）
  - `hermes_cli/container_boot.py` 218 行
  - `plugins/platforms/mattermost/adapter.py` 1192 行（plugin.yaml + `register(ctx)` + 5-hook 模型）
  - `tools/approval.py:29 _YOLO_MODE_FROZEN: bool = is_truthy_value(os.getenv("HERMES_YOLO_MODE", ""))`（模块导入时一次性求值，gates @ line 948 + 1089）
  - `tools/tts_tool.py:339 BUILTIN_TTS_PROVIDERS`（与 registry 镜像）
  - `tools/transcription_tools.py:226 BUILTIN_STT_PROVIDERS`
  - `hermes_cli/providers.py:63 "openai-api": HermesOverlay(...)` + `hermes_cli/models.py:202,943,2245`
  - `hermes_cli/main.py:6212-6215 cmd_security_audit` 注册
  - `hermes_cli/plugins.py:645,683,785` PluginContext API（`register_tts_provider` / `register_transcription_provider` / `register_auxiliary_task`）
  - `hermes_cli/config.py:1026 "resume_skip_tool_only": True`
  - `docker/main-wrapper.sh` 30 行 + `docker/stage2-hook.sh` 142 行 + `docker/s6-rc.d/{main-hermes,dashboard,user}/`
- 关键 commit 用 `git show <sha> --stat` + `head -50` 抽样核对：`e0e9c895d` (s6 BREAKING) / `2afefc501` (per-profile s6) / `7ab167736` (security audit, 943 行新增) / `0219b0408` (perf -63%) / `4117fc364` (cred-pool 周配额, 4 文件 189+/50-) / `99d62f6ba` (subagent interrupt protection) / `af973e407` (mattermost plugin, 1244 NEW) / `4cb3eb03c` (YOLO frozen) / `3ab7e2aa9` (GHSA filter) / `dbe5d8497` (universal main-model fallback) / `ac5359a3f` (partial-stream length) / `2d422720b` + `8601c4d44` (Codex Responses-API)
- 测试增量约 +2200 行（security_audit 299 / container_boot 235 / profiles_s6_hooks 190 / container_restart 168 / gateway_s6_dispatch 117 / yolo+approval ~120 / Codex ~200 / 其它）
- **README.md / index.md** badge & changelog 索引：28 → 29 changelogs，"最后更新" 2026-05-24 → 2026-05-25，跟踪 HEAD 标注 `186bf25` → `b62af47`
- 验证策略: 每条结论都至少一条 `grep -n` / `Read` 命中源码；功能描述对照对应 PR 标题 + commit body + 实际 hunk 内容


## [2026-05-26] ingest | 跨日同步 hermes-agent 37 commits（`b62af47` → `556bf7c5c`）
- 输入: `git clone NousResearch/hermes-agent` @ `556bf7c5c`（`2026-05-26 23:23 -0700`，msg "test(cron): guard schedule-required description text on CRONJOB_SCHEMA"）
- 范围: 自 wiki HEAD `c112148` = hermes `b62af47` 起 37 个新 commit（18 `fix`、7 `feat`、6 `chore`、4 `test`、1 `refactor`、1 `harden`），版本仍 v0.14.0；验证基线 `/home/user/hermes-agent` clone @ `556bf7c5c`
- 新增 1 个 changelog 页面：
  - changelog/2026-05-26-update.md（约 19 章 + 文件矩阵）—— 主题：**Promptware 防御 — 共享威胁模式库 252 行 + Memory load-time scan + `<untrusted_tool_result>` 工具结果分隔符**（feat #32269）、**Nous-approved MCP 目录 + 交互式选择器**（feat #30870，`optional-mcps/{n8n,linear}` + `hermes_cli/mcp_catalog.py` 776 行 + `mcp_picker.py` 322 行 + `mcp_config.py` 803 行）、**Skills Hub 健康检查 + 新鲜度徽章 + 4h watchdog cron**（feat #32345）、**3 个新可选 skill**（`web-pentest` #32265 / `openhands` #477 / `code-wiki` #486）、**Patch 工具三连**（缩进保留 + CRLF 保留 + per-file 失败升级，feat #507/#32273）、**Cron 扫描器二级分裂**（strict 用户 prompt + loose skill assembled，fix #32339）、**Skill install 拒绝符号链接**（fix）、**Dashboard 插件资源 suffix-allowlist + 子进程影响型 env 变量 denylist**（fix #32277）、**Markdown 链接 scheme 收紧 + WeCom callback defusedxml**（harden）、**AGENTS.md 限定工作目录内载入**（fix）、**Telegram DM topic 投递 6 连**（路由直发 / anchor 要求 / 自动 create / 刷新过期 thread / 简化 refresh / `reply_to_mode=off` 豁免）、**Anthropic API-key 路径跳过 OAuth autodiscovery**（fix）、**外部 secrets 每 HERMES_HOME 每进程仅应用一次**（fix #32271）、**Gateway `/model --global` scalar→dict coerce**（fix #32272）、**Agent outer-loop ERROR + traceback**（fix #32264）、**Cron schedule 在 create 模式必填**（fix #32427）、**qwen3.6-plus → qwen3.7-max** 同步 / 移除 grok-4-1-fast、**TTS 双 `[pause]` 修复**（fix #29417）、**CLI fallback paste collapse**（fix #32447）、**Telegram 表格 row-group 间距收紧**（fix）
- 源码已验证存在：
  - `tools/threat_patterns.py` 252 行（`_PATTERNS` line 49-115、`INVISIBLE_CHARS` line 116-137、`scan_for_threats` line 188-225、`first_threat_message` line 228-244、3 scope all/context/strict）
  - `tools/memory_tool.py:133-208`（`load_from_disk` + `_sanitize_entries_for_snapshot` 在 frozen snapshot 中替换 `[BLOCKED: ...]`；live state 保留原文）
  - `agent/tool_dispatch_helpers.py:320-396`（`make_tool_result_message` line 320、`_UNTRUSTED_TOOL_NAMES = {"web_extract", "web_search"}` line 354、`_UNTRUSTED_TOOL_PREFIXES = ("browser_", "mcp_")` line 358-361、`_UNTRUSTED_WRAP_MIN_CHARS = 32` line 363、`_maybe_wrap_untrusted` line 371-396）
  - `hermes_cli/mcp_catalog.py` 776 行（`_parse_manifest` line 151、`install_entry` line 670、`uninstall_entry` line 755）
  - `hermes_cli/mcp_picker.py` 322 行（`_Row` line 55、`run_picker` line 274、`_handle_row` line 160-228）
  - `hermes_cli/mcp_config.py` 803 行
  - `hermes_cli/main.py:13023-13046`（mcp picker / catalog / install 子命令注册）
  - `optional-mcps/n8n/manifest.yaml`、`optional-mcps/linear/manifest.yaml`（manifest_version: 1，stdio+api_key+git-bootstrap / http+native OAuth）
  - `scripts/build_skills_index.py:330-348`（`EXPECTED_FLOORS` + `MIN_TOTAL=1500` + sys.exit(2)）
  - `.github/workflows/skills-index-freshness.yml` 149 行（每 4h cron）
  - `tools/skills_hub.py:3046-3058`（`install_from_quarantine` rglob + `_is_path_redirect` 拒符号链接）
  - `optional-skills/security/web-pentest/SKILL.md`、`optional-skills/autonomous-ai-agents/openhands/SKILL.md`、`optional-skills/software-development/code-wiki/SKILL.md` + 4 模板（templates/README.md / architecture.md / getting-started.md / module.md）
  - `tools/fuzzy_match.py:185-258 _reindent_replacement` + line 274 非 exact only 调用
  - `tools/file_operations.py:77-103, 741-760, 1047, 1167`（`_detect_line_ending` + 4096 byte 探测 + write/patch CRLF normalize）
  - `tools/file_tools.py:257-292, 1080-1095`（`_patch_failure_tracker` + 失败 #3+ 升级 hint）
  - `tools/cronjob_tools.py:186-227`（`_scan_cron_prompt` strict + `_scan_cron_skill_assembled` loose）+ `cron/scheduler.py:1170-1191`（按 `has_skills` 路由）
  - `hermes_cli/web_server.py:4546-4612`（`/dashboard-plugins/<name>/<path>` 仅放 17 suffix → 404）
  - `hermes_cli/config.py:117-152`（`_ENV_VAR_NAME_DENYLIST` frozenset 37 项 + `_reject_denylisted_env_var`）
  - `gateway/platforms/wecom_callback.py:20-24`（defusedxml.ElementTree + `DEFUSEDXML_AVAILABLE` flag）
  - `web/src/components/Markdown.tsx:324-345`（链接 scheme allowlist http(s)/mailto）
  - `agent/subdirectory_hints.py:49-57, 169-220`（`is_relative_to(working_dir)` 强制 + `_is_ancestor_or_same` fallback）
  - `gateway/delivery.py`（`_looks_like_telegram_private_chat_id` + DM topic 直发分支）
  - `hermes_cli/env_loader.py:32-40 _APPLIED_HOMES`（per-HERMES_HOME 去重 set）
- 关键 commit 用 `git show <sha> --stat` + `--format=full` 抽样核对：`0dee92df2`（promptware defense 三模块）/ `8b69ec03a`（MCP catalog 1901 行新增）/ `d8703e27f`（skills-hub health workflow 149 行）/ `cea87d913`（catalog source 全显示）/ `5671461c0` / `386f245d9` / `263e008d6`（三新 skill）/ `6bd0be30b`（patch 三连）/ `ccd899318`（cron scanner 二级）/ `c26af4681`（skill symlink reject）/ `30928f945`（dashboard allowlist + env denylist）/ `5744b1757` + `31c8d5ff5`（markdown scheme + WeCom defusedxml + extras）/ `f4953bc64`（subdir hints scope）/ `415be5539` + 5 跟进（Telegram DM topic）/ `e3236e99a`（Anthropic API-key skip OAuth）/ `de76f4dbc`（external secrets once）/ `2c6bbaf35`（gateway /model scalar coerce）/ `c2aa23532`（outer-loop logger）/ `51013268c` + `556bf7c5c`（cron schedule required）/ `ccd3d04fc` + `bbc8f2f96`（model swap/drop）/ `1d73d5fac` + `5caeb65a0`（TTS [pause]）/ `2517917de`（CLI paste collapse）/ `9d10c45e3`（Telegram 表格 row-group）
- 更新 9 个 concept / docs 页面：
  - security-defense-system.md — 新增"v0.14 增量 — 2026-05-26 Promptware 防御 + Posture 硬化簇"大节，覆盖 共享威胁模式库 + Memory load-time scan + `<untrusted_tool_result>` 工具结果分隔符 + 符号链接拒绝 + Dashboard suffix-allowlist + env denylist + Markdown scheme + WeCom defusedxml + AGENTS.md scope + Anthropic API-key skip OAuth + Cron 扫描器二级分裂（引 `threat_patterns.py:49-115` + `memory_tool.py:174-208` + `tool_dispatch_helpers.py:320-396` + `skills_hub.py:3046-3058` + `web_server.py:4546-4612` + `config.py:117-152` + `wecom_callback.py:20-24` + `subdirectory_hints.py:49-57,169-220`）；frontmatter sources / updated 同步
  - memory-system-architecture.md — "安全扫描" 节升级为"双层 + Load-Time Snapshot 净化"，加 Layer A / Layer B 二分 + BLOCKED 占位 + live state 双轨原则 + prefix cache 不变量 + 威胁模型 poison 来源 + scope strict 集示例
  - prompt-builder-architecture.md — "上下文文件注入防护" 节迁移到共享 `tools/threat_patterns.py`，加 scope 三分表 + 模式哲学 + 17 invisible unicode codepoint
  - mcp-and-plugins.md — 新"Nous-Approved MCP Catalog" 大节，覆盖三入口 CLI + manifest schema + 仓内两参考条目 + 设计原则 + 三模块拆分表
  - skills-system-architecture.md — 新"Skills Hub 健康监控"节（`EXPECTED_FLOORS` + watchdog cron）+ "Skill Install 拒绝符号链接"节 + "新增 Optional Skills"表（web-pentest / openhands / code-wiki）
  - cron-scheduling.md — "prompt-injection 扫描器二级分裂" 节升级（strict vs loose 表 + scheduler.py:1170 路由）+ "Cron Schedule 必填 — Schema 描述显式化" 节
  - messaging-gateway-architecture.md — "Telegram DM Topic 投递 6 连"节 + "Telegram 表格 Row-Group 间距收紧" + "WeCom Callback defusedxml + Lazy Dep"节；frontmatter sources 加 `gateway/delivery.py` + `wecom_callback.py`
  - agent-loop-and-prompt-assembly.md — "高风险工具结果 `<untrusted_tool_result>` 包裹" 节（高风险工具集 + 包裹格式 + 5 项包裹策略 + 设计取舍）+ "Agent Outer-Loop 异常日志" 节
  - fuzzy-matching-engine.md — "2026-05-26 Patch 工具三连增强" 大节（缩进保留算法 + CRLF 保留 + per-file 失败升级 + 测试增量）
- README.md / index.md badge & changelog 索引：29 → 30 changelogs，"最后更新" 2026-05-25 → 2026-05-26，跟踪 HEAD 标注 `b62af47` → `556bf7c5c`（badge 用 short hash `556bf7c`）
- 验证策略: 每条结论都至少一条 `grep -n` / `Read` 命中 `/home/user/hermes-agent` clone；每个 file:line 引用现行 source 实际行号；功能描述对照对应 PR 标题 + commit body + 实际 hunk 内容


## [2026-05-27] ingest | 跨日同步 hermes-agent 645 commits（`556bf7c5c` → `963d22c`）
- 输入: `git clone NousResearch/hermes-agent` @ `963d22c`（`2026-05-27 13:55 -0700`，msg "test(install): harden uv-python-path regression test against future drift"），hermes 远端默认分支由 `master` 改名 `main`
- 范围: 自 wiki HEAD `e4d2175` = hermes `556bf7c5c` 起 645 个新 commit（312 fix、79 feat、78 chore、42 test、27 docs、19 refactor、11 infographic、10 perf、7 ci、3 security），多个 PR 长期 feature branch 集中合并；版本仍 v0.14.0；验证基线 `/tmp/hermes-agent` clone @ `963d22c`
- 新增 1 个 changelog 页面：
  - changelog/2026-05-27-update.md（约 19 章 + 文件矩阵）—— 主题：**Dashboard OAuth 鉴权闸门 Phase 0-7 整体落地**（`hermes_cli/dashboard_auth/` 10 文件 1868 行 + Nous Portal Provider 582 行 + WS 30s 单次性 ticket）、**Honcho AI-native 跨会话用户建模 MemoryProvider**（5 文件 5158 行 + identity-mapping single/multi/hybrid wizard）、**Krea 图像生成 Provider 插件**（548 行，Krea 2 Medium/Large）、**security-guidance 插件**（25 条 dangerous-pattern Apache-2.0 fork #33131）、**TUI Session Orchestrator**（in-TUI 多 session 同屏 635 行）、**API Server 三连**（Session CRUD + GET /v1/skills + /v1/toolsets #33016）、**Windows 原生支持收官 v0.14 beta**（UTF-8 stdio shim / Scheduled Task / install.ps1 加固 / 79+63 skill platforms）、**Docker wave**（Node 22 LTS multi-stage + chown 链 + s6 env 转译）、**Codex Responses-API 14 修复**（drop responses.stream() helper + null/large/encrypted_content recovery）、**xAI 模型退役迁移工具链**（hermes migrate xai + ruamel round-trip）、**xAI Web Search provider 插件**（第 8 个 web provider）、**Telegram 19 修复**（in-place edit + DM topic + heartbeat 原地 + 2GB skip-STT + ignore_root_dm）、**性能 wave**（agent-loop -47% via load_config_readonly + terminal poll -195ms + cold start -19s）、**Bitwarden EU + self-hosted server URL #31378**、**BrowseShSource 第 8 个 skill catalog**（Browserbase 200+ 站点）、**hermes update --branch + post-pull syntax-validate auto-rollback #28669/#26172**、**Nix #messaging / #full 包变体 #33108**
- 新增 1 个 concept 页面：
  - concepts/dashboard-auth-oauth-gate.md（约 280 行）—— 完整新架构页：DashboardAuthProvider ABC + Session/LoginStart dataclass + 3 类异常映射、Registry 进程级单例、Middleware 闸门白名单、Cookie 体系（__Host-/__Secure-）、WS 单次性 ticket、Nous Portal Provider 协议要点、Phase 0-7 时间线、fail-closed 与 hardening、loopback vs gated 对比、测试矩阵；引 `hermes_cli/dashboard_auth/{base.py:65,middleware.py:32,routes.py,ws_tickets.py:30,cookies.py,login_page.py,prefix.py,audit.py,registry.py}` + `plugins/dashboard_auth/nous/__init__.py` + `hermes_cli/plugins.py:558`
- 更新 7 个 concept 页面：
  - hook-system-architecture.md — 顶部增 "2026-05-27 新增钩子" 表（`register_dashboard_auth_provider:558` + `standalone_sender_fn`），PluginContext 8 个 register_* 全表（image_gen/dashboard_auth/video_gen/web_search/browser/tts/transcription/auxiliary_task）；`register_auxiliary_task` line 由 703 修正到 825
  - memory-system-architecture.md — 顶部增 "2026-05-27 增量 — Honcho Memory Provider 全 identity-mapping wave" 大块，覆盖 5 个 honcho_* 工具 + 配置 chain + identity-mapping 三 shape + `pinUserPeer ↔ pinPeerName` 别名链 + 6 个 honcho 修复簇 + gateway 集成；frontmatter sources / updated / tags 同步
  - security-defense-system.md — 末尾追加 "v0.14 增量 — 2026-05-27 Wave 4" 大节，覆盖 Dashboard OAuth + security-guidance + 凭据/Webhook/file-safety 加固簇 + v0.14 增量信息汇总表（Wave 1-4 时段分类）；frontmatter sources 加 dashboard_auth + security-guidance 文件路径
  - cli-architecture.md — 新增 "v0.14 增量 — 2026-05-27" 大节，覆盖 hermes migrate xai 命令 + hermes update --branch + Dashboard OAuth 配置 surface + TUI Session Orchestrator + Bitwarden EU + Nix 包变体 + API Server 三连 + 性能微调（load_config_readonly）
  - messaging-gateway-architecture.md — 新增 "2026-05-27 wave" 大节：Telegram 19 修复表 + API Server CRUD + Signal/Google Chat/Slack 小修 + Voice-mode 容器化音频桥 + SQLite NFS fallback；frontmatter sources 加 api_server.py
  - auxiliary-client-architecture.md — 新增 "v0.14 增量 — Codex Responses API 修复簇（2026-05-27 wave）" 大节：14 个 Codex 修复表 + Provider fallback 凭据池隔离 + switch_model 失败 rollback；`register_auxiliary_task` line 由 703 修正到 825
  - web-tools-architecture.md — provider 表 7 → 8 加 xAI Web Search 行 + Firecrawl integration tag 注释
  - skills-system-architecture.md — 新增 "BrowseShSource — 第 8 个 catalog 源（2026-05-27 NEW）" 大节 + "Skills 修复簇（2026-05-27 NEW）" 表（atomic lock / preserve packages / backfill provenance / nested install paths 等 7 条）+ "7 个 Linux/macOS-only Skills 在 Windows 上 gate" 节
- 源码已验证存在（关键样本）：
  - `hermes_cli/dashboard_auth/base.py:65 DashboardAuthProvider` + `:9 Session` + `:125 assert_protocol_compliance` （共 158 行）
  - `hermes_cli/dashboard_auth/middleware.py:32 _GATE_PUBLIC_PREFIXES`（共 207 行）
  - `hermes_cli/dashboard_auth/ws_tickets.py:27 TTL_SECONDS=30` + `:32 mint_ticket` + `:55 consume_ticket`（共 87 行）
  - `hermes_cli/dashboard_auth/registry.py:23 register_provider` + `:49 list_providers`（共 58 行）
  - `plugins/dashboard_auth/nous/__init__.py`（582 行，RS256 + JWKS 5min cache + agent_dashboard:access scope + agent_instance_id claim 校验）
  - `hermes_cli/plugins.py:558 register_dashboard_auth_provider`（明 hook + ABC 类型校验 + try/except 降级为 warning 不让 host 崩）
  - `plugins/memory/honcho/__init__.py:191 HonchoMemoryProvider` + `:33-188` 5 个工具 schema（1327 行）
  - `plugins/memory/honcho/client.py:495-505 pinUserPeer/pinPeerName` 4-key 别名链解析（840 行）
  - `plugins/memory/honcho/cli.py:431 cmd_setup` + `:512-600` deployment-shape 三 shape wizard（1650 行）
  - `gateway/run.py:1791,15109-15121` honcho session managers + doctor 暴露
  - `plugins/image_gen/krea/__init__.py:50 _MODELS` + `:161 KreaImageGenProvider` + `:546-548 register(ctx)`（548 行；Krea 2 Medium/Large）
  - `plugins/security-guidance/patterns.py:53 SECURITY_PATTERNS`（25 条；368 行）
  - `plugins/security-guidance/__init__.py`（259 行；transform_tool_result + pre_tool_call hook）
  - `ui-tui/src/components/activeSessionSwitcher.tsx`（635 行）
  - `tui_gateway/server.py` +221 行（TUI session orchestrator 后端 RPC）
  - `gateway/platforms/api_server.py` +476 行（session controls + /v1/skills + /v1/toolsets）
  - `hermes_cli/config.py:4579 load_config_readonly` + `hermes_cli/timeouts.py:22,51`（agent-loop -47% 性能修复）
  - `hermes_cli/xai_retirement.py`（253 行，纯逻辑） + `hermes_cli/migrate.py:cmd_migrate_xai` + `hermes_cli/main.py:11265-11297 migrate_xai` 子命令注册
  - `plugins/web/xai/plugin.yaml` + `provider.py`（第 8 个 web provider）
  - `tools/skills_hub.py:2429 BrowseShSource(SkillSource)`（catalog https://browse.sh/api/skills + skillMdUrl CDN）
- 关键 commit 用 `git show <sha> --stat` 抽样：`8773bbf` / `2dc6d03` / `c32b17f` / `848baeb` / `b69fce9` / `2fc4615` / `848baeb` / `c310419` / `4272977` / `b3dc539`（dashboard auth Phase 0-7）；`2e3c662` / `0bac880` / `1a8e670` / `c03960d` / `eccbbe4`（honcho 15 子修复）；`9919caf` (Krea) / `249534e` (security-guidance) / `0a83247` (TUI orchestrator) / `f7527b0` (api_server session) / `25f43d3` (api_server /v1/skills #33016) / `cb38ce2` + `b6ca56f` + `e8955f2` (Codex 修复); `0ec052c` (cold start -19s) / `544c31b` (47% agent-loop perf) / `6bd4311` (terminal poll -195ms); `12842d3` + `9ff98da` + `6f3a020` (xAI migrate); `a0c0312` (xAI Web Search); `57145ca` (BrowseShSource); `bc3f1f4` (Bitwarden EU)
- README.md / index.md badge & changelog 索引：30 → 31 changelogs，"最后更新" 2026-05-26 → 2026-05-27，跟踪 HEAD 标注 `556bf7c5c` → `963d22c`（badge short hash `963d22c`），跟踪远端分支由 `master` 改为 `main`，**concept 页面 45 → 46**（新增 [[dashboard-auth-oauth-gate]]）
- 验证策略: 每条结论都至少一条 `grep -n` / `Read` 命中 `/tmp/hermes-agent` clone @ `963d22c`；每个 file:line 引用现行 source 实际行号；功能描述对照对应 PR 标题 + commit body + 实际 hunk 内容；645 commit 量级下重点抓 19 个 feat + 3 security + 11 perf 上游 PR 验证
