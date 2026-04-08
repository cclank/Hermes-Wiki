---
title: Messaging Gateway Architecture
created: 2026-04-07
updated: 2026-04-07
type: concept
tags: [gateway, architecture, module, telegram, discord, messaging]
sources: [raw/articles/code-analysis-2026-04-07.md]
---

# Messaging Gateway Architecture

## Overview

Gateway 是 Hermes Agent 的**统一消息网关**，支持 14+ 消息平台，从单一进程管理所有平台的连接和消息分发。

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
    ├── homeassistant.py
    ├── webhook.py
    ├── api_server.py
    └── base.py
```

## 平台适配器基类

```python
# gateway/platforms/base.py
class BasePlatform:
    def __init__(self, config):
        ...
    
    async def start(self):
        """启动平台连接"""
    
    async def stop(self):
        """停止平台连接"""
    
    async def send_message(self, chat_id, text, ...):
        """发送消息"""
    
    async def handle_message(self, event):
        """处理接收消息"""
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

## Session 管理

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

## Gateway 服务管理

### Linux (systemd)

```bash
hermes gateway start    # 启动服务
hermes gateway stop     # 停止服务
hermes gateway status   # 检查状态
```

服务单元：`hermes-gateway.service` 或 `hermes-gateway-<profile>.service`

### macOS (launchd)

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

### Discord
- 支持服务器和私聊
- 需要 @mention 或 DM
- 语音频道支持
- Opus 音频编码
- Slash commands 集成

### WhatsApp
- 需要 WhatsApp Bridge (Node.js)
- 群消息需要前缀触发
- 允许列表控制

### Home Assistant
- 智能家居事件监控
- 设备控制
- 自动化触发

## 相关文件

- `gateway/run.py` — 主循环和消息分发
- `gateway/session.py` — SessionStore
- `gateway/platforms/base.py` — 平台基类
- `gateway/delivery.py` — 消息投递
- `gateway/config.py` — 网关配置
- `hermes_cli/gateway.py` — Gateway CLI 命令
