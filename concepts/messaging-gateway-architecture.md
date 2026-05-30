---
title: Messaging Gateway Architecture
created: 2026-04-07
updated: 2026-05-27
type: concept
tags: [gateway, architecture, module, telegram, discord, messaging, qq, teams, line, simplex, ntfy, wecom, proxy, api-server]
sources: [gateway/run.py, gateway/platforms/, gateway/platforms/api_server.py, gateway/delivery.py, plugins/platforms/, hermes_cli/config.py, gateway/platforms/wecom_callback.py]
---

# 消息网关架构

## 概述

Gateway 是 Hermes Agent 的**统一消息网关**，截至 2026-05-24 支持 **23 个消息平台**（含 6 个插件平台：IRC / Teams / Google Chat / LINE / SimpleX Chat / **ntfy**），从单一进程管理所有平台的连接和消息分发。

## 架构

```
gateway/
├── run.py              # 主循环、斜杠命令、消息分发
├── session.py          # SessionStore — 对话持久化
├── delivery.py         # 消息投递
├── config.py           # 网关配置
├── hooks.py            # 钩子系统
├── pairing.py          # DM 配对
├── status.py           # 状态管理
├── mirror.py           # 跨平台镜像
├── sticker_cache.py    # 贴纸缓存
├── stream_consumer.py  # 流式消费
├── channel_directory.py # 频道目录
├── platform_registry.py # 平台插件注册表（PlatformRegistry）
├── slash_access.py     # 按平台的 admin/user 斜杠命令分级
├── shutdown_forensics.py # 关停诊断/取证记录
└── platforms/          # 平台适配器
    ├── telegram.py
    ├── telegram_network.py
    ├── discord.py
    ├── slack.py
    ├── whatsapp.py
    ├── signal.py
    ├── email.py
    ├── sms.py
    ├── matrix.py
    ├── mattermost.py
    ├── dingtalk.py
    ├── feishu.py
    ├── wecom.py
    ├── weixin.py
    ├── bluebubbles.py
    ├── homeassistant.py
    ├── webhook.py
    ├── msgraph_webhook.py
    ├── api_server.py
    ├── msgraph_webhook.py   # MS Graph webhook（v0.13.x+）
    ├── yuanbao.py / _media / _proto / _sticker
    └── base.py

plugins/platforms/         # 插件化平台（v0.13.x+）
├── irc/                   # IRC（参考实现）
├── line/                  # LINE Messaging API
├── google_chat/           # Google Chat
├── teams/                 # Microsoft Teams
└── simplex/               # SimpleX Chat
```

## 平台支持

### 内置消息平台（gateway/platforms/）

源代码 `gateway/config.py:82-111` 的 `Platform` Enum 显式列出所有内置 member。下表去除了 `LOCAL` / `WEBHOOK` / `API_SERVER` / `MSGRAPH_WEBHOOK` / `WECOM_CALLBACK` 这些非用户对话平台，剩 **17 个**：

| 平台 | 类型 | 特性 |
|------|------|------|
| Telegram | Bot API | 群组/私聊、语音转录、贴纸、代理支持、链接预览控制、`allowed_chats` |
| Discord | Bot API | 服务器/私聊、语音频道、Slash Commands、`DISCORD_ALLOWED_ROLES`（v0.13 起 guild-scoped，封堵 CVSS 8.1 跨 guild DM 旁路）、channel_prompts |
| Slack | Bot API | Workspace 集成、Thread 支持、`strict_mention`、`channel_skill_bindings`、`allowed_channels` |
| WhatsApp | Bridge (Node.js) | 群组/私聊、允许列表、v0.13 起默认**拒绝陌生人** + 永不在 self-chat 回复 |
| Signal | Bot API | 加密消息，原生格式化、reply 引用、reactions（v2026.4.23+） |
| Email | IMAP/SMTP | 邮件交互 |
| SMS | Twilio | 短信，字符限制 |
| Home Assistant | WebSocket | 智能家居事件 |
| Matrix | E2E 加密 | 去中心化消息、`allowed_rooms` |
| Mattermost | Bot API | 自托管团队消息、`allowed_channels` |
| 钉钉 | Stream | 企业消息，QR 扫码认证，require_mention + allowed_users 权限控制 |
| 飞书/Lark | Stream | 企业消息、`require_mention`、操作可配置的 bot admission policy（v0.13） |
| 企业微信 | Stream | 企业微信消息、QR 扫码 bot 创建（v2026.4.18+） |
| BlueBubbles | REST + Webhook | iMessage（macOS），tapback、已读回执 |
| 微信/WeChat | iLink Bot API | 长轮询收消息，AES-128-ECB 媒体加密，QR 登录 |
| QQ Bot | Official API v2 | WebSocket 入站(C2C/群/频道/DM) + REST 出站,语音转录(腾讯 ASR),allowlist + DM 配对 |
| Webhook | HTTP | 外部事件接收 |
| **腾讯元宝 Yuanbao** | API | 原生文本+媒体投递，sticker 支持（v2026.4.23+） |
| **IRC**（插件） | TLS asyncio | 零外部依赖，TLS、PING/PONG、nick collision、NickServ、频道寻址（v2026.4.23+，参考实现） |
| **Microsoft Teams**（插件） | Graph + Webhook | v0.12 落地插件 → v0.14 端到端：auth + webhook listener + pipeline + 投递（`plugins/teams_pipeline/`） |
| **Google Chat**（插件） | API | 第 20 平台（v0.13，`plugins/platforms/google_chat/`） |
| **LINE**（插件） | Messaging API | 日韩台主流通讯（v0.14，`plugins/platforms/line/`） |
| **SimpleX Chat**（插件） | 去中心化无 ID | privacy-focused（v0.14，`plugins/platforms/simplex/`） |
| **Google Meet**（plugin） | OpenAI Realtime + Node bot | 会议接入：转录 + 跟进（v0.12，`plugins/google_meet/`） |
| **ntfy**（插件） | HTTP streaming sub + POST publish | 第 23 平台。`plugins/platforms/ntfy/`，零额外依赖（仅 httpx），无原生 user identity —— 每 topic 视为单一受信任频道（2026-05-23） |

> 还原成插件后，gateway 核心从 21 个 if/elif 收敛到 1 个 registry 查询；新平台 0 代码改 core。

## v0.13+ 增强汇总

| 增强 | 说明 |
|------|------|
| **Session auto-resume** | 网关重启后自动恢复未完成会话（`#21192`） |
| **统一 allowlist** | Slack/Telegram/Mattermost/Matrix/DingTalk 全部支持 `allowed_channels`/`allowed_chats`/`allowed_rooms`（`#21251`） |
| **WhatsApp 默认拒生人** | 默认 reject strangers（v0.13 安全 wave） |
| **Discord 历史回填** | 首次进频道/线程读消息历史（`#25984`） |
| **Discord role-allowlist guild-scoped** | 修 CVSS 8.1 跨 guild DM bypass |
| **Native multi-image 投递** | Telegram/Discord/Slack/Mattermost/Email/Signal 全平价（`#17909`） |
| **FLAC 音频路由** | + Telegram 文档 fallback（`#17833`） |
| **`/handoff` 实时切 model/persona/profile** | 不丢任何 message/tool call（`#23395`） |
| **`clarify` 原生按钮** | Telegram + Discord 多选用平台按钮（`#24199/#25485`） |
| **Telegram skip-STT audio path + 2GB cap** | 通过 local Bot API server |
| **`ignore_root_dm` + lobby** | Telegram 系统命令集中（`c931dad1d`） |
| **`disable_topic_auto_rename`** | Telegram |
| **`pin incoming user message`** | Telegram |
| **`require_mention`** | Signal 群聊只回 @ |
| **QQBot 原生审批键盘** | 与 Telegram / Discord UX 对齐（`#21342/#21353`） |
| **Deliverable mode** | 任何 surface 都能 ship 原生 artifact（`#27813`） |
| **i18n** | 7 个 locale: zh / ja / de / es / fr / uk / tr |

