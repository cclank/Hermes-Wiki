# Wiki Log

> 所有 wiki 操作的按时间顺序记录。只追加，不修改。
> 格式：`## [YYYY-MM-DD] action | subject`
> Actions: ingest, update, query, lint, create, archive, delete
> 当此文件超过 500 条时，轮换：重命名为 log-YYYY.md，重新开始。

## [2026-06-03] sync | hermes-agent c47b9d126 → 6fff744158（131 commits，Observability hooks/NeMo-Relay 插件 + Desktop xAI Grok OAuth + 状态栏 inline model picker + hermes portal 一站化 + 大规模 Desktop 卫生 wave）
- 同步范围：hermes-agent/main `c47b9d126`（2026-06-02 16:51 -0400）→ `6fff744158`（2026-06-03 14:09 -0700），**131 个 commit**，约 21 小时窗口
- 验证基线：`/tmp/hermes-agent` blobless clone + `git checkout 6fff744158a0dc46d19ff817c1f82b87b52790d9 -- .` 全 checkout @ HEAD，所有 commit hash / file:line / 路径经 `grep -n` / `git show --stat` / `Read` 实证
- 版本：仍 v0.15.1（`pyproject.toml:7 version = "0.15.1"` 不变，**无新发布 tag**）；持续高节奏维护窗口
- commit 类型分布：69 fix / 12 feat / 8 test / 6 chore / 5 docs / 1 refactor / 1 polish / 1 perf / 1 ci（+ 25 个 Merge PR 节点；69 fix 反映出昨晚 Desktop App / Portal / Installer 三大特性的密集回归修复浪潮）
- 新增文件：`changelog/2026-06-03-update.md`（约 850 行，29 章节）
- 更新文件：
  - `README.md` — 版本徽章 `v0.15.1 (c47b9d12) → v0.15.1 (6fff7441)`、Changelogs 35 → 36、统计信息块跟踪 HEAD 与最后更新日期同步 2026-06-03、新增 changelog 列表条目（cluster 综合摘要）
  - `index.md` — 顶部 tracking 字段（HEAD `6fff744158` / Total pages 35 → 36 changelogs / Last updated 2026-06-03）、changelog 列表新增 2026-06-03 条目
  - `log.md` — 本条记录
