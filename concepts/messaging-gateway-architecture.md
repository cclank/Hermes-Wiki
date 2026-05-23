---
title: Messaging Gateway Architecture
created: 2026-04-07
updated: 2026-05-14
type: concept
tags: [gateway, architecture, module, telegram, discord, messaging, qq, proxy]
sources: [gateway/run.py, gateway/platforms/, gateway/platform_registry.py, hermes_cli/config.py, plugins/platforms/]
---

# 消息网关架构

## 概述

Gateway 是 Hermes Agent 的**统一消息网关**，支持 **20+ 消息平台**（截至 v0.13.0），从单一进程管理所有平台的连接和消息分发。

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
    ├── api_server.py
    └── base.py
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
| **IRC**（插件） | TLS asyncio | 零外部依赖，TLS、PING/PONG、nick collision、NickServ、频道寻址（v2026.4.23+，首个参考实现） |
| **Microsoft Teams**（插件） | Graph API | v0.12.0 引入，首个 plugin-shipped 平台 |
| **Google Chat**（插件） | Pub/Sub + Chat REST | **第 20 个平台**（v0.13.0），Cloud Pub/Sub 入站 + per-user OAuth 附件，service account / ADC 双路径 |
| **Line**（插件） | Line Messaging API | v0.13.0 引入 |

### Bundled 平台插件（plugins/platforms/）

通过 `PlatformRegistry` 接入，行为与内置平台完全一致：

| 插件平台 | 实现 | 引入版本 |
|----------|------|----------|
| **IRC** | TLS asyncio，零外部依赖、NickServ、PING/PONG、频道寻址 | v2026.4.23（首个参考实现） |
| **Microsoft Teams** | Bot Framework + Adaptive Card 审批 | v0.12.0（19th platform） |
| **Google Chat** | Cloud Pub/Sub pull + Chat REST、每用户 OAuth 文件附件 | v0.13.0（20th platform） |
| **LINE** | aiohttp webhook + HMAC-SHA256 签名 + reply token / Push API fallback | v0.13.0+ |

第三方插件（`~/.hermes/plugins/`）走相同机制，无需改 gateway 核心。

### 协议 / 内部平台

`LOCAL`（CLI）、`WEBHOOK`、`API_SERVER`、`MSGRAPH_WEBHOOK`、`WECOM_CALLBACK` 是协议接入点，不对应一对一的「消息平台」。

## 平台适配器插件化（v2026.4.23+，v0.13.0 扩展）

`gateway/platform_registry.py` 引入 `PlatformRegistry` 单例 + `PlatformEntry` dataclass，让任何人都可以把新平台（IRC、Teams、Google Chat、LINE 等）以**纯插件**形式接入，无需改 gateway 核心代码。

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

### 4 个 bundled 插件参考实现

| 插件路径 | 标签 | 关键技术 |
|----------|------|----------|
| `plugins/platforms/irc/` | IRC | asyncio + TLS + NickServ，零外部依赖 |
| `plugins/platforms/teams/` | Microsoft Teams | Bot Framework + Adaptive Card 审批 + threading |
| `plugins/platforms/google_chat/` | Google Chat | Cloud Pub/Sub pull + Chat REST + 每用户 OAuth 文件附件 |
| `plugins/platforms/line/` | LINE | aiohttp webhook + HMAC-SHA256 + Reply token + Push API fallback |

### 当前 plugin 平台目录（v0.13.0）

`plugins/platforms/` 下 4 个：

| 插件 | 状态 | 入站 / 出站 |
|------|------|-----------|
| `irc` | v0.12 参考实现 | stdlib asyncio TLS |
| `teams` | v0.12 引入 | Microsoft Graph API |
| `google_chat` | v0.13 引入（第 20 个平台） | Cloud Pub/Sub pull + Chat REST + per-user OAuth 附件 |
| `line` | v0.13 引入 | Line Messaging API |

每个插件目录有 `plugin.yaml`，里面声明 `requires_env` / `optional_env` 列表（带 description / prompt / url / password 元数据），`hermes config` UI 在 platform-plugin 注入器中渲染为向导。

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
- **DM 主题模式（topic mode）**（v2026.5.x 新增）：DM 论坛话题映射多个独立 session。`extra.dm_topics` 配置 `chat_id` + `topics: [{name, thread_id?}]`，启动时自动 `create_forum_topic`；新增 `/topic on|off` 指令、CASCADE 重命名、`switch_session` 期间持久化 thread 绑定、`/new` 重新绑定。源：`gateway/platforms/telegram.py:282 _dm_topics`
- **聊天白名单（群组/论坛）**：`@web3blind` 提交，v0.12.0 ([#15027](https://github.com/NousResearch/hermes-agent/pull/15027))
- **markdown 表格→分组项目符号**：v0.12.0 ([#16997](https://github.com/NousResearch/hermes-agent/pull/16997))
- **原生多图发送**：v0.12.0 跨 Telegram/Discord/Slack/Mattermost/Email/Signal 统一

### Discord
- 支持服务器和私聊
- 需要 @mention 或 DM
- 语音频道支持
- Opus 音频编码
- Slash commands 集成
- **角色权限控制**（v0.10.0）：`DISCORD_ALLOWED_ROLES` 环境变量，逗号分隔 Role ID。与 `DISCORD_ALLOWED_USERS` 是 OR 关系——用户 ID 或角色任一匹配即放行，两个都没配则所有人可用
- **channel_prompts**（v0.10.0）：按频道/话题注入不同的系统提示，也扩展到 Telegram（群组/论坛话题）、Slack、Mattermost
- **@everyone 和角色 ping 屏蔽**：`allowed_mentions` 默认阻止 bot 触发全体通知

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

### WhatsApp
- 需要 WhatsApp Bridge (Node.js)
- 群消息需要前缀触发
- 允许列表控制

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

### 与其他 Agent 框架对比

| 特性 | Hermes | OpenClaw | Claude |
|------|--------|----------|--------|
| 平台数量 | 14+ | 14+ | 1 |
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

## 相关页面

- [[gateway-session-management]] — 网关会话管理架构
- [[cron-scheduling]] — Cron 调度器由网关驱动
- [[hook-system-architecture]] — 网关事件钩子系统

## 相关文件

- `gateway/run.py` — 主循环和消息分发
- `gateway/session.py` — SessionStore
- `gateway/platforms/base.py` — 平台基类
- `gateway/delivery.py` — 消息投递
- `gateway/config.py` — 网关配置
- `gateway/platforms/` — 平台适配器目录
- `hermes_cli/gateway.py` — Gateway CLI 命令