### Bundled 平台插件（plugins/platforms/）

`gateway/platform_registry.py` 引入 `PlatformRegistry` 单例 + `PlatformEntry` dataclass，让任何人都可以把新平台以**纯插件**形式接入，无需改 gateway 核心代码。

当前 `plugins/platforms/` 下共有 5 个插件平台：`irc`、`line`、`google_chat`、`simplex`、`teams`。它们通过 `ctx.register_platform()` 自注册，启动时按文件系统扫描自动发现（`Platform._missing_()` 为 bundled 插件创建身份稳定的 pseudo-member）。

```python
# 插件注册入口（hermes_cli/plugins.py 提供 ctx.register_platform）
def register(ctx):
    ctx.register_platform(
        name="line",
        label="LINE",
        adapter_factory=create_line_adapter,
        check_fn=check_line_available,
        validate_config=validate_line_config,
        required_env=["LINE_CHANNEL_ACCESS_TOKEN", "LINE_CHANNEL_SECRET"],
        install_hint="pip install line-bot-sdk",
    )
```

### `PlatformEntry` 元数据字段（gateway/platform_registry.py:37-143）

| 字段 | 作用 |
|------|------|
| `adapter_factory` / `check_fn` / `validate_config` / `is_connected` | 工厂 + 健康检查 |
| `required_env` / `install_hint` / `setup_fn` | 安装 / 配置辅助 |
| `allowed_users_env` / `allow_all_env` | `_is_user_authorized` 集成 |
| `max_message_length` / `pii_safe` / `emoji` | 显示 / 隐私 / 智能分片 |
| `allow_update_command` | 是否允许该平台触发 `/update` |
| `platform_hint` | 注入系统 prompt 的平台行为提示 |
| `env_enablement_fn` ⭐ | 从 env vars 读取，返回要 seed 到 `PlatformConfig.extra` 的 dict（v0.13） |
| `cron_deliver_env_var` ⭐ | `*_HOME_CHANNEL` env 名；让 `cron.scheduler` 识别 `deliver=<name>` 为合法目标（v0.13） |
| `standalone_sender_fn` ⭐ | out-of-process delivery：cron 独立进程时打开临时连接发送，支持 OAuth refresh（v0.13） |

`env_enablement_fn` / `cron_deliver_env_var` / `standalone_sender_fn` 是 v0.13 抽离出来的 platform-plugin hooks，让插件平台**完全平权**：cron deliver、env-only setup 状态显示、out-of-process send 全部正常。

### 关键改造点

| 模块 | 改造 |
|------|------|
| `Platform` enum (`gateway/config.py:82-176`) | `_missing_()` 接受未知字符串，按 `plugins/platforms/` 扫描 + runtime registry 创建缓存 pseudo-member（`Platform('irc') is Platform('irc')` 永真） |
| `GatewayConfig.from_dict` | 解析 config.yaml 里的插件平台名，不再拒绝未知平台 |
| `_create_adapter()` in `gateway/run.py` | 先查 registry，未命中再 fall through 到内置 if/elif 链（line 5167） |
| `get_connected_platforms()` | 把未知平台委托给 registry |
| `PluginContext.register_platform()` | 镜像 `register_tool()` / `register_hook()` 模式 |
| `_apply_env_overrides` | 调用 `entry.env_enablement_fn()`，让 `gateway status` 看得到 env-only 配置（v0.13） |

### 5 个插件平台实现（HEAD）

| 插件 | 文件 / 行数 | 关键能力 |
|------|------------|---------|
| `plugins/platforms/irc/` | adapter.py | TLS asyncio，零外部依赖（v0.11.0） |
| `plugins/platforms/teams/` | adapter.py (1197) + 独立 `plugins/teams_pipeline/` (2436) | Bot Framework + MS Graph，会议召开 / 转录 / 摘要（v0.14.0） |
| `plugins/platforms/google_chat/` | adapter.py (3342) + oauth.py | Chat API + OAuth（v0.13.0，第 20 个平台） |
| `plugins/platforms/line/` | adapter.py (1638) | LINE Messaging API（v0.14.0） |
| `plugins/platforms/simplex/` | adapter.py (746) | 去中心化、无 user ID（v0.14.0） |
| `plugins/platforms/ntfy/` | adapter.py (582) + plugin.yaml (56) | HTTP streaming subscribe + POST publish；零额外依赖；**81 个新测试**；2026-05-23 通过 `b10f17b`→`6a8e131`→`3b096d6` 三 commit 链落地（先 built-in，再重构为插件，再加固 401/404 fatal-error 暴露） |

### 后续插件平台（v0.12 → v0.14）

- **Microsoft Teams** (`plugins/platforms/teams/` + `plugins/teams_pipeline/`，v0.12.0 起完整链路，v0.14.0 端到端) —— Microsoft Graph 完整栈（`tools/microsoft_graph_auth.py` + `tools/microsoft_graph_client.py` + `gateway/platforms/msgraph_webhook.py`）
- **Google Chat** (`plugins/platforms/google_chat/`，v0.13.0) —— 第 20 个平台
- **LINE** (`plugins/platforms/line/`，v0.14.0) —— 日韩台
- **SimpleX Chat** (`plugins/platforms/simplex/`，v0.14.0) —— 隐私优先去中心化
- **ntfy** (`plugins/platforms/ntfy/`，2026-05-23) —— HTTP-only 推送通知，第 23 个平台

### Discord 频道历史回填（v0.14.0+）

`gateway/platforms/discord.py:3683,3692,4784`：首次加入 Discord 频道/thread 时**回读近期消息**作为上下文，避免"我们在聊什么"。默认开。

### 跨平台统一 allowlist（v0.13.0+）

`allowed_channels` / `allowed_chats` / `allowed_rooms` 配置覆盖 Slack、Telegram、Mattermost、Matrix、钉钉（`gateway/platforms/dingtalk.py:392-496`）—— 统一的硬 gate ACL。

### Discord DM 角色 Guild-scoped（v0.13.0+）

`gateway/platforms/discord.py:508 dm_role_auth_guild`、`:2206-2235`：闭合 CVSS 8.1 跨 guild DM 绕过。允许列表绑定到具体 guild，不再被其他服务器借用。

### WhatsApp 默认拒陌生人（v0.13.0+）

`gateway/platforms/whatsapp.py:236-239`：`dm_policy: open | allowlist | disabled`（默认 open，但 SECURITY release notes 提及"strangers rejected by default" —— 配合 `allow_from`/`group_allow_from` 白名单使用）。`group_policy` 同步控制群组。

### Native button UI for `clarify`（v0.14.0+）

`tools/clarify_gateway.py:48`：Telegram + Discord 适配器 override `send_clarify`，渲染 inline button（如 Telegram `InlineKeyboardMarkup`）。tap 即答，移动端尤佳。

