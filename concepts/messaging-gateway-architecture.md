---
title: Messaging Gateway Architecture
created: 2026-04-07
updated: 2026-05-02
type: concept
tags: [gateway, architecture, module, telegram, discord, messaging, qq, proxy, plugin-platform]
sources: [gateway/run.py, gateway/platforms/, gateway/platform_registry.py, plugins/platforms/, hermes_cli/config.py]
---

# 消息网关架构

## 概述

Gateway 是 Hermes Agent 的**统一消息网关**，支持 19 个消息平台（v0.12.0 起，含两个**插件交付**平台 — IRC + Microsoft Teams），从单一进程管理所有平台的连接和消息分发。

> **v0.12.0 (2026-04-30)**：Microsoft Teams 第 19 个平台，作为**插件**交付，依赖 v2026.4.23 引入的 `gateway/platform_registry.py:PlatformRegistry`。Slack 大量加固（ephemeral ack + per-user 隔离 + 保留 slash 屏蔽）；gateway 自动重启在源文件变更（`f99676e`）；systemd 无限重试 + backoff（`f98b5d0`）；lazy session creation（`c5b4c48`）—— 不发消息时不再产生幽灵 session。详见 [[2026-05-02-update]]。

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

| 平台 | 类型 | 特性 |
|------|------|------|
| Telegram | Bot API | 群组/私聊、语音转录、贴纸、代理支持、链接预览控制 |
| Discord | Bot API | 服务器/私聊、语音频道、Slash Commands、角色权限控制、channel_prompts |
| Slack | Bot API | Workspace 集成、Thread 支持 |
| WhatsApp | Bridge (Node.js) | 群组/私聊、允许列表 |
| Signal | Bot API | 加密消息，原生格式化、reply 引用、reactions（v2026.4.23+） |
| Email | IMAP/SMTP | 邮件交互 |
| SMS | Twilio | 短信，字符限制 |
| Home Assistant | WebSocket | 智能家居事件 |
| Matrix | E2E 加密 | 去中心化消息 |
| Mattermost | Bot API | 自托管团队消息 |
| 钉钉 | Stream | 企业消息，QR 扫码认证，require_mention + allowed_users 权限控制 |
| 飞书/Lark | Stream | 企业消息 |
| 企业微信 | Stream | 企业微信消息 |
| BlueBubbles | REST + Webhook | iMessage（macOS），tapback、已读回执 |
| 微信/WeChat | iLink Bot API | 长轮询收消息，AES-128-ECB 媒体加密，QR 登录 |
| QQ Bot | Official API v2 | WebSocket 入站(C2C/群/频道/DM) + REST 出站,语音转录(腾讯 ASR),allowlist + DM 配对 |
| Webhook | HTTP | 外部事件接收 |
| **腾讯元宝 Yuanbao** | API | 原生文本+媒体投递，sticker 支持（v2026.4.23+） |
| **IRC**（插件） | TLS asyncio | 零外部依赖，TLS、PING/PONG、nick collision、NickServ、频道寻址（v2026.4.23+，参考实现） |

## 平台适配器插件化（v2026.4.23+）

`gateway/platform_registry.py` 引入 `PlatformRegistry` 单例 + `PlatformEntry` dataclass，让任何人都可以把新平台（IRC、Viber、Line 等）以**纯插件**形式接入，无需改 gateway 核心代码。

```python
# 插件注册入口
def register(ctx):
    ctx.register_platform(
        name="irc",
        label="IRC",
        adapter_factory=create_irc_adapter,
        check_fn=check_irc_available,
        validate_config=validate_irc_config,
        required_env=["IRC_NICK", "IRC_PASS"],
        install_hint="pip install ...",
    )
```

### 关键改造点

| 模块 | 改造 |
|------|------|
| `Platform` enum | `_missing_()` 接受未知字符串，创建缓存的 pseudo-member（`Platform('irc') is Platform('irc')` 永真） |
| `GatewayConfig.from_dict` | 解析 config.yaml 里的插件平台名，不再拒绝未知平台 |
| `_create_adapter()` in `gateway/run.py` | 先查 registry，未命中再 fall through 到内置 if/elif 链 |
| `get_connected_platforms()` | 把未知平台委托给 registry |
| `PluginContext.register_platform()` | 镜像 `register_tool()` / `register_hook()` 模式 |

### IRC 参考实现

`plugins/platforms/irc/` 是首个插件平台：
- 全 async（`asyncio` stdlib，零外部依赖）
- TLS 连接、PING/PONG 心跳、nick 冲突重命名、NickServ 自动鉴权
- 频道消息要求 `nick: msg` 寻址，DM 全部派发
- 输出 Markdown 自动剥离（IRC 不支持），消息分片（IRC 长度限制）
- 交互式 `setup` 向导（v2026.4.23+）

### 平台插件 12 个集成点全覆盖

`feat: complete plugin platform parity` (2e20f6ae2) + `feat: final platform plugin parity` (e464cde58) 让插件平台和内置平台行为一致：
- webhook 投递、PLATFORM_HINTS、`get_connected_platforms`、cron 投递、动态 toolset 生成、setup wizard 等
- bundled 插件平台（如 IRC）启动时自动加载（`feat(plugins): bundled platform plugins auto-load by default`）

## 平台适配器基类

```python
# gateway/platforms/base.py
class BasePlatform:
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

## 平台特定功能

### Telegram
- 支持群组和私聊
- 群消息需要 @mention 触发
- 语音消息转录
- 贴纸支持
- 话题/线程支持
- **代理支持**（v0.10.0）：`TELEGRAM_PROXY` 环境变量或 `config.yaml` 中 `proxy_url`
- **链接预览控制**（v0.10.0）：`config.yaml` 中 `telegram.disable_link_preview` 关闭消息链接预览

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
