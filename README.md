# Hermes Agent Architecture Wiki

<p align="center">
  <img src="https://img.shields.io/badge/Wiki-Hermes_Agent-blue?style=for-the-badge&logo=markdown" alt="Wiki" height="28">
  <img src="https://img.shields.io/badge/Source-hermes--agent-green?style=for-the-badge&logo=github" alt="Source" height="28">
  <img src="https://img.shields.io/badge/Knowledge_Base-46_pages-orange?style=for-the-badge&logo=obsidian" alt="Knowledge Base" height="28">
  <img src="https://img.shields.io/badge/Changelogs-32-blueviolet?style=for-the-badge" alt="Changelogs" height="28">
  <img src="https://img.shields.io/badge/Version-v0.15.1_(689ef5e2)-purple?style=for-the-badge" alt="Version" height="28">
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
- [provider-plugin-system](concepts/provider-plugin-system.md): **NEW v0.13.0** ProviderProfile ABC + 30 个插件化 provider

### 记忆与会话

- [memory-system-architecture](concepts/memory-system-architecture.md): 三层架构（MemoryStore/MemoryManager/MemoryProvider），冻结快照模式
- [session-search-and-sessiondb](concepts/session-search-and-sessiondb.md): FTS5 搜索 + LLM 摘要的跨会话回忆，orphan 删除策略
- [context-compressor-architecture](concepts/context-compressor-architecture.md): 自动上下文压缩 v3
- [skills-and-memory-interaction](concepts/skills-and-memory-interaction.md): Skills 与 Memory 的互补关系和决策树
- [skills-system-architecture](concepts/skills-system-architecture.md): 渐进式披露架构 + Curator 后台维护（v0.13 新增 archive/prune/list-archived）

### 工具与能力

- [browser-tool-architecture](concepts/browser-tool-architecture.md): 多后端浏览器自动化，accessibility tree+三层安全防护
- [web-tools-architecture](concepts/web-tools-architecture.md): 八大后端插件化搜索/提取（WebSearchProvider ABC + 注册表），LLM 智能内容压缩（**web_crawl 工具于 2026-05-29 移除 #33824**）
- [code-execution-sandbox](concepts/code-execution-sandbox.md): execute_code 沙箱，7 工具限制+UDS/File RPC 两种通信模式
- [voice-mode-architecture](concepts/voice-mode-architecture.md): Push-to-talk 语音交互，STT（5 Provider）+ TTS（10 内置 Provider，含 Piper 本地神经 TTS）
- [context-references](concepts/context-references.md): @file/@folder/@diff/@url/@git 引用系统，安全沙箱+注入量限制
- [fuzzy-matching-engine](concepts/fuzzy-matching-engine.md): 8 策略链模糊匹配，从精确到相似度匹配
- [large-tool-result-handling](concepts/large-tool-result-handling.md): 三层溢出防护（工具内截断/单结果持久化/轮次聚合预算）
- [lsp-integration](concepts/lsp-integration.md): **NEW v0.14** LSP 语义诊断集成，agent/lsp/ 11 modules + file-mutation footer 三层后写校验
- [i18n-and-locales](concepts/i18n-and-locales.md): **NEW v0.13** i18n 薄切片本地化（仅 hermes 自身静态消息，不动 agent 输出）

### 性能与优化

- [parallel-tool-execution](concepts/parallel-tool-execution.md): 智能并发安全检测
- [prompt-caching-optimization](concepts/prompt-caching-optimization.md): 冻结快照保护 prefix cache，75% 成本节省
- [smart-model-routing](concepts/smart-model-routing.md): 智能模型路由

### 安全与可靠性