### `[[as_document]]` 技能媒体路由指令（v0.13.0+）

`gateway/run.py:11159,11163` + `gateway/platforms/base.py:2133,2154-2157,3160-3174`：skills 可在内容里加 `[[as_document]]`，强制 gateway 在支持的平台上把输出当 document 投递（而非 inline 消息）。

### 平台插件 12 个集成点全覆盖

`feat: complete plugin platform parity` (2e20f6ae2) + `feat: final platform plugin parity` (e464cde58) 让插件平台和内置平台行为一致：
- webhook 投递、PLATFORM_HINTS、`get_connected_platforms`、cron 投递、动态 toolset 生成、setup wizard 等
- bundled 插件平台（如 IRC、Teams、LINE、Google Chat）启动时自动加载（`feat(plugins): bundled platform plugins auto-load by default`，4d36349）

### 已 bundled 的平台插件（v0.12.0+）

`plugins/platforms/` 目录下随源码发行的平台插件：

| 插件目录 | 平台 | 关键源码 | 备注 |
|---------|------|---------|------|
| `irc/` | IRC | `adapter.py` | 首个参考实现，零外部依赖 |
| `teams/` | Microsoft Teams | `adapter.py` (Bot Framework) | Adaptive Card 审批，threading via `app.reply()`，本地图片走 attachment（避免 Markdown 链接渲染失败） |
| `line/` | LINE | `adapter.py` (LINE Messaging API SDK) | 免费 reply token 优先 + Push API 兜底；慢响应 (`LINE_SLOW_RESPONSE_THRESHOLD` 秒，默认 45s) 推送 Template Buttons postback 让用户重新获取免费 token |
| `google_chat/` | Google Chat | `adapter.py` + `oauth.py` | Pub/Sub 拉取（与 Slack Socket / Telegram long-poll 同形态，无需公网 URL）；`/setup-files` per-user OAuth 启用原生文件附件 |

### 多平台访问控制（v0.13.0）

`allowed_channels` / `allowed_chats` / `allowed_rooms` 配置项扩展到 Slack、Telegram、Mattermost、Matrix、DingTalk（`#21251`）。

源码验证：

- `gateway/platforms/slack.py:_slack_allowed_channels()` (line 3010)
- `gateway/platforms/mattermost.py:712` `allowed_channels` / `MATTERMOST_ALLOWED_CHANNELS`
- `gateway/platforms/dingtalk.py:_dingtalk_allowed_chats()` (line 392)

非空时充当**硬白名单**——不在表里的 channel / chat / room 收到的消息全部丢弃，不响应。

### 安全：Discord role-allowlist 改为 guild-scoped（v0.13.0）

`gateway/platforms/discord.py:2130` 注释直引：

> Voice inputs always originate from a specific guild (guild_id is in scope). Pass it so role checks are guild-scoped and not cross-guild.

修复 CVSS 8.1 的 cross-guild DM 绕过：之前 role allowlist 是 *全局* —— A guild 的角色能给 B guild 的用户开门。现在 `_is_allowed_user(user_id, guild=..., is_dm=...)` 必须传 guild 上下文（`discord.py:2134`、`2349`）。

### `[[as_document]]` 媒体路由指令（v0.13.0）

`gateway/platforms/base.py:2095-2119`：skill 输出里出现 `[[as_document]]` 字符串时，gateway 把所有图片附件改成**文档投递**（适用于 Signal / 部分企业平台需要保留原图细节的场景），然后从可见文本里剥离指令字符串。一次声明，覆盖该 response 中的所有图片路径。

### 网关 = 插件宿主（v0.12.0+）

v0.12.0 起 gateway 正式成为 **plugin host**：
- Drop-in messaging adapter 住在 core 之外
- Microsoft Teams 是首个 plugin-shipped 平台（v0.12.0 引入，v0.14.0 端到端完工）
- 第三方加新平台**不需要 fork 仓库**，只需 drop `plugins/platforms/<name>/` 目录

## 平台适配器基类

```python
# gateway/platforms/base.py
class BasePlatformAdapter(ABC):
    """平台适配器基类"""
    
    def __init__(self, config: dict, gateway):
        self.config = config
        self.gateway = gateway
        self.platform_name = self.__class__.__name__.lower()
    
    async def start(self):
        """启动平台连接"""
        raise NotImplementedError
    
    async def stop(self):
        """停止平台连接"""
        raise NotImplementedError
    
    async def send_message(self, chat_id: str, text: str, **kwargs):
        """发送消息"""
        raise NotImplementedError
    
    async def handle_message(self, event: MessageEvent):
        """处理接收消息"""
        await self.gateway.process_event(event)
```

## 消息处理流程

```
用户发送消息
  ↓
平台适配器接收
  ↓
创建 MessageEvent
  ↓
GatewayRunner.process_event(event)
  ↓
解析斜杠命令（如果有）
  ↓
查找或创建 Session
  ↓
调用 AIAgent
  ↓
获取响应
  ↓
通过平台适配器发送回复
```

## 会话管理

```python
# gateway/session.py
class SessionStore:
    """对话持久化存储"""
    
    def get_or_create_session(self, chat_id, platform):
        """获取或创建会话"""
    
    def save_session(self, session_id, messages):
        """保存会话"""
    
    def get_session(self, session_id):
        """获取会话"""
```

## 斜杠命令

与 CLI 共享的斜杠命令系统：

| 命令 | 描述 |
|------|------|
| `/new` | 新对话 |
| `/reset` | 重置对话 |
| `/model [provider:model]` | 切换模型 |
| `/personality [name]` | 设置个性 |
| `/retry` | 重试上一次 |
| `/undo` | 撤销上一次 |
| `/compress` | 压缩上下文 |
| `/usage` | 检查 token 使用 |
| `/insights [days]` | 使用洞察 |
| `/skills` | 浏览技能 |
| `/stop` | 中断当前工作 |
| `/status` | 平台状态 |
| `/sethome` | 设置主平台 |
| `/handoff` | 跨平台会话转移（`gateway/run.py` `_handoff_watcher` / `_process_handoff`，轮询 state.db 的 pending 会话并重新绑定到目标平台） |

### 按平台的命令分级

`gateway/slash_access.py` 提供按平台/聊天类型作用域的斜杠命令访问控制（`SlashAccessPolicy`）：

- `allow_admin_from` — 可运行全部已注册斜杠命令的管理员用户 ID 列表
- `user_allowed_commands` — 非管理员用户可运行的命令名白名单（未设置则非管理员无任何命令权限）
- 群组作用域有独立的 `group_allow_admin_from` / `group_user_allowed_commands`
- 若某作用域未设置 `allow_admin_from`，则该作用域的命令分级保持禁用（行为不变），需操作者显式列出至少一名管理员才会启用

## DM 配对

通过 `GATEWAY_ALLOWED_USERS` 环境变量控制谁可以与机器人对话：

```bash
# 允许的 Telegram 用户 ID
GATEWAY_ALLOWED_USERS=telegram:123456789,discord:987654321
```

未授权用户发送消息时，机器人不会响应（静默忽略）。

## 媒体处理

```
用户发送图片/文件
  ↓
平台适配器下载
  ↓
保存到临时目录
  ↓
传递给 Agent（vision_analyze 或文件处理）
  ↓
Agent 响应包含 MEDIA: 路径
  ↓
提取本地文件
  ↓
通过平台原生方式发送
```

