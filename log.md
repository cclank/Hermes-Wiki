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

## [2026-05-14] update | 同步 v0.12.0 + v0.13.0 + post-release（1,533 commits）

基于 hermes-agent main 分支 `cd64bed55` (2026-05-14) 的逐行源码验证。覆盖 v0.12.0 (2026.4.30, "The Curator Release") + v0.13.0 (2026.5.7, "The Tenacity Release") + v0.13.0 之后的 fix wave。

**新增 changelog（1）**：
- `changelog/2026-05-14-update.md` —— 1,533 commits 综述

**新增概念页（5）**：
- `concepts/kanban-architecture.md` —— v0.13.0 旗舰：持久多 profile 协作看板（`tools/kanban_tools.py` + `hermes_cli/kanban*.py`，~10.9k 行）
- `concepts/goal-loop-architecture.md` —— `/goal` + `/subgoal` Ralph 判官循环（`hermes_cli/goals.py`，722 行）
- `concepts/i18n-localization.md` —— `agent/i18n.py` + 16 个 locale catalog
- `concepts/provider-profile-plugins.md` —— ProviderProfile ABC + 30 个 plugins/model-providers/<name>/
- `concepts/checkpoints-architecture.md` —— Checkpoint v2 单 shared shadow git store + 真 prune

**更新概念页（9）**：
- messaging-gateway-architecture — 20+ 平台（Google Chat 第 20）+ 4 个插件平台 + 多平台 allowlists + Discord guild-scoped 安全 + `[[as_document]]` 媒体路由
- multi-agent-architecture — 从 3 类机制扩到 **5 类**（加入 Goal Loop + Kanban），完整对比表
- skills-system-architecture — Curator 子命令扩张（archive/prune/list-archived，同步 run，per-run 报告）
- web-tools-architecture — 7 个 plugins/web/ 全量插件化，按 capability 独立选 provider
- voice-mode-architecture — TTS provider registry + Piper + xAI Custom Voices
- security-defense-system — Redaction 默认 ON（`agent/redact.py:67` 验证）+ Discord guild-scoped + post-write delta lint + v0.13.0 安全 wave 全表（已验证 vs release notes 声明）
- hook-system-architecture — 17 个 VALID_HOOKS 完整列出 + `transform_llm_output` 详解
- mcp-and-plugins — MCP v0.13.0 升级（SSE OAuth / stale-pipe retry / MEDIA tag / keepalive）
- cli-architecture — 新斜杠命令清单（/goal、/subgoal、/queue、/steer、/kanban、/curator 子命令、/mouse、/indicator）+ `hermes -z` 一次性模式
- smart-model-routing — 链接到 ProviderProfile 插件化

**Top-level**：README（v0.13.0 / 42 页 / 6 changelog）、index.md（同步）

**源码验证摘录**：
- Kanban: `tools/kanban_tools.py:_check_kanban_mode` line 60；9 tool 注册；`hermes_cli/kanban_db.py:VALID_STATUSES` line 93；`SCHEMA_SQL` line 754；`DEFAULT_FAILURE_LIMIT = 2` line 2887
- /goal: `hermes_cli/goals.py` 722 行；`DEFAULT_MAX_TURNS = 20` line 47；`_meta_key(session_id) = f"goal:{session_id}"` line 194；`hermes_cli/commands.py:105-108`
- i18n: `agent/i18n.py:SUPPORTED_LANGUAGES` line 42 列 16 个语言；`locales/` 16 个 YAML 文件
- ProviderProfile: `providers/base.py:ProviderProfile` dataclass line 25；`providers/__init__.py` 描述发现路径；`plugins/model-providers/` 30 个目录
- Checkpoint v2: `tools/checkpoint_manager.py` 1638 行；`_STORE_DIRNAME = "store"` line 72；`prune_checkpoints` line 1223；自动迁移 `legacy-<ts>/` line 340
- Redaction: `agent/redact.py:_REDACT_ENABLED = os.getenv("HERMES_REDACT_SECRETS", "true")` line 67（默认 ON，secure default per #17691）
- Discord guild-scoped: `gateway/platforms/discord.py:2130` "guild-scoped and not cross-guild"
- transform_llm_output: `hermes_cli/plugins.py:136` 在 VALID_HOOKS 中；`run_agent.py:15510-15529` 调度
- video_analyze: `tools/vision_tools.py:1414 registry.register(name="video_analyze")`
- 16 个 locale: `c39168453` (2026-05-10, #22914) 一次性补齐到 16

**未在源码验证 / 保守标注的声明**：
- WhatsApp"默认拒绝陌生人"——当前 `gateway/platforms/whatsapp.py:263` `dm_policy` 默认仍为 `"open"`，wiki 在 security-defense-system.md 显式标注未验证
- 其他 release notes 声明项（TOCTOU 修复、cron prompt-injection 扫描、`hermes debug share` redaction）保留 release notes 描述并明确标注 verification 状态