- [security-defense-system](concepts/security-defense-system.md): 多层防御 + Redaction 默认 ON + Discord guild-scoped + post-write delta lint（v0.13.0 安全 wave）+ **Wave 4 Dashboard OAuth + security-guidance 插件**（2026-05-27）
- [dashboard-auth-oauth-gate](concepts/dashboard-auth-oauth-gate.md): **NEW 2026-05-27** Dashboard OAuth 鉴权闸门（可插拔 ABC + Nous Portal Provider + WS 单次性 ticket + Phase 0-7）
- [interrupt-and-fault-tolerance](concepts/interrupt-and-fault-tolerance.md): 中断传播、Fallback 模型链
- [credential-pool-and-isolation](concepts/credential-pool-and-isolation.md): 多密钥自动轮换、Profile 隔离
- [checkpoints-architecture](concepts/checkpoints-architecture.md): **NEW v0.13.0** Checkpoint v2 共享 shadow git store
- [tool-loop-guardrails](concepts/tool-loop-guardrails.md): **NEW v0.12.0** 工具调用循环护栏，exact failure / same-tool failure / idempotent no-progress 三维检测

### 多 Agent

- [multi-agent-architecture](concepts/multi-agent-architecture.md): 5 种运行时机制（delegate_task/MoA/Background Review/send_message/**Kanban**）
- [kanban-multi-agent-board](concepts/kanban-multi-agent-board.md): 可持久化多 Agent 协作板（SQLite + WAL，心跳/熔断/幻觉拦截，跨 session/profile）
- [goal-and-ralph-loop](concepts/goal-and-ralph-loop.md): `/goal` + `/subgoal` 持续推进系统（fail-open judge，回合预算，保 prompt cache）
- [configuration-and-profiles](concepts/configuration-and-profiles.md): 多 Profile 架构，完全隔离的 agent 实例（第二种多 Agent 方案）

### 平台与扩展

- [cli-architecture](concepts/cli-architecture.md): CLI 架构、斜杠命令、hermes dump/proxy/kanban/curator/migrate
- [terminal-backends](concepts/terminal-backends.md): 7 种终端后端（含 Vercel Sandbox）、统一 spawn-per-call 执行模型
- [messaging-gateway-architecture](concepts/messaging-gateway-architecture.md): 22 平台统一网关（含 Teams/LINE/SimpleX Chat/Google Chat 等插件平台），PlatformRegistry、Session auto-resume、统一 allowlist
- [hermes-proxy](concepts/hermes-proxy.md): OAuth → OpenAI-compatible 本地代理，让 Aider/Cline/Codex 复用 Nous/SuperGrok 订阅
- [gateway-session-management](concepts/gateway-session-management.md): 网关会话管理，多平台会话隔离+PII 脱敏+重置策略
- [hook-system-architecture](concepts/hook-system-architecture.md): 双 Hook 系统（Gateway Hooks + Plugin System），register_command/dispatch_tool，Dashboard 插件
- [mcp-and-plugins](concepts/mcp-and-plugins.md): MCP 集成、插件钩子系统、OAuth 支持
- [skin-engine](concepts/skin-engine.md): YAML 驱动的皮肤/主题系统
- [worktree-isolation](concepts/worktree-isolation.md): Git Worktree 并行隔离模式
- [cron-scheduling](concepts/cron-scheduling.md): 内置调度器、自然语言调度、多平台投递、`no_agent` watchdog 模式
- [trajectory-and-data-generation](concepts/trajectory-and-data-generation.md): 轨迹保存、批量运行器、RL 训练环境

### 更新日志（32 个，最新优先 — 完整列表见 [index.md](index.md)）

- [2026-05-29-update](changelog/2026-05-29-update.md): **275 commits 跨日同步**（hermes-agent `963d22c → 689ef5e2`）— **v0.15.0 + v0.15.1 双版本发布**、**claude-opus-4-8 + opus-4-8-fast 模型**（#34003）、**工具渐进式披露扩展到 MCP/插件工具**（`agent/tool_search.py`，`369075dc9`）、**MCP mTLS 客户端证书**（`tools/mcp_tool.py:573-625 _resolve_client_cert`，#33721）、**web_crawl 工具与 provider crawl 管线全面移除**（23 文件，#33824）、**`hermes sessions optimize` + FTS5 段合并**（`hermes_state.py:3267 optimize_fts`/`:3306 vacuum`）、**Kanban `POST /runs/{run_id}/terminate`**（`plugins/kanban/dashboard/plugin_api.py:1317`）+ 一系列可靠性硬化（per-profile 并发上限、SQLite 抗撕裂写、worker SIGTERM、close-FD-after-connect、corrupt-DB 内容寻址备份名）、**`sync_turn` 新增 `messages` 上下文参数**（`agent/memory_provider.py:115-133`，`5a95fb2e1`）、**pluggable Context Engine ABC**（`agent/context_engine.py:32 class ContextEngine(ABC)`，`9b5dae17a`）、**Skills 目录大扩张**（skills.sh 858→19,932 经 sitemap、ClawHub 200→20k+、NVIDIA tap），**新增可选 skill `antigravity-cli`/`grok`**、**Krea 2 进入 FAL 目录**（与既有 `plugins/image_gen/krea` 直连后端并存，#33506）、**FAL 视频经 Nous 网关**、**Docker s6 wave**（persist-across-processes #20561 + 孤儿回收 + `PUID`/`PGID` alias）、**安全 wave**（Nous 仅 JWT、子进程 AWS 凭据剥离、code-exec 审批旁路回归簇、`API_SERVER_KEY` 必填、Docker stop/kill 进 dangerous patterns）、**MEDIA 提取扩展名统一**（#34517）
- [2026-05-27-update](changelog/2026-05-27-update.md): **645 commits 跨日同步**（hermes-agent `556bf7c → 963d22c`，默认远端分支 `master → main`）— **Dashboard OAuth 鉴权闸门 Phase 0-7 整体落地**（`hermes_cli/dashboard_auth/` 10 文件 1868 行 + `DashboardAuthProvider` ABC + Nous Portal Provider 582 行 + WS 单次性 30s ticket + `register_dashboard_auth_provider` 第 8 个 PluginContext hook）、**Honcho AI-native 跨会话用户建模 MemoryProvider**（`plugins/memory/honcho/` 5 文件 5158 行 + dialectic Q&A + peer cards + identity-mapping `single`/`multi`/`hybrid` wizard + `pinUserPeer ↔ pinPeerName` 别名链 + 15 个 honcho 子修复）、**Krea 图像生成 Provider 插件**（Krea 2 Medium/Large，548 行）、**security-guidance 插件 25 条 dangerous-pattern 警告**（Apache-2.0 Anthropic fork，#33131）、**TUI Session Orchestrator**（in-TUI 多 session 同屏 635 行 + `tui_gateway/server.py` +221）、**API Server 三连**（Session CRUD + `GET /v1/skills` + `GET /v1/toolsets`，#33016）、**Windows 原生支持收官**（UTF-8 stdio shim / psutil PID / Scheduled Task / install.ps1 加固 / 79+63 skill platforms frontmatter / Playwright autoinstall / `_pid_exists` helper）、**Docker wave**（Node 22 LTS multi-stage + chown 链 + s6 env 转译 + `agent-browser` boot discover）、**Codex Responses-API 14 修复**（drop `responses.stream()` helper + null/large/encrypted_content recovery + 凭据池 fallback isolation）、**xAI 模型退役迁移工具链**（`hermes migrate xai [--apply]` + ruamel round-trip + doctor 提示 + chat 启动 warn）、**xAI Web Search provider 插件**（第 8 个 web provider）、**Telegram 19 修复**（in-place status edit + DM topic thread 修复 + heartbeat 原地编辑 + 静默 chatter + 2GB skip-STT 音频 + ignore_root_dm + pin user message）、**性能 wave**（agent-loop -47% via `load_config_readonly` + terminal poll -195ms + cold start -19s + termux fast-path）、**Bitwarden EU + 自托管 server URL**（#31378）、**BrowseShSource 第 8 个 skill catalog**（Browserbase 200+ 站点专用浏览器自动化）、**`hermes update --branch` + post-pull syntax-validate auto-rollback**（#28669/#26172）、**Nix #messaging / #full 包变体**（#33108）、**Honcho identity-mapping 三 shape wizard** + **gateway/run.py 暴露 honcho 配置到 doctor 视图**
- [2026-05-26-update](changelog/2026-05-26-update.md): **37 commits 跨日同步**（hermes-agent `b62af47 → 556bf7c`）— **Promptware 防御**（共享威胁模式库 252 行 + Memory load-time scan + `<untrusted_tool_result>` 工具结果分隔符，#32269）、**Nous-approved MCP 目录 + 交互式选择器**（`hermes mcp catalog/install/picker`，`optional-mcps/{n8n,linear}`，#30870）、**Skills Hub 健康检查**（`EXPECTED_FLOORS` + `MIN_TOTAL=1500` + 新鲜度徽章 + 每 4h watchdog cron，#32345）、**3 个新可选 skill**（`web-pentest` / `openhands` / `code-wiki`）、**Patch 工具三连**（缩进保留 / CRLF 保留 / per-file 失败升级，#507/#32273）、**Cron 扫描器二级分裂**（strict vs loose，#32339）、**Skill install 拒绝符号链接**、**Dashboard 插件资源 suffix-allowlist + 子进程影响型 env denylist**（#32277）、**Markdown 链接 scheme 收紧 + WeCom callback defusedxml**（harden）、**AGENTS.md 限定工作目录内载入**、**Telegram DM topic 投递 6 连**、**Anthropic API-key 路径跳过 OAuth autodiscovery**、**外部 secrets 每进程仅应用一次**（#32271）、**Gateway `/model --global` scalar→dict coerce**（#32272）、**Agent outer-loop ERROR + traceback**（#32264）、**qwen3.6-plus → qwen3.7-max** / 移除 grok-4-1-fast、**TTS 双 `[pause]` 修复**（#29417）、**CLI fallback paste collapse**（#32447）、**Cron schedule 在 create 模式必填**（#32427）
- [2026-05-25-update](changelog/2026-05-25-update.md): **175 commits 跨日同步**（hermes-agent `186bf25 → b62af47`）— **Docker `s6-overlay` 取代 `tini` 作 PID 1（BREAKING）+ 容器化运行时监管子系统**（~20 commits：`ServiceManager` Protocol + `S6ServiceManager` + `container_boot.py` + per-profile gateway 监管 + 多架构 SHA256 校验）、**安全 wave 3**（~25 commits：6 处 symlink 拒绝矩阵 + `/proc/*/environ|cmdline|maps` deny + 项目本地 `.env` 读 deny + `.env` 全 0o600 + `_YOLO_MODE_FROZEN` 模块级冻结 + GHSA-rhgp-j443-p4rf config.yaml 路径合规 + Skills Guard multi-word Unicode-spoofing + 7 处凭据持久化 TOCTOU/path 加固）、**`hermes security audit`**（OSV.dev `querybatch`，覆盖 venv/plugin/MCP 三面）、**CLI 冷启动 -63%**（Bitwarden disk L2 cache, 666ms→295ms）、**Plugin hook**：`register_tts_provider()` + `register_transcription_provider()` + `stt.providers.<name>` command 注册表、**`openai-api` 新 Provider**（直连 `api.openai.com`，`/v1/models` 直拉，gpt-5.5-pro）、**CredentialPool 周配额轮换正确性**（peek pool + `explicit_api_key`）、**Gateway 在飞子 Agent 抗 busy-mode 中断**（`_agent_has_active_subagents` 降级 queue 语义）、**Mattermost 迁移为 bundled plugin**（plugin 化第二个 built-in 平台）、**MCP OAuth 无头 paste-back 三连**、**Codex Responses-API TTFB watchdog + 上下文 token 估算修复**、**mid-tool-call partial-stream-stub 走 `finish_reason=length` 续传**、**Auxiliary 统一 main-model fallback**（PR #31845）、**Nous OAuth 401 可执行指导**、**`/resume` 编号选择 + recap 调优键**、**`/q` 改属 `/queue`** 等
- [2026-05-24-update](changelog/2026-05-24-update.md): **84 commits daily delta** — 安全 wave 2（17 commits：Webhook fail-closed + Svix 签名 + Dashboard WebSocket loopback + Feishu/QQBot/Discord/DingTalk/MSGraph 审批授权 + `response_store.db` 0o600）、**ntfy 第 23 平台**（plugin 化）、Plugin `register_auxiliary_task()` 新 hook API、**跨 Profile 文件写入软护栏**（`classify_cross_profile_target`）、**Streaming 完成可见性三连**（guardrail halt 推到 stream / `response_transformed` 编辑 in-place / partial-stream `finish_reason=length`）、Kanban `promote` 子命令（`--ids` 批量）、Skills AST 深度诊断（`audit --deep`）、Bitwarden EU + 自托管、`config.yaml model.provider` 单一 source of truth
- [2026-05-23-update](changelog/2026-05-23-update.md): **49 commits daily delta** — `hermes setup --portal` + `hermes portal {status,open,tools}` 一键起步、Kanban DB 抗污染（`KanbanDbCorruptError` + CodeQL 硬化 + scratch tip）、Memory.md/USER.md 外部漂移防护、审批"沉默 ≠ 同意"契约（#24912）、TLS FD 回收三层防御（#29507）、Plugin RCE 第二段（GHSA-5qr3-c538-wm9j）、Webhook INSECURE_NO_AUTH 动态路由保护、Telegram 状态消息 in-place edit、WhatsApp JID/LID alias、QQBot intent/op7-9/SILK 修复簇、OpenCode Go reasoning controls
- [2026-05-22-update](changelog/2026-05-22-update.md): **v0.14.0 集大成** — Kanban、`/goal`+`/subgoal`、Hermes Proxy、PyPI + Windows、Provider/Browser/Web/Video/Image/TTS 全面插件化、Curator 1781 行、LSP semantic diagnostics、Codex app-server、跨 session 1h Claude cache、Cold-start -19s、Teams/LINE/SimpleX/Google Chat、12 P0 + 50 P1 关闭
- [2026-05-20-update](changelog/2026-05-20-update.md): v0.14.0（~2,480 commits across v0.12.0/v0.13.0/v0.14.0）
- [2026-05-16-update](changelog/2026-05-16-update.md): v2026.5.16（2,890 commits since v2026.4.23）
- [2026-05-07-v0.13.0](changelog/2026-05-07-v0.13.0.md): **v0.13.0 release** — Provider plugin 化、Checkpoint v2、i18n、Curator 自治
- [2026-04-30-v0.12.0](changelog/2026-04-30-v0.12.0.md): **v0.12.0 release (The Curator Release)** — Persistent Goals、Tool-call Loop Guardrails、Kanban、Teams、4 新 Provider
- [2026-04-29-update](changelog/2026-04-29-update.md): 182 commits (v2026.4.23)，平台适配器插件化（PlatformRegistry + IRC）、Curator 后台技能维护、MiniMax OAuth、Vercel Sandbox、腾讯元宝
- [2026-04-18-update](changelog/2026-04-18-update.md): 410 commits post-v0.10.0，Transport ABC 重构、Shell Hooks、Delegate Orchestrator、Step Plan/AI Gateway/xAI STT/KittenTTS、WeCom QR
- [2026-04-17-update](changelog/2026-04-17-update.md): 641 commits (v0.10.0)，压缩 v3、Bedrock/Gemini/Ollama Provider、Tool Gateway、插件命名空间技能、钉钉 QR 认证、Dashboard 插件
- [2026-04-10-update](changelog/2026-04-10-update.md): 293 commits，Context Engine 插件化、watch_patterns、WeChat、xAI、Discord/Slack 增强
- [2026-04-09-update](changelog/2026-04-09-update.md): 59 commits，结构化错误分类、统一执行层、三层溢出防护、BlueBubbles 等

---

## 统计信息

- **概念页面**: 46 个
- **实体页面**: 2 个
- **更新日志**: 31 个
- **源码覆盖**: 关键模块逐行验证
- **跟踪版本**: v0.14.0（hermes-agent/main HEAD `963d22c`，默认远端分支由 `master` 改为 `main`）
- **最后更新**: 2026-05-27


## 使用方式

- **GitHub 在线浏览**: 直接点击上方目录链接
- **Obsidian 本地知识库**: 
  ```bash
  git clone https://github.com/cclank/Hermes-Wiki.git ~/Hermes-Wiki
  ```
- **配合 Hermes Agent**: 在 config.yaml 中设置 `skills.config.wiki.path: ~/Hermes-Wiki`


---

*本文档基于 Hermes Agent 源码分析生成。*