## Deliverable 模式（可投递制品）

Gateway 不再只把图片/视频内嵌发送，而是按文件类型智能路由（"deliverable mode"）。

- **文件分区**：`extract_local_files`（`gateway/platforms/base.py:2158`）会从 Agent 响应文本中识别裸的本地文件路径。路由分区位于 `gateway/platforms/base.py:3258-3333`：
  - **内嵌发送**：仅图片、视频（在平台支持时内嵌展示）。
  - **原生上传**：PDF、docx/xlsx/pptx、压缩包、音频、html 等一律走 `send_document` 作为文件附件发送。
- **支持的文档类型**：`SUPPORTED_DOCUMENT_TYPES` 现为一个 dict（`gateway/platforms/base.py:815-836`），映射扩展名到 MIME 类型，包含 pdf/md/txt/csv/log/json/xml/yaml/yml/toml/ini/cfg/zip/docx/xlsx/pptx，并新增了 `.ts`、`.py`、`.sh`（均为 `text/plain`）。
- **Kanban 制品投递**：`kanban_complete` 工具新增 `artifacts` 参数（文件路径列表），Gateway 通过 `_deliver_kanban_artifacts`（`gateway/run.py`）将这些制品上传给用户。

## 网关服务管理

### Linux (systemd)

```ini
# ~/.config/systemd/user/hermes-gateway.service
[Unit]
Description=Hermes Agent Gateway
After=network-online.target

[Service]
ExecStart=/path/to/hermes gateway run
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
```

```bash
hermes gateway start    # 启动服务
hermes gateway stop     # 停止服务
hermes gateway status   # 检查状态
```

服务单元：`hermes-gateway.service` 或 `hermes-gateway-<profile>.service`

### macOS (launchd)

```xml
<!-- ~/Library/LaunchAgents/com.nousresearch.hermes-gateway.plist -->
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.nousresearch.hermes-gateway</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/hermes</string>
        <string>gateway</string>
        <string>run</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
```

```bash
hermes gateway start    # 启动 launchd 服务
hermes gateway stop     # 停止
hermes gateway status   # 状态
```

标签：`com.nousresearch.hermes-gateway`

## 更新时自动重启

`hermes update` 命令会自动：
1. 发现所有运行中的 gateway 服务
2. 重启 systemd/launchd 服务
3. 停止非服务模式的手动进程

### Per-platform 重启通知 opt-out（v2026.5+）

`PlatformConfig.gateway_restart_notification`（默认 `True`）覆盖**三种 lifecycle ping**：

1. **预重启 drain 通知**：`⚠️ Gateway restarting — Your current task will be interrupted...`，发送给所有活跃 session + home channel（`gateway/run.py:2462, 2500`）
2. **重启完成 ping**：`♻ Gateway restarted`，发送给触发 `/restart` 的 chat（`gateway/run.py:11406`）
3. **启动 ping**：`♻️ Gateway online`，发到 home channel（`gateway/run.py:11465`）

设计动机：**operator vs end-user surfaces**。Telegram 这种 back-channel 保留 ping 合理；与 end user 共享的 Slack workspace 把 "Gateway restarting" 读作 "the bot is broken"，operator 应能一致禁用三种噪音：

```yaml
slack:
  gateway_restart_notification: false
```

## 平台特定功能

### Telegram
- 支持群组和私聊
- 群消息需要 @mention 触发
- 语音消息转录
- 贴纸支持
- 话题/线程支持
- **代理支持**（v0.10.0）：`TELEGRAM_PROXY` 环境变量或 `config.yaml` 中 `proxy_url`
- **链接预览控制**（v0.10.0）：`config.yaml` 中 `telegram.disable_link_preview` 关闭消息链接预览
- **clarify 内联键盘按钮**（#24199，v2026-05-15+）：gateway 模式下 clarify 工具通过 Telegram inline keyboard 按钮呈现选项。`gateway/run.py` 现在向 `AIAgent` 传入 `clarify_callback`；`tools/clarify_gateway.py` 是事件驱动原语（register/wait_for_response/resolve_gateway_clarify，per-session FIFO + `threading.Event` 阻塞）。`gateway/platforms/base.py` 提供带编号文本兜底的抽象 `send_clarify`，所有适配器（Discord、Slack、WhatsApp、Signal、Matrix 等）开箱可用
- **原生 draft 流式**（Bot API 9.5+，v2026-05-10+）：通过 `sendMessageDraft` 实现 DM 回复的流式草稿，token 到达时平滑动画预览，替代旧的 `editMessageText` 轮询路径
- **状态消息 in-place edit**（#30864 / PR #30141，commit `9acf949`，2026-05-23+）：lifecycle / compression / context-pressure 状态回调不再每次 append 新气泡。`gateway/platforms/telegram.py:1915-1946 send_or_update_status()` 维护 `{(chat_id, status_key) → message_id}` 缓存（`telegram.py:471-474 self._status_message_ids`），首发 `send`，后续相同 key `edit`，edit 失败丢缓存 fallback fresh send。`gateway/run.py` 在 `_status_callback_sync` 走该路径（adapter 支持时），否则退到 `adapter.send()`。+5 测试覆盖 first send / edit / failure-fallback / 跨 key & chat 隔离

### Discord
- 支持服务器和私聊
- 需要 @mention 或 DM
- 语音频道支持
- Opus 音频编码
- Slash commands 集成
- **角色权限控制**（v0.10.0）：`DISCORD_ALLOWED_ROLES` 环境变量，逗号分隔 Role ID。与 `DISCORD_ALLOWED_USERS` 是 OR 关系——用户 ID 或角色任一匹配即放行，两个都没配则所有人可用
- **channel_prompts**（v0.10.0）：按频道/话题注入不同的系统提示，也扩展到 Telegram（群组/论坛话题）、Slack、Mattermost
- **@everyone 和角色 ping 屏蔽**：`allowed_mentions` 默认阻止 bot 触发全体通知
- **任意附件接收**：`allow_any_attachment` 配置项允许接收未在白名单类型内的附件（untyped file 路径）
- **频道历史回填**：默认开启，向共享会话注入最近频道历史（按用户 + 线程），避免每次热路径都全量扫描 `channel.history()`，受 `history_backfill` / `history_backfill_limit` 控制
- **choices 渲染为按钮**：多选模式（`choices` 非空）时每个选项渲染为一个 Discord 按钮
- **thread_require_mention**：`thread_require_mention` 配置项要求线程内消息也需 @mention 才触发

### 钉钉 DingTalk
- Stream 协议连接
- **QR 扫码认证**（v0.10.0）：`hermes_cli/dingtalk_auth.py`（292 行）实现 Device Flow——终端渲染 QR 码，用户用钉钉扫码，自动获取 AppKey/AppSecret，无需手动创建应用
- **require_mention + allowed_users 权限控制**（v0.10.0）：与 Telegram/Discord 对齐
- 支持 dingtalk-stream 0.24+ SDK 和 oapi webhooks

