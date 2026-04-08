---
title: Gateway 多平台适配架构
created: 2026-04-07
updated: 2026-04-07
type: concept
tags: [architecture, gateway, multi-platform, messaging]
sources: [raw/articles/code-analysis-2026-04-07.md]
---

# Gateway 多平台适配架构

## 设计原理

Hermes 支持 14+ 消息平台，使用**统一网关 + 平台适配器**模式。单一 Gateway 进程管理所有平台连接，共享 Agent 实例和会话状态。

## 平台支持

| 平台 | 类型 | 特性 |
|------|------|------|
| Telegram | Bot API | 群组/私聊、语音转录、贴纸 |
| Discord | Bot API | 服务器/私聊、语音频道、Slash Commands |
| Slack | Bot API | Workspace 集成、Thread 支持 |
| WhatsApp | Bridge (Node.js) | 群组/私聊、允许列表 |
| Signal | Bot API | 加密消息 |
| Email | IMAP/SMTP | 邮件交互 |
| SMS | Twilio | 短信，字符限制 |
| Home Assistant | WebSocket | 智能家居事件 |
| Matrix | E2E 加密 | 去中心化消息 |
| Mattermost | Bot API | 自托管团队消息 |
| 钉钉 | Stream | 企业消息 |
| 飞书/Lark | Stream | 企业消息 |
| 企业微信 | Stream | 企业微信消息 |
| Webhook | HTTP | 外部事件接收 |

## 适配器基类

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
平台适配器接收 (Telegram/Discord/...)
  ↓
创建 MessageEvent
  ↓
GatewayRunner.process_event(event)
  ↓
解析斜杠命令（如果有）
  ↓
查找或创建 Session
  ↓
调用 AIAgent.run_conversation()
  ↓
获取响应
  ↓
通过平台适配器发送回复
```

## 会话管理

```python
# gateway/session.py
class SessionStore:
    """会话持久化存储"""
    
    def get_or_create_session(self, chat_id: str, platform: str) -> Session:
        """获取或创建会话"""
        session_key = f"{platform}:{chat_id}"
        if session_key not in self.sessions:
            self.sessions[session_key] = Session(
                session_id=str(uuid.uuid4()),
                chat_id=chat_id,
                platform=platform,
            )
        return self.sessions[session_key]
    
    def save_session(self, session_id: str, messages: list):
        """保存会话到 SQLite"""
        self.session_db.save_session(session_id, messages)
```

## DM 配对

```python
# 允许的用戶
GATEWAY_ALLOWED_USERS=telegram:123456789,discord:987654321

# 未授权用户静默忽略
def _is_user_allowed(user_id: str, platform: str) -> bool:
    allowed = os.getenv("GATEWAY_ALLOWED_USERS", "").split(",")
    return f"{platform}:{user_id}" in allowed
```

## 媒体处理

```
用户发送图片/文件
  ↓
平台适配器下载到临时目录
  ↓
传递给 Agent（vision_analyze 或文件处理）
  ↓
Agent 响应包含 MEDIA: 路径
  ↓
提取本地文件
  ↓
通过平台原生方式发送
```

## 服务管理

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

## 优越性分析

### 与其他 Agent 框架对比

| 特性 | Hermes | OpenClaw | Claude |
|------|--------|----------|--------|
| 平台数量 | ✅ 14+ | ✅ 14+ | ❌ 1 |
| 统一网关 | ✅ 单一进程 | ✅ | N/A |
| 会话共享 | ✅ 跨平台 | ✅ | N/A |
| 语音转录 | ✅ Telegram/Discord | ✅ | N/A |
| 群组支持 | ✅ 多平台 | ✅ | N/A |
| 服务管理 | ✅ systemd/launchd | ✅ | N/A |

## 相关文件

- `gateway/run.py` — 网关主循环
- `gateway/session.py` — 会话管理
- `gateway/platforms/` — 平台适配器
- `gateway/delivery.py` — 消息投递