- 核心结论（均经源码验证，每个 `file:line` 引用现行 source 实际行号 @ `6fff744158`）：
  - **Observability observer-grade telemetry hooks + NeMo-Relay 插件** (#29722 salvage, `0d9b7132f`)：`hermes_cli/plugins.py:128-200 VALID_HOOKS` 新增 `api_request_error`/`subagent_start` 共 21 hook + `:1574 def has_hook`(self) + `:1658 def has_hook` 顶层；**新建** `plugins/observability/nemo_relay/__init__.py 568 行` + `plugin.yaml 20 行` + `README.md 368 行`，与既有 `plugins/observability/langfuse` 并列；总览 `docs/observability/README.md 316 行`；hot path 零开销（`has_hook()/presence checks` 闸所有 payload dict 构建 / request payload 在 middleware 不重写时按引用返回）；`827f25142 perf` 把 per-tool emit 也闸（`_emit_post_tool_call_hook` 短路 `has_hook("post_tool_call")` + status/error 懒派生）；NeMo-Relay 未装时 fail open
  - **`hermes portal` 一站化** (3 commits)：`hermes_cli/portal_cli.py:170 _cmd_login` + `:191 portal_command`（默认/login → `_cmd_login`；info/status → `_cmd_status`；open/tools 不变）+ `:212 add_parser` 注册；`hermes_cli/setup.py:2723-2790 _run_portal_one_shot` 通过 `hermes_cli.main._model_flow_nous` 统一路由——未登录走 device-code OAuth 内部选模型，已登录弹 27-model curated picker，再 Tool Gateway opt-in + `provider=nous`，最后从磁盘重 sync 防 save_config 覆盖；`hermes_cli/main.py:11875` portal 在 subparsers list + `:13166-13167 _add_portal_parser`
  - **Desktop xAI Grok 升级一等 OAuth provider** (`dd5e97bd7`, 5 文件 +434/-6)：`hermes_cli/web_server.py:3160-3163` catalog 条目 `flow=loopback` + `:3750 _start_xai_loopback_flow()` +222 行 + `:4246 loop.run_in_executor(None, _start_xai_loopback_flow)`；6 后续修：`63e824831` reorder + `3be9fb731`/`d963ad56c` 两轮 Copilot review + `a13db76ea` cancel 信号 DELETE 设 `callback_result` cancelled 防 worker spin + `33807e2b1` `source_label` 用 auth-store 路径
  - **Desktop 状态栏 inline model picker** (`ea4fe1563`, 11 文件 +788/-)：`apps/desktop/src/app/shell/model-menu-panel.tsx 289 行` 主下拉 + `apps/desktop/src/app/shell/model-edit-submenu.tsx 248 行` reasoning+fast hover-Edit + `apps/desktop/src/components/model-visibility-dialog.tsx 148 行` localStorage edit-models + `apps/desktop/src/components/ui/dropdown-menu.tsx +118 行` 共享 primitives（`DropdownMenuSearch` + portaled 协同碰撞 submenu）+ `apps/desktop/src/lib/model-status-label.ts 103 行` + 31 测试；4 后续修：`b6945ce77` Enter/Space 键盘激活 picker rows + `d704df2d6` optimistic switch 失败回滚 + `115671ae6` Copilot review + 2 chore uptick
  - **Desktop session/scroll/sticky/clamp wave (~12 commits)**：`apps/desktop/src/components/assistant-ui/thread-virtualizer.tsx:230 lastClientHeightRef` + `:319 clientHeightChanged > 1` 修 viewport resize 误 disarm sticky-bottom；`apps/desktop/src/app/chat/composer/index.tsx:581 if (event.nativeEvent.isComposing) return` 修 IME composing Enter split messages；4 sticky human bubble commit 加 `--sticky-human-top` 0.75rem token + clamp ~2 行 + 0.75s transition；自定义 zoom 0.1 step 替 0.2；clipboard image dedupe items/files；`55a76ec66 + e0a999aa8` in-flight new chats 保留+labeling；`93228d529 + 1b89715e1` persist pins + reconnect after sleep + branch search precise
  - **Desktop slash/`@` + Stop + 后台 bleed**：`188e52db9`/`49f1b9e4b` `triggerKeyConsumedRef` 替 timing-fragile `trigger !== null` guard；`a23728dfc` Stop 按钮真 interrupt `userInterruptedRef` 拢一次 drain + `shouldAutoDrainOnSettle()` 抽出；`28f1590b7` 后台 session messages 改 keyed-by-sessionId map staging 防覆盖前景写
  - **Desktop macOS 自更新 clean rebuild**：`a1cda2410 update.rs/main.cjs/bootstrap.rs/powershell.rs/failure.tsx` 综合 rebuild PATH + ditto install stage + `AtomicBool` race guard；`d3b1e4300 swap_in_new_bundle()` 严格不变式；`810e5864d` LogStream 结构化 metadata；`1971b1052` emit_log signature；`746618217 apps/desktop/electron/main.cjs +145` 已存在 macOS 安装收编；`1daecfa4b` Dock 钉 `pathToFileURL` type 15；`21e172b94 entitlements.mac.inherit.plist +2` 麦克风 entitlement 继承；`46e513ef5` Linux chrome-sandbox 4755
  - **Desktop 远端显示禁 GPU**：`6a2909fe5 apps/desktop/electron/bootstrap-platform.cjs +51 detectRemoteDisplay` SSH X11/VNC/RDP 软件渲染 + `HERMES_DESKTOP_DISABLE_GPU` 双向 override；`d0ea4caf7 -5/-2` WSLg vGPU 本地渲染例外
  - **Dashboard System 检查后再更新** (`c5d199ead`)：`hermes_cli/web_server.py:1168 GET /api/hermes/update/check` 6h cache `?force=1` 失效 + `:1140 POST /api/hermes/update` + System 页 update-status badge + Check-for-updates 按钮 + Update-now ConfirmDialog 展示 commit 数 + 5 端点测试
  - **Dashboard Profiles 富化 + Channels env 去重** (`7fb8a6b5c`)：active-profile 切换 / 角色描述 auxiliary LLM 自动生成 / per-profile 模型选择 / gateway-running + distribution badges；messaging 凭据 `channel_managed` 从 Keys/Env 页隐藏；"messaging" → "Gateway" i18n（`t.common.gateway` / `gatewayHint`）
  - **Dashboard auth WS origin + PTY internal credential**：`dd28f2ac9` `_ws_host_origin_is_allowed` 把 OAuth-gated 后的非 web origin 信任广义化（packaged Hermes Desktop `file://` 不再 403）+ `fd1ec8033` `_build_gateway_ws_url()` 补 gated 分支让 PTY child 用进程内 mint-once internal credential（之前嵌入 chat 在每个 gated 部署都 4401）+ `e114b31ed` 7 分支单测
  - **Dashboard PTY 维度 WSL2 钳制** (`966630563`)：WSL2 winsize 探测坏掉报 `cols=131072 rows=1`，`struct.pack` 抛 `struct.error` 但之前只 catch `OSError`；钳到 `[1,2000]×[1,1000]`，非有限/非整数 fallback 到最小值
  - **Gateway ResponseStore + 未挂 adapter 泄 fd 修** (`4b06c98fe`)：reconnect 3 失败路径都 drop 新建 adapter 不挂 `self.adapters`，2 fd（db + WAL）漏每次，~12h 撑爆 2560 fd ulimit #37011；3 路径都显式 dispose + `disconnect()` 关 `ResponseStore`；`01eaba706` Copilot review 接
  - **Gateway `/background` 媒体按类型路由** (`082025abc`)：TTS→voice / video→`send_video` / image→`send_image_file` 替统一 `send_document`；`gateway/run.py:12265 import` + `:12322`/`:12610-12617` 三处分支；复用 `gateway/platforms/base.py:102 should_send_media_as_audio` + 保留 `:1313 cache_media_bytes`
  - **Gateway schtasks locale 解码** (`973decc05`)：`hermes_cli/gateway_windows.py +21` 用 locale preferred encoding + `errors="replace"`，Windows 中文 console 不再 `UnicodeDecodeError`
  - **Web-server event channel state 从模块全局搬 app.state** (`cbc82511e`)：`_lifespan()` 在 FastAPI 启动时在正在运行的 event loop 创建 dict + lock；`_get_event_state(app)` 在 app.state lazy init；所有 call site (`_broadcast_event` / `/api/pub` / `/api/events`) 改读 app.state；修跨 TestClient/uvicorn reload "attached to a different loop"
  - **Doctor `HERMES_MAX_ITERATIONS` env 影子检测** (`6ee046a72`, 关 #17534)：`hermes_cli/doctor.py:894-922 cfg_max_turns ... env_ghost` 直接 `load_env()` 读 `.env` 文件本身（非 `get_env_value/os.environ`，因 bridge 可能已覆盖 `os.environ`）；`hermes config show` 同时显示 drift
  - **Kanban 速率限制非永久阻塞** (`4c544b633`)：`hermes_cli/kanban_db.py:158-161` `EX_TEMPFAIL=75` 哨兵；`:189-196` `HERMES_KANBAN_RATE_LIMIT_COOLDOWN_SECONDS` 默认 5min；`:4760` 注释；`:4821 rate_limited` field；`:4873-4884` reap 分类；`:5429` worker drain；rate_limited 释放回 ready **不增** `consecutive_failures`（断路器不被 trip）；120s `Retry-After` cap 不变
  - **Matrix `!` bang 命令别名 + 死代码修** (`0022e94d7`/`a1264e996`)：`gateway/platforms/matrix.py +55`；underscore→hyphen 容忍 emit 可解析 token（`!set_home → /set-home`）；skill command keys slash-prefixed 比较（`!arxiv → /arxiv`）；reply-fallback 剥离后**再次**跑 bang 规范化；162 测试
  - **MCP banner `disabled` 不再 `failed`** (`1d90b2398`)：`hermes_cli/banner.py +5` + `tools/mcp_tool.py +6`，`enabled: false` 改 dim "— disabled"
  - **TUI 持久化 trail OOM 修** (`e76d8bf5a`)：`ui-tui/src/lib/text.ts:2-5 LIVE_RENDER_MAX_CHARS, LIVE_RENDER_MAX_LINES, VERBOSE_TRAIL_MAX_CHARS=800` + `:223-226` 注释 `silently OOM-kill the TUI. See VERBOSE_TRAIL_MAX_CHARS (#34095)`；持久化 trail 字符串掉 17×（12.2MB → 0.7MB @ 800 msgs）；`memoryMonitor.ts` 阈值从真实 V8 heap ceiling 派生（~88%/70%）替硬编码 2.5GB；`e02a6038a` TUI `/save` 写 `get_hermes_home()/sessions/saved/` 含 system prompt；`dfba3f3e5` 右键复制清选区
  - **Aux Nous-routed self-heal** (`ab2472e69`)：`agent/auxiliary_client.py:2495 _is_model_not_found_error` 404/400 "not found / does not exist / not a valid model" 判定（排除 billing 关键字防 overlap `_is_payment_error`）+ `:1624 _refresh_nous_recommended_model` 强制刷新 + `:5121-5122` / `:5583-5584` 两 call site；长寿命进程缓存 Portal 推荐 model 被 catalog 掉时不再 404 至重启
  - **CLI `display.interface` 可配置默认界面** (`d6b0c23f8`)：`hermes_cli/main.py:108` 无依赖早期 cached YAML 读 + `:145 _wants_tui_early` + `:171` + `:1823 _resolve_use_tui` + `:1842 iface = load_config()...["display"]...["interface"]` + `:12090-12092`；`--cli` 与 `--tui` 都通过 `_inherited_flag` 注册 self-relaunch 自动携带
  - **Debug 含 `desktop.log`** (`1b302a047`)：`hermes_cli/logs.py +2` 注册 `desktop → desktop.log`（启用 `hermes logs desktop`）+ `debug.py +32` summary 报告 + share 上传 + gateway `/debug` 经 `collect_debug_report()` 继承 desktop tail
  - **Packaging `locales/` 进 wheel/sdist/Nix** (`c349eca82`, 关 #23943/#27632/#35374)：`[tool.setuptools.data-files] locales = ["locales/*.yaml"]`（wheel）+ `MANIFEST.in graft locales`（sdist）+ `agent/i18n.py:88 _locales_dir HERMES_BUNDLED_LOCALES` env override → source → sysconfig data scheme + Nix wrapper 双保险；封闭安装下不再渲染原始 i18n key（如 `gateway.reset.header_default`）
  - **Refactor 单一 managed-uv 路径** (`4df280d51`)：**新建** `hermes_cli/managed_uv.py 228 行`：`:35 managed_uv_path` + `:48 resolve_uv` + `:59 ensure_uv` 返回 `(path, freshly_bootstrapped)` tuple + `:101 rebuild_venv` + `:135 update_managed_uv`；替换多路径 UV 解析链；删 install.sh **61 行** `ensure_fts5/_python_has_fts5/_reinstall_python_with_fts5/_warn_no_fts5`（managed uv 总装带 FTS5 的当前 Python）；`4a626ed18 _patch_managed_uv autouse fixture` 测试隔离
  - **Workspace lockfile 整合 + Node ≥20.19/22.12**：`a51a7b9b9` per-package package-lock.json → root 单一 + Nix `lib.nix` 共享 `npmDepsHash` + Python `_workspace_root()` helper + Desktop 内容 hash build stamp `_compute_desktop_content_hash` 替 `--force-build`/mtime + Dockerfile 单一 npm install + CI nix-lockfile-fix 引用根 lockfile；`ba57ebec3` npmDepsHash refresh；`1dca7c620` Node 版本预检 + 帮助信息；`214b7e070 install.ps1` 处理 Windows `core.autocrlf=true` 引起的脏 worktree；`205ed71ba` npm audit 6 修
  - **Docker TUI launcher 用 prebuilt bundle** (`9272e4019`)：`hermes_cli/main.py:1479-1506` `HERMES_TUI_DIR` env 修嵌入 dashboard Chat tab 在托管镜像 502 - PTY child 跑运行时 `npm install` 失败因 root lockfile 含 `apps/*` workspace 但镜像只装 root/web/ui-tui；Dockerfile +17 + 79 测试；`d9f7e7ac8 docker/stage2-hook.sh:291,307 HERMES_GATEWAY_BOOTSTRAP_STATE=running` 首次启动 seed `gateway_state.json`
  - **Cron skill bundles 展开** (`ae5b2de2f`)：`cron/scheduler.py +26 from agent.skill_bundles import build_bundle_invocation_message, resolve_bundle_command_key`（`:1118`）+ 64 测试覆盖 + 注入防御
  - **Setup browser/TTS picker 默认指向免费本地后端** (`b28dd3417`)：reorder provider 列表让免费本地后端是 index 0（Local Browser / Microsoft Edge TTS），不再 Enter 即走 inline Nous Portal device-code 付费
  - **Submodule + RELEASE 清理**：`43fd63b4b 7 文件 -35` rip out unused submodule + `047e7cf36` 残留 CONTRIBUTING.md + `64202200a` 15 RELEASE_v*.md（v0.2.0 - v0.15.1）+ `.gitignore` 防 `git add -A`
  - **杂修**：`192020992 + 5fca754ee HERMES_DESKTOP_CHILD_PID` 排除 desktop-managed backend 在 stale-dashboard kill 端到端关 #37532；`6ed9a2de8` dashboard 远端 bind 允许 desktop WS origin；`a429a2a0b ci(nix)` 折叠 package+devShell 进 flake check；`bb1c8b6f1 test(honcho)` prewarm 去 flake；AUTHOR_MAP 4 entry；5 docs 远端 backend 自含 + `--tui` flag + session token 钉法

## [2026-06-02] sync | hermes-agent b9646276f → c47b9d126（104 commits，Dashboard Channels + Admin Panel v2 + Gateway Stream-Event Protocol + runtime_cwd + Fuzzy Picker 全面强化）
- 同步范围：hermes-agent/main `b9646276f`（2026-06-01 09:57 -0700）→ `c47b9d126`（2026-06-02 16:51 -0400），**104 个 commit**，约 28 小时窗口
- 验证基线：`/tmp/hermes-agent` blobless clone + `git checkout origin/main -- .` 全 checkout @ `c47b9d126f2f820f41059813a2c5b16ea4742bf8`，所有 commit hash / file:line / 路径经 `grep -n` / `git show --stat` / `Read` 实证
- 版本：仍 v0.15.1（`pyproject.toml:7 version = "0.15.1"` 不变，**无新发布 tag**）；持续维护 + 多个延迟 PR 接力
- commit 类型分布：43 fix / 23 feat / 7 test / 6 refactor / 5 docs / 5 chore / 1 ci（+ ~14 个 Merge PR 节点，~22% feat 反映高 throughput）
- 新增文件：`changelog/2026-06-02-update.md`（864 行，29 章节）
- 更新文件：
  - `README.md` — 版本徽章 `v0.15.1 (b9646276) → v0.15.1 (c47b9d12)`、Changelogs 34 → 35、统计信息块跟踪 HEAD 与最后更新日期同步 2026-06-02、新增 changelog 列表条目（17 cluster 综合摘要）
  - `index.md` — 顶部 tracking 字段（HEAD `c47b9d126` / Total pages 34 → 35 changelogs / Last updated 2026-06-02）、changelog 列表新增 2026-06-02 条目
  - `log.md` — 本条记录
- 核心结论（均经源码验证，每个 `file:line` 引用现行 source 实际行号 @ `c47b9d126`，17 个 cluster 全列）：
  - **Dashboard Channels 页面** (#37211, `3c1d066a`)：`web/src/pages/ChannelsPage.tsx +429`（`:34-49 STATE_BADGE` 5 态徽章 / `:51 export default function ChannelsPage()` / `:72 load()` / `:83 openConfig()` / `:126 handleToggle()` / `:146 handleTest()`）+ `web/src/App.tsx:81,135,176`（import + route + Radio icon tab）+ `web/src/lib/api.ts:476-490`（3 client 方法）+ `:871-913`（4 类型：`MessagingPlatformEnvVar` / `MessagingPlatform` / `MessagingPlatformUpdate` / `MessagingPlatformTestResult`）
  - **Dashboard 完整管理面板 v2** (#36736, `bd8e2ec1`)：10 文件 +2597 / -210；`hermes_cli/web_server.py +665` 新增 6 类端点 — `:757 get_system_stats()` GET /api/system/stats / `:4578 class MCPEnabledToggle` / `:4583 set_mcp_server_enabled()` PUT /api/mcp/servers/{name}/enabled / `:4602 list_mcp_catalog()` GET /api/mcp/catalog / `:4903 set_webhook_enabled()` PUT /api/webhooks/{name}/enabled / `:5242 list_hooks()` GET /api/ops/hooks / `:5496 search_skills_hub(q, source, limit)` GET /api/skills/hub/search；6 大前端页扩展 `McpPage`/`SystemPage`/`SessionsPage`/`SkillsPage`/`WebhooksPage`/`CronPage`；`tests/hermes_cli/test_dashboard_admin_endpoints.py +191`
  - **Dashboard `nous-blue` 主题 + bulk sessions + schedule picker** (#37383, `6d14a24b`)：41 文件 +3299 / -213；LENS_5I overlay 系统移植到 `DashboardTheme` + foreground inversion 提到 `z-index:200` 修长期 hover/loading 视觉伪影；`localStorage`/API 的旧 `"lens-5i"` 在首次读取改写 `"nous-blue"` 无感升级；新增 `--series-input-token` / `--series-output-token` CSS 变量；Analytics+Models 图表消费；14 种 i18n locale 同步（fr/ga/hu/it/ja/ko/pt/ru/tr/uk/zh/zh-hant + types.ts）；`web/src/lib/schedule.ts +382` 新建；`web/src/pages/SessionsPage.tsx +407` bulk；CronPage / AnalyticsPage / ModelsPage / SystemPage / themes/{context,presets,types} 同步翻新
  - **Dashboard auth refresh-token 轮转** (#37247, `c10ccaaf`)：4 文件 +428 / -55；`plugins/dashboard_auth/nous/__init__.py:244-302 refresh_session(refresh_token)` POST grant_type=refresh_token 到 Portal /token + `:263-266` 空 RT fast-fail 不联网 + `:269-291` body + `x-nous-refresh-token` header + `:298-302` 400→`RefreshExpiredError` / 网络错→`ProviderError` + `:304-326 _token_response_to_session()` 参数化异常 + `:207-242 complete_login()` 捕获初次 RT；`hermes_cli/dashboard_auth/middleware.py:236 _attempt_refresh()` + `:255 refresh_token=new_session.refresh_token` + `:302 _attempt_refresh(request, *, refresh_token)` —— **关键修**：AT 缺席 + RT 存在不再硬 401，走 refresh 路径透明续期 + 写新 cookie；3 回归 case（AT 驱逐 + RT 存在 / 双 cookie 缺 / RT-only + 死 RT）
  - **Gateway 结构化 stream-event 协议** (#37250, `787936d1`)：8 文件 +740 / -29；**新建** `gateway/stream_events.py 171 行` 7 frozen dataclass（`:44 MessageChunk(text)` / `:56 MessageStop(final:bool)` / `:72 Commentary(text)` / `:85 ToolCallChunk(tool_name, args, preview)` / `:104 ToolCallFinished` / `:122 LongToolHint` / `:135 GatewayNotice`）；**新建** `gateway/stream_dispatch.py 132 行` `:40 class GatewayEventDispatcher(adapter, sink, enqueue_tool_line, tool_mode, preview_max_len, on_long_tool, on_notice)` + `:88-129 dispatch(event)` 路由 + mode 过滤（`all`/`new`/`verbose`/`off`）；`gateway/platforms/base.py:1873 supports_draft_streaming()` 默认 False + `:1934 render_message_event(event, sink)` 映 MessageChunk→on_delta、MessageStop→on_segment_break、Commentary→on_commentary + `:1955 format_tool_event(event, mode, preview_max_len)` 返 emoji+name+preview（或 None 吃事件）；Telegram `gateway/platforms/telegram.py:2498 send_draft()` 应用 `format_message()` + `parse_mode=MARKDOWN_V2` + `:2535-2542` MarkdownV2 优先 BadRequest 回 plain text — **告别 draft 流式动画与最终 sendMessage 格式跳变**；`gateway/config.py streaming.transport` 默认 → `"auto"` 让 supports_draft_streaming==True 的 adapter 自动 native draft；`tests/gateway/test_stream_events.py +182` + `tests/gateway/test_telegram_send_draft_format.py +114`；**表现层契约**：不写入对话历史，保持 cache / message-flow invariants
  - **Per-platform streaming 默认值** (#37303, `195c4d2a`)：2 文件 +86 / -1；`hermes_cli/config.py:1355-1364` 注释（Telegram 原生 sendMessageDraft 平滑→默认开；Discord/Slack 重复 editMessage 闪烁→默认关）；`:1365-1368 "platforms": {"telegram": {"streaming": True}, "discord": {"streaming": False}}`；deep-merge 用户值赢，全局 `streaming.enabled` master gate 仍然有效；**不 bump `_config_version`**；dashboard 自动暴露 toggle（schema 由 DEFAULT_CONFIG 生成）；`tests/hermes_cli/test_per_platform_streaming_defaults.py +65`；配套 `d78d77e4 feat(config): surface gateway streaming block in DEFAULT_CONFIG (#37285)` + `134643a2 fix(desktop): reflect active toolset provider in config panel`
  - **TUI 单一 `/model` 命令 + 统一 Sessions 浮层** (#37112, `fabca0bd`)：17 文件 +480 / -347；`hermes_cli/commands.py:126 CommandDef("model", ...)` 仍存 + `/provider` 别名移除 + `apps/desktop/src/lib/desktop-slash-commands.ts` 同步从 PICKER_OWNED_COMMANDS 删 `/provider` + `tests/test_tui_gateway_server.py` 翻转断言；`ui-tui/src/components/activeSessionSwitcher.tsx 394 行` 合并 /resume 冷启与 /sessions 实时为一浮层 — `:60-66 sessionRowKindAt(index, liveCount)` 三态（new/live/history）+ `:68-84 relativeSessionAge(ts)` today/yesterday/Nd ago + `:87-89 resumableHistory(history, live)` 按 id 去重；**armed-delete 跟 session id 而非 row index** 防 1.5s 实时状态轮询重排错杀；`ui-tui/src/app/slash/commands/session.ts:99-122` /resume + /sessions + /session + /switch 全开浮层，带 id 立即 resume cold，`new` 创建 live 不 guard，bare 不 guard
  - **Agent `runtime_cwd` 单一真源** (8 commit `4bc72960`+`16047655`+`f90777a6`+`75f47875`+`ac0cce5f`+`128da688`+`2564760d`+`eadfeef6`，全 emozilla `2026-06-01 16:55 -0700` 同分钟提交)：**新建** `agent/runtime_cwd.py 62 行` 5 函数 — `:20 _SESSION_CWD = ContextVar("HERMES_SESSION_CWD", default=_UNSET)` + `:23 set_session_cwd(cwd) -> Token` 多 session gateway 钉住 + `:28 clear_session_cwd()` + `:32 _session_cwd_override()` + `:39-50 resolve_agent_cwd()` 主用 ContextVar override→TERMINAL_CWD（**isdir guard**）→getcwd（**传播 OSError 不吞**） + `:53-62 resolve_context_cwd() -> Path|None` context-files 用 不 guard isdir（**给本地 CLI 留** None=getcwd fallback，避免 gateway 误吸 install 目录）；`agent/system_prompt.py:43 from agent.runtime_cwd import resolve_context_cwd` + `agent/prompt_builder.py:17 from agent.runtime_cwd import resolve_agent_cwd` + `:806 host_lines.append(f"Current working directory: {resolve_agent_cwd()}")` + `:805-808` OSError guard；**修多年悬而未决的 issue 簇** #24882/#24969/#27383/#29265 — 配置的工作目录不进 system prompt；`tests/agent/test_runtime_cwd.py 40 测试`（agent 路径 / context 路径 / SESSION_CWD override 三段，含 OSError 传播、tilde、空白、不对称设计 pin）；配套 `f90777a6 refactor` 切现有 callsite + `c79b80a8 test` 进 TestEnvironmentHints + `128da688 test(tools)` TERMINAL_CWD 契约 + `eadfeef6`+`75f47875` doc 校准 None 语义；`31c40c72 fix(desktop)` project folder session 稳定化基于此（14 文件 +493 含 `tests/agent/test_runtime_cwd.py +52` desktop-side regression）
  - **Model picker 模糊搜索** (3 commit `7527e7ae`+`53f598e7`+`0fdab53e`)：5 文件 +696 / -55；**新建** `web/src/lib/fuzzy.ts 192 行` + 镜像 `ui-tui/src/lib/fuzzy.ts 177 行` + `ui-tui/src/lib/fuzzy.test.ts 109 行 15 测试`；`:19-24 interface FuzzyMatch{score, positions[]}` + `:53-119 fuzzyScore(target, query)` subsequence 匹配评分 exact(+20)/prefix(+8)/word-boundary(+3)/contiguous(+5)/first(+5)/gap penalty(-3 cap)，不是 subseq 返 null + `:126-157 fuzzyScoreMulti(target, query)` 空白分割 AND 语义 + `:168-192 fuzzyRank<T>(items, query, toText)` 泛型 ranker 返 RankedItem[] 含 positions；`web/src/components/ModelPickerDialog.tsx:12,160-165,171-178` provider+model rank + `<mark>` 高亮；`ui-tui/src/components/modelPicker.tsx 197 行` type-to-filter 实时排序 + Backspace 编辑 + Ctrl+U 清 + Esc 在非空 filter 时只清不返；查询 `g4o` 命中 `gpt-4o`、`clad snnt` 命中 `claude-sonnet`
  - **Desktop session 卫生/archive/media streaming + connecting overlay** (#37099, `85b65e29`)：26 文件 +1000 / -77；`tui_gateway/server.py:2771-2824 session.create()` 不再创建 DB row 阻止 "Untitled" session 泄露（注释 `:2819-2824` 实证 row 由 `_ensure_session_db_row` + prompt.submit lazy 建）；`hermes_state.py:267 archived INTEGER NOT NULL DEFAULT 0` + `:1434-1448 set_session_archived(session_id, archived)` soft-hide + `:1569-1629 list_sessions(archived_only|include_archived)` 三态过滤 + `:3270-3292 count_empty_sessions()` 守 `message_count=0 AND ended_at IS NOT NULL AND archived=0` 防误删用户故意 archive 的 empty + `:3294-3309 delete_empty_sessions()` 孤儿化子 session 不 cascade；`apps/desktop/electron/main.cjs:375-427 hermes-media://` 自定义协议 secure/standard/stream/supportFetchAPI 权限 + STREAMABLE_MEDIA_EXTS 白名单（.mp4/.webm/.mp3/.m4a 等）非白名单 415 + electronNet.fetch Range 支持 — **去 data URL 16 MB cap + 支持视频拖动定位**；`apps/desktop/src/app/settings/sessions-settings.tsx +168 :42 listSessions(200, 0, 'only')` 拉 archived-only；`apps/desktop/src/components/gateway-connecting-overlay.tsx +183 :48-97` ASCII decode 动画连接成功淡出，boot.error 时 bail；后续 9 修复 — `42392309 cancellable first-launch install`（`desktop-install-overlay.tsx +79`）+ `5b71f7dd session search in sidebar`（138 行）+ `135c6509 stable in-workspace ordering + No-workspace default` + `de8bdf52 keep pinned + recent visible across compression` + `5e55b35c refactor: model management Command Center→Settings` + `a2b8e430 refactor: skills+tools 合并 pane` + `c2050183 content-hash build stamp --build-only/--force-build`（`tests/hermes_cli/test_gui_command.py +163`）+ `ac76bbe2 GUI quality-of-life triage` 38 文件 +1638 / -2227（含 `apps/desktop/src/lib/ansi.ts +175` + `ansi.test.ts +123`）+ `31c40c72 stabilize project folder sessions` 基于 runtime_cwd（14 文件 +493）+ `134643a2 reflect active toolset provider in config panel`
  - **Skills Hub browse cap 修复 + 源链接 + 复制按钮** (#37143, `59510d7b`)：`hermes_cli/skills_hub.py:343 _PER_SOURCE_LIMIT` 补 `"hermes-index": 5000` — **修 silent 50-item cap**；`:407-410` browse 表加 Identifier 列（overflow=fold 复制长 slug）+ `:429 r.identifier` 行；`:451-456` 替换 generic Tip→actionable hint；`:741-746 parallel_search_sources` 接 `browse_skills()` 修 double-counting；`:748-752` index 可用时**跳过 external API**；网页门户 `website/scripts/extract-skills.py` 合成 sourceUrl（github/clawhub/skills.sh/lobehub/browse.sh）+ `website/src/pages/skills/index.tsx` View source 按钮 + install Copy 按钮 + `tests/website/test_extract_skills.py 13 回归测试`（_source_url 合成、优先级、_guess_category 整理 430→173 类别）
  - **Cron skill 不可见 unicode 改净化非硬阻** (#37245, `2c0d6483`)：`tools/cronjob_tools.py:184-210 _strip_invisible_unicode(prompt) -> (cleaned, removed)` 保留合法 emoji ZWJ；`:235-266 _scan_cron_skill_assembled(assembled)` 返 `(cleaned_prompt, error)`；`:255-261` 净化 + 记 codepoints + skill body 是 install-time vetted 净化安全；`:262-265` 净化后**再扫** directive — **真注入 directive 仍能匹**不漏检；`cron/scheduler.py:1184-1194` 用 cleaned prompt 替代 raw；raw `_scan_cron_prompt` 路径保持硬阻；`tests/cron/test_cron_prompt_injection_skill.py:212-230` + `tests/tools/test_cronjob_tools.py:113-154`
  - **MCP HTTP fast-fail** (`c914e4a3` + `64f7f367`)：`tools/mcp_tool.py:1475-1478 _MCP_CONTENT_TYPES = ("application/json", "text/event-stream")` + `:1480-1553 async _preflight_content_type()` HEAD/GET 探针 ≤5s 检 HTML 抛 `NonMcpEndpointError` + `:1526-1531` HEAD 优先 405/501 回 GET + `:1537-1544` 静默 pass-through DNS/timeout 不二猜 SDK，**仅判 2xx**，missing/empty content-type 或 MCP-shaped pass-through + `:1546-1552` 错误带 URL + actual content-type + actionable hint；`tests/tools/test_mcp_preflight_content_type.py 137 行`；**告别填错 URL 等满 connect_timeout** + **不 retry 防反复打靶子**
  - **Kanban workspace 继承** (`72e82f88` + `272c2f30`)：`hermes_cli/kanban_db.py:4355-4370 decompose_triage_task` 取根 `workspace_kind`+`workspace_path`（之前强制 scratch）+ `:4365-4370` 存 root_ws_kind/path 给子 + `:4381-4392` per-child override 仍赢 + 防 worktree path 误指 + `:4393-4408` INSERT 用 child_ws_kind/path；`272c2f30` `kanban_create` 通过 `HERMES_KANBAN_TASK` env 让 worker 看清自己上下文 inherit；`tests/hermes_cli/test_kanban_decompose_db.py +62`
  - **File-safety sandbox-mirror 双层 soft guard** (`162c7856` + `1495f0cc`)：`agent/file_safety.py:498-531 classify_sandbox_mirror_target(path)` 路径形态检测 `…/sandboxes/<backend>/<task>/home/.hermes/…` + `:520-521 _find_sandbox_mirror_segments()` backend-agnostic 不需解析器/不需文件存在 + `:524-525` 返 dict（target/mirror_root/inner_path 用户大概率想 address 的 host 路径） + `:534-563 get_sandbox_mirror_warning()`；`:582-610 classify_container_mirror_target(path, mirror_prefix)` inner-container 案例 bind-mount 剥 sandboxes/ 前缀 + `:613-640 get_container_mirror_warning()`；接进 `tools/file_tools.py:328-376 _check_cross_profile_path()` 既有 write_file + v4a patch 无 API 改自动拿；防 docker 后端写 SOUL.md 两份分歧副本 #32049/#32213/#32407
  - **Telegram 观测群媒体缓存 → 平台无关原语** (`f768e75e` + `fa3b06b0`)：`gateway/platforms/base.py:1313-1366 cache_media_bytes(data, filename, mime_type, default_kind)` 平台无关 helper 任何 adapter 复用 + `:1330-1332` 由 filename+MIME 解析扩展+sanitize + `:1334-1366 is_image/video/audio/document` 分派返 CachedMedia 带 sandbox-translated agent-visible 路径 + `:1328 to_agent_visible_cache_path()` 防带空格路径泄露；`gateway/platforms/telegram.py` observed-group 路径 size-gate→download→cache_media_bytes→annotate + `_media_message_type()` 辅助合并 addressed-media 类型阶梯
  - **Gateway extract-stripped 工具响应恢复 + final-delivery 收敛** (#29346 `a1f76ba7` + `8bf498c2`)：`gateway/platforms/base.py:1748-1761 _strip_media_directives(text)` 剥 `[[audio_as_voice]]`/`[[as_document]]`/`MEDIA:<path>`；`:4082-4083 _response_pre_extract = response` 在 extract_media/extract_images/extract_local_files **前快照**；`:4114-4126` extraction 后**文本空+无附件** → 从 post-`extract_media` body 恢复（MEDIA 语法已剥空格路径）+ `:4120-4125 response_delivery_recovered` WARNING 含 pre-extract 大小+chat_id；`:4179-4200` 文本存在+非 `_tts_caption_delivered` → 发；`:4333 response_delivery_dropped` ERROR 守"响应非空但啥也没发"不变式；`tests/gateway/test_tool_response_drop_recovery.py +258`
  - **Weixin `asyncio.wait_for` 替 aiohttp ClientTimeout** (`56666901` + `765790a2`)：`gateway/platforms/weixin.py:370-390 _api_post()` `asyncio.wait_for(_do(), timeout=timeout_ms/1000)` + `:393-414 _api_get()` 同模式 + `:405-407` 注释钉死 cron `run_coroutine_threadsafe()` 场景 aiohttp 找不到 running task；`:417-435 _get_updates()` + `:562-591 _do_upload/_download()` 已是 wait_for 模式现在统一；`tests/gateway/test_weixin.py +145` 回归 cron→wechat
  - **MiniMax-M3 ≤204,800 stale cache 主动失效** (#36726, `1ffa22ee`)：`agent/model_metadata.py:204-208 "minimax-m3": 1_000_000` + `:1130-1140 _model_name_suggests_minimax_m3(model)` 返 `"minimax-m3" in model.lower()` 涵盖 native + OpenRouter + Nous 变体 + `:1554-1567` step 1 cached value 命中后判 `cached ≤ 204_800 AND _model_name_suggests_minimax_m3(model)` → `_invalidate_cached_context_length(model, base_url)` + log "Dropping stale MiniMax-M3 cache entry %s@%s -> %s"；**M3 是 1M context，pre-catalog 经 generic 'minimax' catch-all 持久化的 204800 不再永远 stick**
  - **Bluebubbles 群消息 mention gating** (`05022066`)：`gateway/config.py +16` + `gateway/platforms/bluebubbles.py +97` + `tests/gateway/test_bluebubbles.py +132` + 用户文档 `website/docs/user-guide/messaging/bluebubbles.md +27`；继 `abe0e19c refactor: simplify mention-gating helpers` 落地，群里能配"只有被 @ 时回复"
  - **xAI 视频按 modality 路由** (`8104b202`)：`plugins/video_gen/xai/__init__.py +89` video / video-with-image 分流 + `plugins/video_gen/xai/plugin.yaml` modality 元数据 + 4 测试 + `tools/video_generation_tool.py +1`
  - **Gateway 杂项**：`f7a3509b fix(gateway): honor WECOM_ALLOWED_USERS in env-only WeCom DM allowlist`（`gateway/platforms/wecom.py:165-171` 加 env 回落 `os.getenv("WECOM_ALLOWED_USERS", "")` + `tests/gateway/test_wecom.py +33`）+ `0cd5867b fix(whatsapp): honor dm_policy and group_policy open at the gateway` + `eee32cdd fix(gateway): fall back to in-process heartbeat when s6 sleep is missing #36208`（`hermes_cli/gateway.py +59` + `tests/hermes_cli/test_gateway_s6_dispatch.py +143/-34`）+ `b14e15c48 fix(gateway): clean service restart notifications`（9 文件 +378/-34 + `gateway/run.py +198` + `gateway/platforms/telegram.py +6` + `tests/gateway/test_restart_notification.py +42` + `tests/gateway/test_telegram_thread_fallback.py +29`）
  - **Docker/CI 维护**：`15cb4e22 install python3-venv` + `81dd43a8 preserve docker -w workdir in main-wrapper #35472/#36259` + `40ae1706 ci(docker): registry-backed build cache for arm64` + `4f7fe9bc fix(dashboard): surface Docker update guidance #34347/#37085`
  - **Installer**：`b34ee807 rename macOS installer to "Hermes" launcher #37516` + `1d9aacbd make commit pinning opt-in default to branch-follow` + `bb0619db align Codex OAuth persistence paths #37517` + `f600352e` merge `installer-optional-commit-pin` + `0c29cfd1 clarify desktop install retry guidance`
  - **TUI status bar 10 连**：`2f171743` pin status/model/whole-segment tail/smaller cwd + `e59b815c` prioritize status/model over cwd 窄屏 + `899e8b90` keep fmtCwdBranch default cap cwd at call site + `1d7a1c00` busy reservation /indicator-style aware + `13a2350c` pass indicatorStyle FaceTicker + `9cb7d40d` derive busy/duration from fmtDuration + `e25b2a6e` address Copilot review + `7d51cd75` merge bb/tui-statusbar-responsive + `038ed94a fix(cli): reset terminal input modes on TUI exit` + `a6b6afdf` merge maxmilian fix
  - **Model picker 多修**：`afea650e fix(model-picker): OpenAI shows curated models; OpenRouter no longer phantom-shows #37404`（`hermes_cli/models.py +23` + `tests/hermes_cli/test_openai_picker_curated.py +96`）+ `21f55af7 stop routing OpenAI selection to OpenRouter #37175` + `79bfddd3 restore gemini-3-flash-preview to Gemini OAuth picker #37606` + `e946f49a add gemini-3.5-flash to Gemini OAuth + API-key pickers #37046`
  - **CLI/Memory/Simplex 小修**：`043350df fix(cli): prepend queued notes safely to multimodal messages` + `c35ede78 refactor(cli): normalize note avoid blank lines in prepend helper` + `a26a12ad test(cli): cover _prepend_note_to_message str/list handling` + `32032e1e fix(simplex): avoid reconnecting healthy idle websocket` + `f24b7ed9 fix: make Honcho startup fail open` + `fc995634 feat(dashboard): add terminalBackground field to DashboardTheme` + `34468ed0 fix: normalize terminalBackground default and drop unrelated lockfile churn` + `d4b533de fix: batch of small robustness/correctness fixes from @kyssta-exe`
  - **Docs/chore**：`92273e4f docs: add 25 new community user stories #37048` + `c45593ce docs: expand quickstart Skills section #37047` + `3eb6bd7f docs: add Desktop App guide #37457` + `7450bee8 fix(docs): update desktop app docs` + AUTHOR_MAP 4 条（`f1237aa9`/`d967e744`/`3a8d643d`/`ddc22866`）+ `d183f75e chore: uptick` + `8977bf28` Potential fix + `267e7fd3`/`23c0578b` merge
- 验证策略：每条结论至少一条 `grep -n` / `Read` / `git show <sha> --stat` 命中 `/tmp/hermes-agent` checkout @ `c47b9d126`；每个 `file:line` 引用现行 source 实际行号；功能描述对照对应 PR 标题 + commit body + 实际 hunk 内容；104 commit 量级 + 22% feat 占比下重点抓 17 个核心 cluster（4 dashboard + 1 streaming protocol + 1 per-platform stream + 1 TUI sessions + 1 runtime_cwd + 1 fuzzy picker + 1 desktop hygiene + 1 skills cap + 1 cron unicode + 1 MCP fast-fail + 1 kanban inherit + 1 file-safety mirror + 1 telegram media cache + 1 gateway extract recover + 1 weixin asyncio + 1 minimax-m3 + 1 bluebubbles + 1 xai-modality）+ ~26 个独立 fix/refactor cluster

## [2026-06-01] sync | hermes-agent eb3cf9750 → b9646276f（58 commits，Desktop App + Dashboard Admin Panel + /undo [N] 三大特性合入）
- 同步范围：hermes-agent/main `eb3cf9750`（2026-05-31 12:13 -0700）→ `b9646276f`（2026-06-01 09:57 -0700），**58 个 commit**，约 22 小时窗口
- 验证基线：`/tmp/hermes-agent` 全历史 clone（`git fetch --unshallow origin main`）@ `b9646276f`，每条结论至少一条 `grep -n` / `Read` / `git show <sha> --stat` 命中
- 版本：仍 v0.15.1（`pyproject.toml:7 version = "0.15.1"` 不变，**无新发布 tag**）；但合入两个延期已久的超大 PR
- commit 类型分布：36 fix / 16 feat / 4 chore / 1 revert / 1 merge（27% feat，含两个超大集成与 7 个独立 feature）
- 新增文件：`changelog/2026-06-01-update.md`（550+ 行，18 章节）
- 更新文件：
  - `README.md` — 版本徽章 `v0.15.1 (eb3cf975) → v0.15.1 (b9646276)`、Changelogs 33 → 34、统计信息块跟踪 HEAD 与最后更新日期同步 2026-06-01、新增 changelog 列表条目（三大特性 + 7 独立 feat + 安全 + Docker 等综合摘要）
  - `index.md` — 顶部 tracking 字段（HEAD `b9646276f` / Total pages 33 → 34 changelogs / Last updated 2026-06-01）、changelog 列表新增 2026-06-01 条目
  - `log.md` — 本条记录
- 核心结论（均经源码验证，每个 `file:line` 引用现行 source 实际行号）：
  - **Hermes Desktop App** (#20059, `51c68d4ab`)：442 文件 +114,155 / -3,124；目录结构 `apps/desktop/{electron,src,scripts,assets,public}` + `apps/bootstrap-installer/` Tauri Windows 安装器 + `apps/shared/` workspace 共享；CLI 入口 `hermes_cli/main.py:14716-14759 subparsers.add_parser("desktop", aliases=["gui"], ...)` 含 `--skip-build`/`--source`/`--build-only`/`--fake-boot`/`--ignore-existing` 5 flag；远程后端模式 `HERMES_DESKTOP_REMOTE_URL` + `HERMES_DESKTOP_REMOTE_TOKEN` 短路本地 Python spawn（WSL2/Windows GUI 跨界）
  - **Dashboard 全管理面板** (#36704, `b571ec298`)：9 文件 +3,189 / -1；4 新页面 `web/src/pages/{McpPage,PairingPage,WebhooksPage,SystemPage}.tsx`（446+276+447+663 行）；`web/src/App.tsx:78-81,131-134` 路由；`hermes_cli/web_server.py +786`（6300→7079 行）新增 17 个端点（MCP 4 + Pairing 4 + Webhooks 3 + Gateway 3 + Credentials 3 + Memory 3 + Ops 6）；228 行 `test_dashboard_admin_endpoints.py`
  - **`/undo [N]` 三层落地** (#21910 SaguaroDev + #36699 Teknium)：5 commit
    - State (`3e59be0c4`)：`hermes_state.py:288 active INTEGER NOT NULL DEFAULT 1` + `:315-316` deferred index + `:2426 rewind_to_message` 软删 + `:2513 restore_rewound` undo-of-undo + `:2537 list_recent_user_messages` + read API `:2001 include_inactive=False` opt-in audit + `:863-870` v12 backfill
    - Memory hook (`31cfa08c6` + `e1951ce70`)：`agent/memory_provider.py:175 on_session_switch(*, rewound=False, ...)` 区分用户切换 vs undo 隐式回退；caller 没传时不转发
    - TUI (`243e836dc`)：`tui_gateway/server.py +51` command.dispatch undo 分支
    - CLI (`3f7d1c801`)：`cli.py:7106 undo_last(n, prefill)` in-memory truncate + soft-delete + agent surgery + memory notify + editable buffer prefill；`:8721-8728` slash 解析
    - Gateway (`0622a70eb`)：`gateway/run.py:8022` 解析 N + `:11630+ _handle_undo_command` echo backed-up text（messaging 无 composer）；`gateway/session.py SessionStore.rewind_session`；16 个 `locales/*.yaml` 同步 `undo.removed{turns}` + `undo.invalid_count`
  - **Curator inactivity 修剪 + 全 skill 用量遥测** (#36701, `70e1571d8`)：`agent/curator.py +53` 默认 off + days-since-last-use **forward from enablement**（避免开关一打开就 mass-prune）+ hub 安装永不修剪；`tools/skill_usage.py +326` telemetry 解耦 curation-eligibility + 新 `usage_report()` + `provenance()`
  - **Blank-slate skills** (#36228, `2ed96372a`)：`scripts/install.sh --no-skills` + `hermes profile create --no-skills` + 运行时 `hermes skills opt-out`/`opt-in` + marker `.no-bundled-skills`；`hermes_cli/skills_hub.py:1075/1145/1550-1553`；`tools/skills_sync.py:43,464,753 set_bundled_skills_opt_out()`
  - **Setup 行内解释** (#36227, `9074a154c`)：`hermes_cli/setup.py +8/-4` "Quick Setup (Nous Portal) — free OAuth login, no API keys" vs "Full setup — BYO keys"
  - **Free tool pool entitlement** (#36153, `e1c7a9aa7`)：`hermes_cli/nous_account.py:17,64,111,152` 与 Portal `tool-pool-eligibility.ts` byte-for-byte 对齐 + decoupled from paid/billing；`nous_subscription.py:889,903` per-tool checklist；`tools_config.py +40`
  - **MiniMax-M3 1M context** (#36214, `e3b3d4d75`)：`agent/model_metadata.py DEFAULT_CONTEXT_LENGTHS['minimax-m3']=1_000_000`（longest-key-first，M2.x 仍 204,800）；`a8526a415` openrouter+nous catalogs 默认指 m3
  - **Model picker group-layer description**：`47d2d0589`/`84d82453a`/`c9a28dfb0` 3 commit
  - **安全：Agent 写 `~/.hermes/config.yaml` 双闸门**
    - 工具层 (`8f2931e3e`)：`tools/file_tools.py:256 _hermes_config_resolved` + `:287` 错误提示指 `hermes config` CLI
    - 终端层 (`4e9d886d9`)：`tools/approval.py:131` 注释 "~/.hermes/config.yaml IS the security policy" + `:139 _HERMES_CONFIG_PATH` + `:166-170 _SENSITIVE_WRITE_TARGET` + `:369-370 tee/>/>>` + `:413-414 sed -i / sed --in-place` 全闸；9 regression test
  - **Skills guard 良性内容 + ignore 蜜罐** (`ba6ffd4ff`)：`tools/skills_guard.py +137`，`.skillignore` / `.clawhubignore` (gitignore-style) 排除 dev/docs；`SKILL.md` 永不可忽略；80 测试通过（64 旧 + 16 新）
  - **Gateway MEDIA 标签 4 连**：`e8827ef70`（JSON string values）/ `fb1b681b3`（JSON-embedded verbatim）/ `521d06975`（restrict auto-append to producer tools）/ `3ccf4fdc6`（code blocks + blockquotes）/ `6c73e8ffa`（mask as locator 模式，"masking is a locator, not a text rewrite"）；`tests/gateway/test_platform_base.py +16` inline-code-survives
  - **Gateway 服务重启通知清理** (`b14e15c48`)：9 文件 +378 / -34；新测试 `test_restart_notification.py +42` + `test_telegram_thread_fallback.py +29`
  - **Streaming broken-stream 不再误报输出截断** (#36705, `023149f66`)：`agent/conversation_loop.py +64` 区分 broken stream（retry-bump）vs output_length 截断（length-resume）；`tests/run_agent/test_run_agent.py +75`
  - **Desktop / Dashboard 后续 9 修复**：`3ef97a61b`/`fa4ebaa8b`/`77bb64813`/`7fbe9b79a`/`0bc616ecf`/`79f7e7a1e`/`359f2be12`（drop files anywhere 新 `chat-drop-overlay.tsx` + `use-file-drop-zone.ts`）/ `c1a531d06`/`e1eba6f8c`
  - **Docker s6 / 启动权限 10 连**：`b3aaf2676`+`e3998d471`（Playwright headless_shell #35717）/ `f106e58af`（s6 envdir 早于 browser path #34601）/ `bdceedf78`（chown top-level state #35098）/ `380ce4789`（non-root 不 drop privs #34837）/ `064875a54`（s6 /init 镜像 #34628）/ `a60bff282`（tini 兼容 shim #34192）/ `740fb28d0`（chown ensure_hermes_home #34107）/ `1031031de`（卷已 remapped 跳 boot chown #35027）/ `758454d1e`（**HERMES_UID/GID 校验防 stage2-hook 提权 #35340**）/ `dcbf62e26`（s6 gateway state legacy run cmd #34829）
  - **杂项**：`b9646276f`（HEAD，`os.fchmod` Windows 防护 atomic_json_write）/ `92a567db2`（CI #36687）/ `cd8aa389c`（revert WSL 终端钳制 #36096）/ `cf328723d`（Windows 原生 GA 去 early-beta #36093）/ `9a82cd33d`+`4e530f1a2`（Windows installer GitHub Action 签名 #36190）/ `a75a45414`+`e2ee9177f`（forwarded secret 回落 `.hermes/.env` #35583）/ `a5371b3e6`+`ef3a650f0`+`ec6261ae2`（AUTHOR_MAP）

## [2026-05-31] sync | hermes-agent 689ef5e2 → eb3cf9750（141 commits, v0.15.1 维护窗口）
- 同步范围：hermes-agent/main `689ef5e2`（2026-05-29 13:30 -0700）→ `eb3cf9750`（2026-05-31 12:13 -0700），**141 个 commit**，约 47 小时维护窗口
- 验证基线：`/tmp/hermes-agent` 全历史 clone @ `eb3cf9750`，逐 commit + `grep -n` + `git show <sha> --stat` 实证
- 版本：仍 v0.15.1（`pyproject.toml:7 version = "0.15.1"` 不变，**无新发布 tag**，纯增量维护）
- commit 类型分布：97 fix / 11 feat / 11 test / 5 chore / 4 perf / 2 docs / 2 refactor / 1 security / 1 revert（≈ 69% 修复，v0.15.1 后冷却期特征）
- 新增文件：`changelog/2026-05-31-update.md`（450+ 行，28 章节）
- 更新文件：
  - `README.md` — 版本徽章 `v0.15.1 (689ef5e2) → v0.15.1 (eb3cf9750)`、Changelogs 32 → 33、跟踪 HEAD 与最后更新日期同步、新增 changelog 列表条目
  - `index.md` — 顶部 tracking 字段（HEAD `eb3cf9750`）、Total pages 32 → 33 changelogs、changelog 列表新增 2026-05-31 条目（141 commit 总述）
  - `concepts/context-compressor-architecture.md` — 顶部 frontmatter `updated/tags/sources` 同步；新章节"2026-05-31 增量 — `/compress here [N]` 边界感知 + Compressor 四连修复"（`hermes_cli/partial_compress.py` 235 行 + 4 compressor fix + status bar token 钳制 + docs 阈值澄清）
  - `concepts/kanban-multi-agent-board.md` — 顶部加入 2026-05-31 双特性 + 三可靠性修复段（task_attachments 表 + `goal_mode`/`goal_max_turns` 字段 + legacy TEXT-PK rebuild + iteration budget 修 + recompute_ready failure_limit 对齐）；文件索引表追加 4 条新行
  - `concepts/cli-architecture.md` — frontmatter 同步；新章节"v0.15.1 维护窗口增量"覆盖 Quick Setup→Nous Portal + Full Setup happy-defaults + curses picker 迁移 + `hermes prompt-size` + `/compress here` 入口 + Tool Gateway 始终展示 + Model picker 三连 + CLI 状态簇 + Update/install 8 簇 + 进程标题 + MCP discovery 非阻塞 + TUI 簇；相关文件表新增 3 条
  - `concepts/messaging-gateway-architecture.md` — frontmatter 同步；新章节"v0.15.1 维护窗口增量"：Telegram DM topic 双修复（合成通知保留元数据 + `_get_dm_topic_info` 类级别解析）+ WhatsApp/WeChat 文本去抖批处理 + `/stop` 跨参与者 + `_HERMES_GATEWAY` 自指令循环防御三层 + 嵌套 `gateway.platforms` 合并 + watcher 分批 + LRU 封顶 + httpx pool 重试 + send_message 邮件 + 其它 12 条 + 媒体投递路径中和四层
  - `concepts/security-defense-system.md` — frontmatter 同步；新章节"v0.15.1 维护窗口增量"：CVE-2026-48710 Starlette pin（3 处 + 注释）+ mutation-verifier footer 路径中和五层防御 + 自指令循环防御 + Dashboard chat WS insecure-非环回 + Discord mention 不脱敏 + Skills rmtree read-only + interrupt state leak 修 + checkpoint preflight 优先级
  - `concepts/fuzzy-matching-engine.md` — frontmatter 同步；新章节"2026-05-31 增量 — 文件 IO 健壮性三连"：write/patch 原子化（`_atomic_write` line 772）+ UTF-8 BOM 处理（`_UTF8_BOM` line 127-143 + `_file_has_bom` 属性）+ 紧凑 gutter（`<n>|content` ~14% token 节省，删 `HERMES_READ_GUTTER` env 逃生口）+ 相对路径 anchor 绝对 base
  - `concepts/session-search-and-sessiondb.md` — frontmatter 同步；新章节"v0.15.1 维护窗口增量"：FTS5 优雅降级（`hermes_state.py:452 _sqlite_supports_fts5` + 4 commit 簇 + uv-managed Python 确保 FTS5 + warning 文案指 supported install）+ Mid-session 模型切换持久化（`SessionDB.update_session_model`）
  - `concepts/agent-loop-and-prompt-assembly.md` — frontmatter 同步；新章节"2026-05-31 增量 — Turn-Completion Explainer + max-iterations 总结路径修复"（`conversation_loop.py:4493-4540` + `run_agent.py:2179 _turn_completion_explainer_enabled` + `config.py:1255 display.turn_completion_explainer` 默认 True + max-iter summary 路径 schema-foreign keys strip #34436）
  - `concepts/auxiliary-client-architecture.md` — frontmatter 同步；新章节"v0.15.1 维护窗口增量"：cumulative-resend tool-arg 修复 → 6h 后 revert 双 commit 拉锯（streaming saga）+ Anthropic thinking-signature 在 orphan-strip 后降级（Opus 4.8 extended-thinking）+ 默认不 cap max_tokens + custom provider 4 元组 runtime main
  - `concepts/browser-tool-architecture.md` — frontmatter 同步；新章节"2026-05-31 增量 — CDP DOM-node 序列化降级 + Vision 4 MB 提前 cap"（`browser_supervisor.evaluate_runtime` 自动 retry `returnByValue=false` + `_browser_eval` 子进程 actionable hint + vision 4 MB embed cap 防 session wedge + 4xx 不重试）
  - `concepts/prompt-builder-architecture.md` — frontmatter 同步；新章节"2026-05-31 增量 — `hermes prompt-size` 诊断命令"（`hermes_cli/prompt_size.py:141 cmd_prompt_size` + 6 类 breakdown + `--platform` / `--json` flag + 离线运行）
  - `concepts/mcp-and-plugins.md` — frontmatter 同步；新章节"v0.15.1 维护窗口增量"：stdio MCP 子孙经进程组信号回收（`tools/mcp_tool.py:2270-2281 _stdio_pgids` + `:3699 killpg`）+ agent-capable startup MCP discovery 非阻塞（**新模块** `hermes_cli/mcp_startup.py` 59 行）+ OAuth 重连 poll 改 `await asyncio.sleep` + TUI 启动不被慢/死 MCP 卡 + mcp_serve 进 py-modules + tool_output_limits 不再 cache
  - `concepts/terminal-backends.md` — frontmatter 同步；新章节"2026-05-31 增量 — cwd 持久化 + spawn_via_env 防双包裹"（`tools/terminal_tool.py:1738 _resolve_command_cwd` ACP→env.cwd→init 优先级 + `tools/environments/base.py:843-846 rewrite_compound_background=False` 跳过二次重写）
  - `concepts/lsp-integration.md` — frontmatter 同步；新章节"2026-05-31 增量 — Windows .cmd shim 双修复"（spawn 探测 `.cmd/.bat` 走 shell + installer probe sweep `[name, name+".exe", name+".cmd", name+".bat", name+".ps1"]`）
  - `concepts/voice-mode-architecture.md` — frontmatter 同步；新章节"2026-05-31 增量 — SSH 下允许语音（探 PulseAudio / PipeWire socket）"（探 `PULSE_SERVER` unix path / `PULSE_RUNTIME_PATH/native` / PipeWire socket）
  - `concepts/smart-model-routing.md` — frontmatter 同步；新章节"2026-05-31 增量 — Model picker UX 三连"（多 endpoint provider 合并到一行 + catalog TTL 24h→1h + deepseek-v4-flash 进精选 + 按 maker 分组 + mirror test 清理）
  - `log.md` — 本条记录
- 核心结论（均经源码验证，关键 `file:line` 引用现行 source 实际行号）：
  - **Setup**：`hermes_cli/setup.py:3010` 菜单文本 + `:3064 _run_first_time_quick_setup` 调用 `hermes_cli.main._model_flow_nous`；`/tmp/hermes-agent` `git show de4f40ed0 --stat` 实证
  - **`/compress here [N]`**：`hermes_cli/partial_compress.py` 235 行 5 函数（`:55 parse_partial_compress_args` / `:111 _coerce_keep` / `:124 split_history_for_partial_compress` / `:180 rejoin_compressed_head_and_tail`）；`cli.py:10006-10019` 路由（实证）
  - **`hermes prompt-size`**：`hermes_cli/prompt_size.py:141 cmd_prompt_size`（153 行）+ `hermes_cli/main.py:14467-14486` subparser 注册（实证）
  - **Kanban 附件**：`hermes_cli/kanban_db.py:399 attachments_root` / `:429 task_attachments_dir` / `:889 class Attachment` / `:1044-1079 CREATE TABLE task_attachments` / `:2535-2620` accessors + `plugins/kanban/dashboard/plugin_api.py:638-640 _MAX_ATTACHMENT_BYTES=25*1024*1024` / `:687-727` POST / `:763 root.resolve()`（实证）
  - **Kanban goal_mode**：`hermes_cli/kanban_db.py:737 goal_mode: bool=False` / `:740 goal_max_turns: Optional[int]` / `:974,977` CREATE TABLE INTEGER NOT NULL DEFAULT 0 / `:1616-1624` additive 迁移 / `:813-817` row→Task 反序列化（实证）
  - **read_file gutter**：`tools/file_operations.py:707-713` 文档化紧凑 gutter；`grep -r HERMES_READ_GUTTER` 全仓零命中（env 已彻底删除）
  - **write/patch 原子化**：`tools/file_operations.py:772 _atomic_write` + `:1192-1207` patch 路径 temp + mv（实证）
  - **UTF-8 BOM**：`tools/file_operations.py:127 _UTF8_BOM` + `:131 _strip_leading_bom` + `:142 _starts_with_utf8_bom` + `:848 _file_has_bom` + `:947` read 注释（实证）
  - **FTS5**：`hermes_state.py:452 _sqlite_supports_fts5` + `:441-444` warning + `:514 _ensure_fts_schema` + `:747-812` v10 trigram 同闸（实证）
  - **Starlette CVE**：`pyproject.toml:86,118,125` 三处 pin `starlette==1.0.1` + `:178` 注释（实证）
  - **进程标题**：`hermes_cli/main.py:68 _set_process_title` + `:84-86 setproctitle` + `:11505 main()` 入口调用（实证）
  - **MCP pgid**：`tools/mcp_tool.py:2270-2281 _stdio_pgids: Dict[int,int]` + `:3699-3700 killpg` 文档（实证）
  - **MCP startup**：`hermes_cli/mcp_startup.py` 59 行新文件（实证）
  - **Telegram DM topic**：`gateway/run.py:12897 getattr(type(adapter), "_get_dm_topic_info", None)` + `:14232,14251 _is_telegram_dm_topic_target` + `gateway/platforms/telegram.py:1292,1318,1469`（实证）
  - **`_HERMES_GATEWAY` 自指令循环**：`gateway/run.py:740 os.environ["_HERMES_GATEWAY"]="1"` + `hermes_cli/gateway.py:5427,5512` 拒检测 + `cli.py:598-600` defense（实证）
  - **Watcher 分批**：`gateway/run.py:4475-4490` 原子分离 + 每 100 个 `await asyncio.sleep(0)`（实证）
  - **Telegram cli alternation curses**：`hermes_cli/setup.py:3010` Quick Setup menu 文案
  - **Terminal cwd**：`tools/terminal_tool.py:1738 _resolve_command_cwd` + `:2034 effective_cwd` + `:2255 cwd field`（实证）
  - **spawn_via_env 防双重写**：`tools/environments/base.py:843-846` 注释 + `rewrite_compound_background=False` 路径（实证）
  - **Turn-completion explainer**：`agent/conversation_loop.py:4493-4540` + `run_agent.py:2179-2204 _turn_completion_explainer_enabled` + `hermes_cli/config.py:1255` 默认 True（实证）
- 关键 commit 用 `git show <sha> --stat` 抽样：`de4f40ed0`（Quick Setup Nous Portal）/ `bcc830100`（`/compress here` 235 行新模块）/ `61268ff7a`（prompt-size 153 行）/ `b47cb1bbf`（Kanban attachments 13 测试）/ `0cd7d54b0`（Kanban goal_mode additive 迁移）/ `ea6eaabd8`+`b1a25404b`（gutter 紧凑+删 env）/ `39f6b6e9d`（原子写）/ `5f84c9144`（UTF-8 BOM）/ `5ad2b4c6d`+`97ecfa0fc`+`a7421dc7d`+`355af2c20`+`4fa20f9a8`+`ec67def5b`（FTS5 优雅降级 6 簇）/ `0437137ff`（Starlette CVE）/ `84ee80eb5`（进程标题）/ `93e6a05ef`+`e1293bde4`+`50db2d9c1`+`7b0915037`（model picker 四簇）/ `64628ea89`（Anthropic thinking signature）/ `ca03486b6`→`2b5268f71`（streaming saga）/ `4259bab7d`+HEAD `eb3cf9750`（Telegram DM topic 双修）/ `b0ce47daa`+`cddb7283d`（WhatsApp/WeChat 去抖）/ `42bbd221e`+`56b8dccf2`+`020601d41`+`e38b0b55d`（compressor 四连）/ `a29d64e50`（MCP pgid）/ `0c6e133c0`（MCP startup）/ `eb9bfd392`（asyncio.sleep）/ `cbf851ae1`（TUI MCP）/ `a57cc0008`（packaging）/ `92ad7cc62`（Browser CDP）/ `0ffbcbbe7`+`b4cf114f6`（Vision 4 MB cap + fail-fast）/ `d4e7b2fc1`（Voice SSH）/ `1fc7bdc5e`（Tool Gateway）/ `5a72e82fd`+`9d2571c86`+`e481b1533`（TUI agents nudge）/ `b1d34cf6e`+`cd067ab91`+`64998fa93`+`16882cfde`（TUI 杂项）/ `59b0ea98c`+`fb0ab2764`（explainer）/ `9b78f411c`+`4ec0adebe`+`bdfba4524`+`02d1da49d`+`c2cbe2c97`+`5cd6c1717`+`bd72d333d`+`e8076c1eb`+`234ac0093`（安全 wave 9 commit）/ `96643b4a5`+`7a315bd70`+`6f8975dcd`（file/terminal/spawn）/ `296fcdfa5`+`460771bf0`（LSP Windows）/ `794519c6a`+`e1945ff69`（state 模型切换）/ `1bdb29d93`+`2334228ec`+`14517ac1f`+`2475244ca`+`9ed9af2f7`+`bb79bcde6`+`c1b2d0917`+`bebd4f851`（update 8 簇）/ `1044d9f25`+`32899279a`+`0036c7292`+`dc4de1437`+`3c21fed09`+`e8cacb57d`+`44f3e5186`+`6d2727ef1`+`0bfe19ba1`+`d3724c0be`+`bfc4a2603`+`8bd00607d`+`9d4c81130`+`2259c15e4`+`45bc65abb`+`91a98d151`+`45465b0d5`+`2b16b756a`+`51d165a8e`+`1b955450e`+`20d073fd0`+`827ce602d`+`aa32edcac`+`d27601837`+`860cf28da`+`04de307d6`+`5921d6678`+`6a72af044`+`9fbde54b5`+`433bffff5`+`f2d4cf4f7`+`897f9533e`+`bede3cf12`+`182739fcd`+`6baf0016b`+`8ae0802d5`+`83a7d0b60`+`6a08fd3c3`+`8e5a6854c`+`6ab71d3bb`+`c70dca3a8`+`10dec7c6d`+`40fcb9658`+`622e53437`+`2062a8400`+`54aa4db1d`+`636ff636d`+`b4cf114f6`+`9d2571c86`+`e481b1533`+`5a72e82fd`+`8738cb92c`+`87e ...` 等约 100+ 杂项 fix/perf/test/chore/refactor commit
- 验证策略：每条结论至少一条 `grep -n` / `Read` 命中 `/tmp/hermes-agent` clone @ `eb3cf9750`；每个 `file:line` 引用现行 source 实际行号；功能描述对照对应 PR 标题 + commit body + 实际 hunk 内容；141 commit 量级 + 97% fix 占比下重点抓 11 个 feat + 4 perf + 1 security + 1 revert 上游 PR + 大块代码新增（235 / 153 / 59 行三新模块）验证

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