### 微信 WeChat
- SILK 编码语音回复（v0.10.0）
- 媒体附件提取和发送
- 原生 Markdown 渲染
- CDN 白名单 SSRF 防护（安全修复）
- macOS SSL 证书修复
- **文本去抖批合并**（2026-05-30，`b0ce47daa` + `cddb7283d`，#35301）：iLink 同样逐条投递无 batching。`gateway/platforms/weixin.py:1180-1197` 读取 `_text_batch_delay_seconds`（default **3.0s**，比 WhatsApp 紧）+ `_text_batch_split_delay_seconds`（default **5.0s**），路径同 WhatsApp `_enqueue_text_event` / `_flush_text_batch`。**配置 config-only**：`gateway.platforms.weixin.extra.text_batch_delay_seconds` / `text_batch_split_delay_seconds`

### WhatsApp
- 需要 WhatsApp Bridge (Node.js)
- 群消息需要前缀触发
- 允许列表控制
- **JID/LID alias 跨形稳定 pairing**（commit `52a368f`，2026-05-23+）：WhatsApp 会在 `xxx@s.whatsapp.net`（JID）和 `xxx@lid`（LID）两种 user identifier 之间漂移。`gateway/pairing.py:124-140 _user_id_aliases()` 把同一用户的所有 alias 折叠成一个 set，`_user_ids_match()` 用集合相交判等；`approve_pair` 和 list/lookup 路径（`pairing.py:377-378`）通过 `expand_whatsapp_aliases` 把 LID/JID 两种形式都登记进 `{platform}:{alias}` 索引，approval 不会因为对端 identifier 切形就失效。+73 测试覆盖各跨形场景
- **文本去抖批合并**（2026-05-30，`b0ce47daa` + `cddb7283d`，#35301）：WhatsApp 逐条投递消息无客户端 batching，快速多条爆发（forward 批 / paste-split）会逐条触发 agent。镜像 Telegram 既有 debounce —— `gateway/platforms/whatsapp.py:285-296` 读取 `_text_batch_delay_seconds`（default 5.0s）+ `_text_batch_split_delay_seconds`（default 10.0s），`_pending_text_batches` 按 session key 累积 TEXT 消息，静默期后 `_flush_text_batch` 一次性派发拼接结果。**配置 config-only**（commit message 误称环境变量；测试 `test_env_var_is_ignored` 显式断言 `HERMES_WHATSAPP_TEXT_BATCH_DELAY_SECONDS` **被忽略**）：`gateway.platforms.whatsapp.extra.text_batch_delay_seconds` / `text_batch_split_delay_seconds`，`_coerce_float_extra()` 防 NaN/Inf/负数 fallback 到 default

### Home Assistant
- 智能家居事件监控
- 设备控制
- 自动化触发

### Gateway 运维增强（v0.10.0）
- **Agent 缓存 LRU + 空闲 TTL 淘汰**：`_agent_cache` 加入上限和空闲超时，防止长期运行的 gateway 内存泄漏
- **临时 agent 关闭**：一次性任务完成后自动关闭临时 agent
- **WebSocket 重连等待**：发送前等待重连完成，避免丢消息

### v0.12.0+ 增强（2026-04-30 ~ 2026-05-13）

- **i18n 国际化**（c391684）：`agent/i18n.py` 引入轻量 i18n 框架，`locales/<lang>.yaml` 16 个语种（en、zh、ja、de、es、fr、tr、uk、af、ga、hu、it、ko、pt、ru、zh-hant）。仅覆盖**最高影响**的静态用户面字符串（approval 提示、若干 gateway 斜杠命令回复、restart-drain 通知），agent 输出/日志/工具结果保持英文。语言解析顺序：`lang=`参数 → `HERMES_LANGUAGE` env → `display.language` config → `"en"`。
- **i18n 也覆盖 web dashboard**（PR #22914 一并落地）。
- **Telegram /topic（DM topic mode）**（d6615d8、d35efb9）：在私聊里通过 `/topic <name>` 创建 Hermes 管理的伪话题（forum topic），每个话题独立 session。`/topic off` 退出，`auth gate + screenshot debounce`，CASCADE 删除，rename guard，General-topic 处理。详见 [[gateway-session-management]]。
- **Telegram native draft streaming**（4ed293b，Bot API 9.5+）：通过 `sendMessageDraft` 而非编辑现有消息来流式输出，避免反复编辑导致的 rate limit。
- **Telegram cadence tuning + adaptive fast-path**（ac95b8c）：短回复走快通道，长回复走平滑节奏，对应 `tests/.../adaptive text-batch tiers`。
- **Telegram edit overflow split-and-deliver**（bf1f409）：超长编辑不再静默截断，而是切分多条投递。
- **Telegram `clarify` inline keyboard**（29d7c24）：将 `clarify` 工具的多选项映射成 inline keyboard buttons，用户点击直接回填。
- **Telegram DM 群组允许列表**（1f71217）：DM 模式下也支持 group user allowlist，并保留 pre-#17686 chat-ID-in-_USERS 配置。
- **QQBot guild ACL 修复**（d69a0b2）：guild messages 和 guild DMs 也走 ACL 检查，堵住 allowlist 旁路。
- **QQBot 健康度修复簇**（2026-05-23+，腾讯团队 @walli）：
  - `bbd77d1` —— `_send_identify` 加 `INTERACTION` intent bit（`1<<26`），原本 approval-button click 触发的 `INTERACTION_CREATE` 事件根本没被网关派发；video/file 附件描述带本地 cached path，方便 LLM 引用文件回发
  - `a54f5af` —— `gateway/platforms/qqbot/adapter.py` 处理 WS opcode 7（Server Reconnect：关 WS 触发重连，保留 session 用 Resume）和 opcode 9（Invalid Session：看 `d` 字段判 resumable，仅 false 时才清 session）；删除 4009（连接超时是 resumable，不该清 session）；扩展 fatal close set 到 4001/4002/4010-4014（无意义重试停掉）
  - `0e7448d` —— `_download_and_cache(original_name=...)` 用 attachment 元数据原文件名，不再用 CDN hash 名（之前文件名是 `qqdownload_...oadftnv5` 一类）
  - `60b0a0e` —— `_guess_ext_from_data` / `_looks_like_silk` 把 `data[:5/4]` 改成 `data[:6]`，原 slice 长度不够匹配 6 字节字面量 `#!SILK`，依赖 9 字节 `#!SILK_V3` 和 2 字节 `0x02!` 兜底
- **Signal 多设备 group message 处理**（e713932）：linked device 经 syncMessage 路径下发的 group message 现在正确处理。
- **Weixin 内容指纹去重**（7a8ee8b）：相同内容的重复 webhook 投递通过 fingerprint 跳过。
- **WeCom AES key 自动 padding**（8f4c0bf）：base64 AES key 解码前自动 pad，兼容上游格式差异。
- **gateway 音频路由集中化 + FLAC 支持**（aa7bf32）：所有平台共用统一音频路由表（`gateway/platforms/base.py:_AUDIO_EXTS`），新增 `.flac`；Telegram 对原生不支持的格式（`.wav`/`.flac`）自动 document fallback。
- **gateway 多图发送**：`send_multiple_images` 在 Telegram、Discord、Slack、Mattermost、Email 上走原生 album/group API（3de8e21）；Signal 也补齐多图（04ea895）。
- **stream-consumer thread context 保留**（ff14666 + e164a9c）：消息溢出/首消息发送时不再丢失 thread routing。
- **stream-retry 诊断**（68e4464 + 126cbff）：drop log 携带 upstream + timing，方便定位是哪个 provider 抖了；同时折叠两行 drop status 到一行，避免噪声。
- **gateway shutdown forensics**（cede612）：非阻塞 diag、每阶段计时、stale unit warning。
- **gateway WSL interop PATH 保留**（8ab9f61）：systemd 单元里保留 WSL interop PATH，避免 `wsl.exe` 不可见。
- **gateway 状态版本检测**（d90f73b）：以 git HEAD SHA 作为 stale-code 检查依据（取代文件 mtime，CI 友好）。
- **gateway scoped-lock stale 检测**（fb1f409、653d304）：start_time 缺失（macOS）时走 cmdline 比对；cmdline 不可读时回退到 lock record argv。
- **gateway kanban 通知去重**（861ce7c、a96dd54）：blocked/gave_up 状态去重，发送异常 rewind，re-block 通知投递。
- **per-platform admin/user 斜杠命令拆分**（a282434）：管理员命令和用户命令分别注册到不同 menu。
- **per-platform reply_to_mode**（6b76ea4）：Discord/Telegram 从 config.yaml 读 reply_to_mode 而不仅是 env。

### v2026.4.18+ 增强

- **企业微信（WeCom）QR 扫码认证**：setup 向导（`hermes_cli/gateway.py:_setup_wecom`）通过 `gateway.platforms.wecom.qr_scan_for_bot_info` 扫码获取 bot 凭证，无需手动配置
- **插件斜杠命令跨平台原生化**：`register_command()` 的插件命令自动暴露为 Discord native slash、Telegram BotCommand、Slack `/hermes` 子命令，无需针对每个平台重复实现
- **决策型 command hook**：`command:<name>` 钩子可返回 `{"decision": "deny"|"handled"|"rewrite"|"allow"}` 在核心处理前拦截
- **Slack 反应生命周期**：`SLACK_REACTIONS` 环境变量开关控制 bot 收发消息时的反应（emoji）
- **Feishu @mention 上下文保留**：入站消息保留 @mention 上下文
- **飞书流式编辑换行修复**：流式输出不再前置多余空行
- **Session 状态维护**：`hermes_state.py` 新增 `maybe_auto_prune_and_vacuum()`，启动时幂等执行（跨进程通过 `state_meta` 表记录上次运行时间）。防止 session 和 FTS5 索引无限增长（一个重度用户报告 384MB/982 sessions 影响性能，prune + VACUUM 后降到 43MB）
- **MEDIA: 标签扩展**：支持 PDF、document、archive 扩展名的自动提取
- **全局隧道/代理场景 URL 开关**：`security.allow_private_urls` / `HERMES_ALLOW_PRIVATE_URLS` 允许解析私有 IP 范围（198.18.0.0/15、100.64.0.0/10），解决 OpenWrt / TUN 代理（Clash/Mihomo/Sing-box）/ 企业 VPN / Tailscale 场景。云元数据端点（169.254.169.254 等）始终阻断
- **平台 hints**：`PLATFORM_HINTS` 覆盖 Matrix、Mattermost、Feishu 的系统提示

### v2026.5.x 增强

#### 新平台插件（5 个 bundled）

SimpleX、LINE、Google Chat、Microsoft Teams 全部以 bundled 插件形式接入（`plugins/platforms/<name>/adapter.py` + `plugin.yaml`，通过 `ctx.register_platform()` 注册），核心 gateway 代码零改动。另有核心适配器 `gateway/platforms/msgraph_webhook.py`。`PlatformEntry` 现暴露通用插件钩子 `env_enablement_fn`（自动启用时注入环境变量）和 `cron_deliver_env_var`（cron `deliver=` 的 home-channel 目标）。

#### 斜杠命令的 admin/user 分级（`gateway/slash_access.py`）

新模块 `SlashAccessPolicy` dataclass 区分管理员和普通用户可执行的斜杠命令：

| 维度 | DM 配置键 | 群组配置键 |
|---|---|---|
| 管理员来源 | `allow_admin_from` | `group_allow_admin_from` |
| 用户可用命令 | `user_allowed_commands` | `group_user_allowed_commands` |

`is_admin()` / `can_run()` 做判定，`_ALWAYS_ALLOWED_FOR_USERS` 是兜底白名单。入口 `policy_from_extra()` / `policy_for_source()`。

#### `/handoff` — 跨平台会话转移

CLI 把 session 在 `state.db` 标记 `handoff_state='pending'`。`gateway/run.py` 的 `_handoff_watcher()`（2 秒轮询）通过 `claim_handoff()` 认领待转移记录，`_process_handoff()` 调用目标平台适配器的 `create_handoff_thread()`（Telegram 重写为创建论坛话题），以 `user_id="system:handoff"` 投递转移通知，最后标记 `completed`/`failed`。让一个会话能从 CLI「接力」到某个聊天平台继续。

#### i18n 静态文本本地化（`agent/i18n.py`）

`t(key, lang, **kwargs)` + `get_language()`，catalog 从 `locales/<lang>.yaml` 扁平化加载。当前 **16 种语言**：af, de, en, es, fr, ga, hu, it, ja, ko, pt, ru, tr, uk, zh, zh-hant。`display.language` 配置静态消息翻译，gateway 命令与 web dashboard 均已本地化。

#### 关停取证（`gateway/shutdown_forensics.py`）

`snapshot_shutdown_context()` 在收到 SIGTERM/SIGINT 时 <10ms 内快照 `/proc` 找出信号发送方，`spawn_async_diagnostic()` 非阻塞地输出 per-phase 计时与 stale-unit 警告，`check_systemd_timing_alignment()` 检查 systemd 超时配置是否合理。

#### 中断会话自动恢复

gateway 重启/崩溃后自动恢复被打断的 session。逻辑在 `gateway/session.py`（`mark_resume_pending()` / `clear_resume_pending()`，`resume_reason="restart_interrupted"`）与 `gateway/run.py`（`resume_pending` 持久标记 + 新鲜度守卫，防止陈旧 tool-tail 复活旧任务）。

#### 频道白名单

`allowed_{chats,channels,rooms}` 白名单扩展到 Telegram、Slack、Mattermost、Matrix、DingTalk、LINE，由 `gateway/config.py` 把 YAML 键映射为环境变量（如 `SLACK_ALLOWED_CHANNELS`、`TELEGRAM_ALLOWED_CHATS`、`LINE_ALLOWED_{USERS,GROUPS,ROOMS}`）。

#### Telegram 增强

- **原生草稿流式（draft streaming）**：`send_draft()` 用 Bot API 9.5 的 `sendMessageDraft`，复用 `draft_id` 动画化预览，仅私聊。
- **clarify 内联键盘**：`send_clarify()` 把多选澄清渲染成 `InlineKeyboardMarkup` 按钮回调（审批/更新提示也复用）。
- **guest mention 模式**：`TELEGRAM_GUEST_MODE` 下，非白名单群成员仅能通过显式 @ 提及触发 bot。
- **通知模式**：`notifications` 配置 `important`/`all`，静默发送中间态推送（`disable_notification=True`），除非 `metadata["notify"]=True`。
- **群组 slash 命令保留**（`9451087`，2026-05-24）：群里观察到的 slash 命令不再被静默吞（`gateway/platforms/telegram.py:+6 行` + 34 行新测试）。

#### 2026-05-24 平台细节修复簇

- **Webhook 路由 fail closed + Svix 签名**（`bbf02c3`/`dbf73e9`/`15aa688`）：见 `[[security-defense-system]]` 同名段落 —— `gateway/platforms/webhook.py:383-395 + 690+` 增 Svix 签名 + 缺 secret 返 403。
- **MSGraph Webhook 强制 client_state**（`4ca77f1`，#30169）：`msgraph_webhook.py:133-145` connect 拒绝 `_client_state is None`；`:316 _validate_client_state()` 在 expected 为 None 时返回 False（之前 True 等同未配 secret 全放行）。
- **Feishu auth 三连**（#30739/#30744/#30746 + `f378f00`）：`gateway/platforms/feishu.py` URL verification token 先于 challenge 回显 + webhook secret 强制 + 审批按钮 chat-binding。
- **QQBot 审批按钮 session-owner 授权**（`3e78e35`，#30737）：`qqbot/adapter.py:+54`。
- **Discord role allowlist 旁路移除**（`c3caca6`，#30742）：`gateway/run.py:6329-6341` 删除早期 return。
- **DingTalk 默认 allow-all 取消**（`1f897b0`，#30743）：`hermes_cli/gateway.py:_setup_dingtalk` 不再自动写 `DINGTALK_ALLOW_ALL_USERS=true`。
- **DingTalk 断开前 finalize streaming 卡片**（`39b8d1d`）：`gateway/platforms/dingtalk.py:+13` 在 `_http_client.aclose()` 之前先 `_close_streaming_siblings`，防止 AI Card 卡死 streaming 状态。
- **WeCom flush cancel-delivery 竞态防护**（`5848174`）：`gateway/platforms/wecom.py:619-628 _flush_text_batch` 加 `_pending_text_batch_tasks.get(key) is not current_task` 同步检查，关闭 sleep/cancel 重叠时 message silently dropped 的窗口（+89 行测试）。
- **WeCom-callback token 失效自动 refresh**（`21db250`）：errcode 40001/42001 时 evict cache + 用新 token 单次重试（之前直到 TTL 7200s 才换 token）。
- **Gateway debouncer + CodeQL 日志最小化**（`7abd627` + `1bed4e8`）：`gateway/platforms/base.py:4-7` debounce 调试日志删除 `event.text[:60]` 切片，改 `text_len=...`。
- **Plugin transform_llm_output 流式可见性**：见 `[[interrupt-and-fault-tolerance]]` "Streaming 完成可见性" 章节 —— `gateway/run.py:17680-17717` `_transformed=True` 时编辑已 streamed message in-place 而非发重复，避免 plugin 修改不可见。

### 与其他 Agent 框架对比

| 特性 | Hermes | OpenClaw | Claude |
|------|--------|----------|--------|
| 平台数量 | 23（17 内置 + 6 插件） | 14+ | 1 |
| 统一网关 | 单一进程 | 支持 | N/A |
| 会话共享 | 跨平台 | 支持 | N/A |
| 语音转录 | Telegram/Discord | 支持 | N/A |
| 群组支持 | 多平台 | 支持 | N/A |
| 服务管理 | systemd/launchd | 支持 | N/A |

## Gateway Proxy Mode（薄中继模式，2026-04-14）

通常 Gateway 和 Agent 跑在同一进程:Gateway 接收消息 → 直接调用 `AIAgent.run_conversation()`。**Proxy mode** 把两者分开——Gateway 只做平台 I/O(加密、分片、媒体),所有 Agent 工作转发给远程 Hermes API server。

### 典型用途

```
[Matrix/Discord/...]  ←→  [Gateway (Linux Docker, E2EE keys)]
                                    │ POST /v1/chat/completions (SSE)
                                    ↓
                              [Hermes API server (macOS host)]
                                    │
                                    ↓
                     本地文件、memory、skills、统一 session store
```

**解决的问题**:想用 Matrix E2EE,但 E2EE 需要持久化加密密钥,跑在 Docker 里比较稳定;而 agent 本身想跑在 macOS 主机上访问本地文件/技能/记忆。原来这俩得二选一,proxy mode 把它们串起来。

### 启用方式

```yaml
# ~/.hermes/config.yaml — 配置优先
gateway:
  proxy_url: "http://host.docker.internal:8080"
```

或环境变量(Docker 友好,不用挂 config):

```bash
GATEWAY_PROXY_URL=http://host.docker.internal:8080
GATEWAY_PROXY_KEY=<matches upstream API_SERVER_KEY>
```

### 实现位置

`gateway/run.py:7709` 起:
- `_get_proxy_url()` — 先查 env var 再查 config.yaml
- `_run_agent_via_proxy()` — HTTP + SSE streaming 转发,解析流式响应
- `_run_agent()` — 检测到 proxy_url 就走 proxy 路径,否则走本地 agent
- `GatewayStreamConsumer` 照常工作,流式分片仍然在 Gateway 侧完成

### 关键特性

| 机制 | 说明 |
|---|---|
| `X-Hermes-Session-Id` header | 携带 session id 保证跨请求 session 连续 |
| `GATEWAY_PROXY_KEY` | 和远端 `API_SERVER_KEY` 匹配,走 Bearer 鉴权 |
| SSE streaming | 响应按 chunk 过来,Gateway 流式发送到平台 |
| 错误兼容 | 返回的 result dict 结构与本地 agent 一致,session store 照常记录 |
| 平台无关 | 不只是 Matrix,任何平台 adapter 都能走 proxy 模式 |

### 调用链

```
用户在 Matrix 发消息
    ↓ E2EE 解密 (Gateway 侧)
gateway.process_event()
    ↓
_run_agent() → 检测到 proxy_url
    ↓
_run_agent_via_proxy():
    POST {proxy_url}/v1/chat/completions
      + X-Hermes-Session-Id: <sid>
      + Authorization: Bearer <GATEWAY_PROXY_KEY>
      + body: { messages: [...], stream: true }
    ↓ SSE stream 到达
    逐 chunk 通过 GatewayStreamConsumer 转发到平台
    ↓ E2EE 加密 (Gateway 侧)
发送回用户
```

## Telegram DM Topic 投递（2026-05-26，6 commit 簇）

涉及 6 个 commit（基线 commit `415be5539`，跟进 `96c71d8c4` / `dcd504cea` / `c394e7919` / `5b1c75d66` / `27df4b388`）。**问题域**：Telegram 同时有 group/channel 内的 forum topic（thread_id > 0，chat_id < 0）与 **DM 私聊** 内的 topic（chat_id > 0）。通用 `DeliveryRouter.send()` 路径在 metadata 里塞 `thread_id` 给 group topic 用得很顺，**直接给 DM 私聊 forum topic 反而通不过 Telegram API**。

**核心修复（`gateway/delivery.py` commit `415be5539`）**：

```python
def _looks_like_telegram_private_chat_id(chat_id: Optional[str]) -> bool:
    if chat_id is None:
        return False
    try:
        return int(chat_id) > 0
    except (TypeError, ValueError):
        return False
```

`DeliveryRouter.send()` 检测到 `target.platform == Platform.TELEGRAM and _looks_like_telegram_private_chat_id(target.chat_id)` 时**不把 `thread_id` 塞进通用 send metadata** —— DM topic 走 adapter-level 的 direct route 而非通用 thread_id forwarding。

**沿 lifecycle 的 5 个跟进**：

| Commit | 行为 |
|--------|------|
| `96c71d8c4` 要求 anchor | DM topic delivery 默认必须有 `reply_to` anchor（防垃圾 thread） |
| `dcd504cea` 自动 create | 首次 DM topic 不存在 → adapter 自动 `forum_topic_create` |
| `c394e7919` 刷新过期 thread | thread_id 在 Telegram 端 expire 后自动重 fetch + cache 失效 |
| `5b1c75d66` refactor | 简化 refresh helper |
| `27df4b388` 豁免 anchor-required | `reply_to_mode=off` 的 DM topic send 不受 anchor-required 约束（手工 exempt 路径） |

## Telegram 表格 Row-Group 间距收紧（2026-05-26，fix）

`9d10c45e3 fix(telegram): tighten table row-group spacing and drop redundant first bullet`：GFM → Telegram-row-group rewriter 之前用 `"\n\n".join(rendered_rows)`，多列表 mobile 上炸成一 bullet 一段；另当 table 无 row-label 列时，row heading 出两次（standalone bold + 首 bullet）。

修复：row-group 内 heading-to-bullets 用单 `\n`，row-group 之间空一行；当 table 无 row-label 时跳过 value == heading 的首 bullet。

## WeCom Callback defusedxml + Lazy Dep（2026-05-26，harden）

`gateway/platforms/wecom_callback.py:20-24`（commit `5744b1757`）：把 `from xml.etree import ElementTree as ET` 换成 `import defusedxml.ElementTree as ET`。WeCom callback request body 是 **pre-auth untrusted**，defusedxml 屏蔽 entity-expansion / billion-laughs / XXE DoS。response-building XML 在 `wecom_crypto.py` 不动（不从 untrusted 输入 parse）。

跟进 `31c8d5ff5`：把 defusedxml import 包 try/except（同 `aiohttp` / `httpx` 兼容模式），set `DEFUSEDXML_AVAILABLE` flag；`check_wecom_callback_requirements()` 检 flag，缺 dep 时 log 实际缺什么 + skip adapter（不再 hard import crash）；`pyproject.toml` 新加 `[wecom] extra` with `defusedxml==0.7.1`；`tools/lazy_deps.py` 注册触发 lazy install prompt。

## 2026-05-27 wave — Telegram 多修复 + API Server CRUD + Signal/Slack/Google Chat 小修

### Telegram 后续 wave

在 2026-05-26 DM topic 6 连之上又叠加多修复：

| Commit | 行为 |
|--------|------|
| `9acf949` | **feat: edit status messages in place instead of appending (#30864)** — 状态消息原位编辑 |
| `1ac8deb` | **feat(gateway): stream Telegram edits safely** — 流式 chunks 安全编辑同一消息 |
| `0325e18` | **fix(gateway): keep Telegram heartbeat + interim commentary on; edit heartbeat in place (#33187)** |
| `95a0955` | **fix(gateway): restore Telegram DM topic thread_id after session split (#27166)** |
| `3ec28f3` | **fix(telegram): preserve topic metadata on overflow edits** |
| `b38140e` | **fix(gateway): allow chat-scoped telegram auth without sender user_id** |
| `d81b888` | **fix(telegram): report cron topic fallback** |
| `16d8e44` | **fix(telegram): add DM topic typing fallback when message_thread_id rejected** |
| `aef297a` | **fix(telegram): skip send_chat_action for DM topic reply-fallback lanes** |
| `b323957` | **fix(telegram): preserve DM topic routing via reply fallback** |
| `ae005ec` | **fix(send_message): map Telegram General topic id to None for forum groups (#22423)** |
| `60f84c6` | **gateway: quiet Telegram operational chatter** |
| `efa9525` | **fix: ignore Telegram start pings** |
| `8807b1c` | **fix(gateway): hide telegram compaction status noise** |
| `9d789f3` | **feat: add disable_topic_auto_rename gateway flag** |
| `ad2531b` | **feat: skip-STT audio path + 2GB cap via local Bot API server** |
| `a724c3b` | **feat: pin incoming user message for duration of agent turn** |
| `c931dad` | **feat: ignore_root_dm with system command lobby** |
| `b1acf80` | **feat: support quick-command-only menus** |

### API Server CRUD（OpenAI-compatible 网关增强）

`gateway/platforms/api_server.py` 大幅扩展（commit `f7527b0` +476 行 + #33016）：

- **Session 控制**：新端点让外部客户端 CRUD session（前提：API_SERVER_KEY Bearer）
- **`GET /v1/skills`**（#33016）—— 列已安装 skill（name/description/category）
- **`GET /v1/toolsets`**（#33016）—— 列 `api_server` 平台 resolved toolset + 展开的 tool name
- 全部受 `API_SERVER_KEY` Bearer scheme 保护
- `/v1/capabilities` 广告 `skills_api` + `toolsets_api` 两个新能力（`9622326`）
- session chat API 支持媒体输入（`464b51d`）

> 解决场景：先前外部客户端只能起 dashboard web server，或通过 chat 让 model 列 skill —— 现在 deterministic、不引入 model cost。

### Signal / Google Chat / Slack 小修

- `7f40767` **feat(signal): add `require_mention` filter for group chats**
- `c386400` **fix(security): honor relay-declared sender_type in Google Chat adapter to prevent BOT filter bypass**
- `8578f89` **test(google-chat): cover relay-declared sender_type honoring**
- `24d3216` **fix(slack): enable writable app home DMs in manifest**

### Voice-mode 容器化音频桥

- `bde487c` **fix(voice): honor `PULSE_SERVER`/`PIPEWIRE_REMOTE` inside Docker (#21203)**
- `30dd554` **fix(voice_mode): generalize container phrasing and use `$XDG_RUNTIME_DIR`**

### Gateway/SQLite 杂项

- `dbafa08` **fix(cron): avoid delivery origin as sender identity**
- `e572737` **Fix cron dashboard rendering for partial jobs** + `e407376` partial job records normalize + `96dc272` getJobState helper
- `2a7047c` **fix(sqlite): fall back to `journal_mode=DELETE` on NFS/SMB/FUSE (#22043)** —— 当 sessions.db 跑在网络共享盘时 WAL 不可用，自动降级
- `78b0008` **fix(gateway): also catch restart TimeoutExpired; friendly message** + `dccf1fb` cap adapter disconnect during stop

## 相关页面

- [[gateway-session-management]] — 网关会话管理架构
- [[cron-scheduling]] — Cron 调度器由网关驱动
- [[hook-system-architecture]] — 网关事件钩子系统
- [[security-defense-system]] — Webhook 硬化、Gateway 平台审批授权链、WeCom callback defusedxml、API server key placeholder
- [[dashboard-auth-oauth-gate]] — Dashboard 鉴权独立闸门（与 api_server Bearer scheme 互补）

## 相关文件

- `gateway/run.py` — 主循环和消息分发
- `gateway/session.py` — SessionStore
- `gateway/platforms/base.py` — 平台基类（`extract_local_files`、`SUPPORTED_DOCUMENT_TYPES`、`send_document`）
- `gateway/delivery.py` — 消息投递（含 2026-05-26 `_looks_like_telegram_private_chat_id` DM topic 直发分支）
- `gateway/config.py` — 网关配置
- `gateway/platforms/` — 平台适配器目录
- `gateway/platforms/api_server.py` — **2026-05-27** Session CRUD + GET /v1/skills + /v1/toolsets（+476 行）
- `gateway/platforms/wecom_callback.py:20-24` — **NEW 2026-05-26** defusedxml + `DEFUSEDXML_AVAILABLE` flag
- `hermes_cli/gateway.py` — Gateway CLI 命令
