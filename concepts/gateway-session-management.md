---
title: Gateway Session 会话管理架构
created: 2026-04-08
updated: 2026-05-17
type: concept
tags: [architecture, module, component, gateway, session-store, multi-platform, handoff, topic]
sources: [gateway/session.py, gateway/run.py, gateway/config.py, gateway/platforms/telegram.py, hermes_cli/commands.py]
---

# Gateway Session — 网关会话管理架构

## 概述

Gateway Session 位于 `gateway/session.py`（约 1398 行），管理网关的**会话生命周期**：会话上下文追踪、消息持久化、重置策略评估、动态系统提示注入。

核心理念：**每个平台/用户/线程的组合都有独立的会话，会话知道它从哪里来、要到哪里去。**

## v0.13.0 关键升级：Session Durability

v0.13 把「网关重启 / `/update` / 源文件 reload」之后的会话恢复变成一等公民：

| 增强 | PR | 说明 |
|------|-----|------|
| **自动恢复被打断的 session** | #21192（salvage #20888） | gateway 在 agent 跑到一半被杀掉，重启后自动续上 |
| **跨重启保留 pending update prompt** | #20160 | "确认升级" 这类等待用户回应的提示不会因重启而丢失 |
| **跨重启保留 home-channel thread target** | #19271（salvage #18440） | 重启通知发到正确的子频道 / 线程 |
| **branch session 时保留 assistant metadata** | #18222 | 分支会话保留 reasoning、tool_call_id 等 |
| **`/update` 进度 + prompt 保留 thread routing** | #18193 | 升级进度不串到错误的 thread |
| **合并 queued event 时保留 document type** | #18215 | 合并消息时不丢图片 / 文件类型 |
| **transient agent 失败仍持久化 user message** | #7100 | 即使 agent 启动失败，用户消息已存进库（不丢消息） |
| **`/new` accepts optional session name** | #19637（salvage #19555，v0.13） | `/new shopping list` 直接命名新 session |

底层依赖：**atomic restart markers + Windows runtime-lock offset**（#17842, PR #18179）+ **git HEAD SHA 用作 stale-code 检测（不再用 file mtime）**（#19740）。

## 架构原理

### 核心数据模型

```text
SessionSource (消息来源)
    ↓
SessionContext (完整会话上下文)
    ↓
SessionEntry (会话存储条目)
    ↓
SessionStore (会话存储管理器)
```

### SessionSource — 消息来源描述

```python
@dataclass
class SessionSource:
    platform: Platform           # telegram, discord, slack, whatsapp...
    chat_id: str                 # 聊天 ID
    chat_name: Optional[str]     # 聊天名称
    chat_type: str               # "dm", "group", "channel", "thread"
    user_id: Optional[str]       # 用户 ID
    user_name: Optional[str]     # 用户名称
    thread_id: Optional[str]     # 线程/话题 ID
    chat_topic: Optional[str]    # 频道主题
    user_id_alt: Optional[str]   # Signal UUID 等备用 ID
    chat_id_alt: Optional[str]   # Signal 群内部 ID
    is_bot: bool                 # 消息作者是否为 bot/webhook（Discord）
    guild_id: Optional[str]      # Discord guild / Slack workspace / Matrix server 作用域
```

**多平台适配**：不同平台使用不同的 ID 格式（Telegram 用数字 ID，Signal 用 UUID + 群内部 ID），SessionSource 统一抽象。

### SessionKey 构建规则

```python
def build_session_key(source, group_sessions_per_user=True, thread_sessions_per_user=False):
    """
    DM 会话:
    → agent:main:{platform}:dm:{chat_id}
    → agent:main:{platform}:dm:{chat_id}:{thread_id}  (带线程)
    
    群组会话:
    → agent:main:{platform}:group:{chat_id}:{user_id}  (按用户隔离)
    → agent:main:{platform}:group:{chat_id}            (共享会话)
    
    线程会话:
    → agent:main:{platform}:thread:{chat_id}:{thread_id}  (默认共享)
    → agent:main:{platform}:thread:{chat_id}:{thread_id}:{user_id}  (per-user)
    """
```

**设计考量**：
- DM 会话：按聊天隔离，确保私人对话独立
- 群组会话：默认按用户隔离（每个用户有自己的对话）
- 线程会话：默认共享（所有参与者看到同一对话），可通过 `thread_sessions_per_user` 启用隔离

### PII 脱敏

```python
_PHONE_RE = re.compile(r"^\+?\d[\d\-\s]{6,}$")

def _hash_id(value: str) -> str:
    """确定性 12 字符十六进制哈希"""
    return hashlib.sha256(value.encode()).hexdigest()[:12]

def _hash_sender_id(value: str) -> str:
    return f"user_{_hash_id(value)}"

def _hash_chat_id(value: str) -> str:
    """保留平台前缀: telegram:12345 → telegram:<hash>"""
    colon = value.find(":")
    if colon > 0:
        return f"{value[:colon]}:{_hash_id(value[colon+1:])}"
    return _hash_id(value)
```

**Discord 例外**：Discord 使用 `<@user_id>` 提及系统，LLM 需要真实 ID 才能 @ 用户，因此 Discord 不在 `_PII_SAFE_PLATFORMS` 中。

### SessionContext — 动态系统提示注入

```python
def build_session_context_prompt(context, redact_pii=False):
    """
    生成注入到系统提示的上下文信息:
    
    ## Current Session Context
    **Source:** Telegram (DM with lnisang La)
    **User:** lnisang La
    **Connected Platforms:** local, telegram: Connected ✓
    
    **Delivery options for scheduled tasks:**
    - "origin" → Back to this chat (lnisang La)
    - "local" → Save to local files only
    - "telegram" → Home channel (...)
    """
```

**平台特定行为提示**：

```python
if platform == SLACK:
    "You do NOT have access to Slack-specific APIs..."
elif platform == DISCORD:
    "You do NOT have access to Discord-specific APIs..."
```

防止 Agent 承诺执行无法完成的操作。

### SessionStore — 会话存储管理器

```python
class SessionStore:
    def __init__(self, sessions_dir, config):
        # 优先使用 SQLite (SessionDB)
        # 回退到 JSONL 文件
        self._db = SessionDB()  # 如果可用
```

**双存储策略**：
1. **SQLite**（优先）：通过 `hermes_state.SessionDB`，支持 FTS5 全文搜索
2. **JSONL**（回退）：简单的 JSON 文件存储

### 会话重置策略

```python
def _is_session_expired(self, entry):
    """
    检查会话是否过期:
    1. 检查是否有活跃后台进程（有则不过期）
    2. 获取平台/聊天类型的重置策略
    3. 检查 idle 超时或 daily 重置
    """
```

**后台过期监控**：

```python
# 当会话过期时:
entry.was_auto_reset = True
entry.auto_reset_reason = "idle"  # 或 "daily"
entry.reset_had_activity = bool(entry.total_tokens > 0)
```

下次消息到达时，网关注入通知：

```
"⚠️ Previous session expired (idle for 24h). Starting fresh conversation."
```

### Token 追踪

```python
@dataclass
class SessionEntry:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    cost_status: str = "unknown"
    last_prompt_tokens: int = 0  # 用于压缩预检查
    memory_flushed: bool = False  # 内存刷新标记（持久化）
```

### 原子保存

```python
def _save(self):
    """使用 tempfile + os.replace 原子写入 sessions.json"""
    fd, tmp_path = tempfile.mkstemp(dir=sessions_dir, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, sessions_file)  # 原子替换
```

**为什么原子写入**：防止网关崩溃时写入不完整的 sessions.json。

## 设计优越性

### 会话隔离的灵活性

| 场景 | 默认行为 | 可配置 |
|---|---|---|
| DM | 按聊天隔离 | 不可改 |
| 群组 | 按用户隔离 | group_sessions_per_user=False → 共享 |
| 线程 | 共享 | thread_sessions_per_user=True → 按用户隔离 |

### 对比简单会话管理

| 维度 | 简单方案 | Gateway Session |
|---|---|---|
| 多平台 | 需要手动处理 | SessionSource 统一抽象 |
| 会话隔离 | 固定策略 | 可配置（per-user / shared）|
| PII 保护 | 无 | 自动哈希脱敏 |
| 上下文注入 | 无 | 动态系统提示 |
| 重置策略 | 无 | idle/daily 自动重置 |
| 成本追踪 | 无 | token 用量 + 成本估算 |
| 持久化 | 内存 | SQLite + JSON 双存储 |

## 配置与操作

### 会话重置策略

```yaml
# config.yaml
gateway:
  reset_policy:
    dm: idle:24h        # DM 24 小时无活动重置
    group: daily        # 群组每日重置
    thread: idle:12h    # 线程 12 小时无活动重置
```

### 会话隔离

```yaml
gateway:
  group_sessions_per_user: true    # 群组中每个用户独立会话
  thread_sessions_per_user: false  # 线程中共享会话（默认）
```

### 查看活跃会话

```python
# 通过 gateway 内部 API
store._entries  # Dict[session_key, SessionEntry]
```

## API Server — X-Hermes-Session-Key（v2026.5+）

`gateway/platforms/api_server.py` 提供 OpenAI 兼容端点（`/v1/chat/completions`、`/v1/responses`、`/v1/runs`）。OpenAI 协议**默认无状态**——同一 channel 的多次请求互不关联，长期记忆 provider（Honcho、Hindsight）无法把它们归到同一个用户。

为此引入 **`X-Hermes-Session-Key`** header，提供**稳定 per-channel 标识**，scope 长期记忆，独立于 transcript-scoped `X-Hermes-Session-Id`：

```text
            X-Hermes-Session-Id      X-Hermes-Session-Key
            (transcript)             (channel)
            ┌───────────────┐        ┌───────────────┐
/new ──>    │  rotates      │        │   stable      │
            │  per /new     │        │   per channel │
            │  per agent    │        │   per user    │
            └───────────────┘        └───────────────┘
              ↓                        ↓
       run_agent / SessionDB      Honcho.resolve_session_name
                                  Hindsight document_id
```

匹配原生 gateway 的 `session_key` / `session_id` 拆分语义：**一个 channel 一个稳定 key，多个 transcript 在 `/new` 时旋转**。

### `_parse_session_key_header`（line 714）

| 验证 | 限制 |
|------|------|
| 需 API-key 启用 | 否则 `X-Hermes-Session-Key` 被 reject |
| 控制字符 sanitize | 拒非可打印字符 |
| 长度上限 | 256 chars |

### 端点 honor

`/v1/chat/completions`、`/v1/responses`、`/v1/runs` 三处 `_create_agent` / `_run_agent` 接受 `gateway_session_key` 参数并 pass 给 `AIAgent(gateway_session_key=...)`；JSON / SSE 响应 echo header；`/v1/capabilities` 通告 `session_key_header: "X-Hermes-Session-Key"` 让 client feature-detect。

## Agent 运行中收到新消息的处理（gateway/run.py line 1920+）

当同一 session 的 agent 正在执行时，用户发新消息的处理逻辑：

```text
同一 session 收到新消息
    │
    ├── /stop         → 硬中断：interrupt + 强制清除 _running_agents 锁，立即解锁 session
    ├── /reset /new   → 中断 + 清空 pending queue（防旧文本重放 #2170）→ 执行 reset
    ├── /queue <text> → 排队：不打断，等当前轮次结束后作为下一轮输入
    ├── /status       → 不打断，直接返回当前状态
    ├── /model        → 拒绝："Agent is running — wait or /stop first"
    ├── /approve /deny→ 绕过中断，直接路由到审批处理器（agent 阻塞在 approval event 上）
    ├── 照片          → 排队不打断，多张照片自动合并到同一个 pending event
    └── 普通文本      → interrupt(event.text) + 文本追加到 _pending_messages
```

### 普通文本打断的完整流程

```python
# gateway/run.py line 2033-2038
running_agent.interrupt(event.text)      # 设置中断信号
if _quick_key in self._pending_messages:
    self._pending_messages[_quick_key] += "\n" + event.text  # 追加
else:
    self._pending_messages[_quick_key] = event.text          # 新建
```

agent 在下一个检查点发现中断信号 → 停止当前轮次 → pending 文本作为新一轮输入继续处理。

### 跨 Session 完全隔离

`_running_agents` 的 key 是 `_quick_key`（由 platform + user_id + chat_id 组成），不同 session 有独立的 key：

| 场景 | 是否打断 | 原因 |
|------|:---:|------|
| 同一聊天窗口发普通文本 | ✅ | interrupt() 打断当前 agent |
| 同一聊天窗口发 /queue | ❌ | 排队等当前完成 |
| 同一聊天窗口发照片 | ❌ | 自动排队合并 |
| 不同聊天窗口 / 不同用户 | ❌ | 不同 _quick_key，独立线程并行 |

不同 session 的 agent 通过 `run_in_executor` 在线程池中执行，真正并行。

## v0.12.0+ 新增能力（2026-04-30 ~ 2026-05-13）

### `/handoff` — 跨平台 session 转移（878611a + 00ce5f0 + 373c4d6）

`hermes_cli/commands.py` 注册 `CommandDef("handoff", ..., "Session", args_hint="<platform>", cli_only=True)`，把当前 CLI session 实时转交给一个运行中的 messaging platform（Telegram、Discord 等）。

```text
[CLI session 跑在终端] ─/handoff telegram──► state.db.handoff_state='pending'
                                              ↓
                          gateway _handoff_watcher() 后台轮询（2s）
                                              ↓
                          claim → 重新绑定到 platform adapter → 投递 handoff notice
                                              ↓
                                标记 completed / failed
```

**核心源码** `gateway/run.py:3708-3795`：
- `_handoff_watcher(interval=2.0)`：网关启动时 `asyncio.create_task`，循环扫描 `state.db` 里 `handoff_state='pending'` 的 session
- `_session_db.list_pending_handoffs()` → `claim_handoff(session_id)` → `_process_handoff(row)` → `complete_handoff` / `fail_handoff(session_id, error)`
- 自动等待目标平台 adapter 就绪后再 dispatch handoff notice，避免空投递

**设计点**：handoff 是**实时迁移**而不仅仅是发"我换平台了"通知——CLI 这边的 working session（消息历史、内存、技能、cron）原样接续到 Telegram 等任意 messaging 端，用户可以从 mac CLI 切到手机继续聊。

### Telegram `/topic` — DM 内多 session 切换（d6615d8 + d35efb9 + 1381c89 + a7683d0）

私聊里通过 Telegram forum topic 机制实现"一个 DM 内多个并行 session"——每个 topic 一个 session，互不污染。

```text
私聊                             /topic <name>           Hermes 创建 forum topic
  └── topic A: session 1   ─────────────────► chat_id + message_thread_id 持久化
  └── topic B: session 2                       到 source.thread_id
  └── topic C: session 3
```

**核心源码** `gateway/platforms/telegram.py:419-422 + 514-585`：

```python
# DM Topics: map of topic_name -> message_thread_id (populated at startup)
self._dm_topics: Dict[str, int] = {}
# DM Topics config from extra.dm_topics
self._dm_topics_config: List[Dict[str, Any]] = self.config.extra.get("dm_topics", [])
```

routing 走 `_metadata_direct_messages_topic_id()` 和 `telegram_dm_topic_reply_fallback` 标记：

- 真正的 Bot API "Direct Messages topic" 走 `direct_messages_topic_id` metadata
- Hermes 自创建的 private-chat topic lane 标记 `telegram_dm_topic_reply_fallback`，走 private topic
- Supergroup forum topics 用 `message_thread_id`
- **General topic 特殊处理**：发送时拒绝 `message_thread_id=1`，必须 omit，否则消息显示成 General 里的"reply to bubble"

**用户控制**：
- `/topic <name>` 切换/创建 topic（auth gate 验证）
- `/topic off` 退出 topic mode 回到主 session
- `/topic help` 用法
- DM topic 绑定通过 `switch_session` 持久化，`/new` 时自动 rebind
- CASCADE 删除：session 删则关联 topic 也清理
- rename guard：防止 topic 改名导致 session 找不到
- screenshot debounce：截图通知去抖

详见 `tests/.../telegram_topic_*.py`。

## 与其他系统的关系

- [[messaging-gateway-architecture]] — Session 是网关的核心组件
- [[multi-agent-architecture]] — 中断传播到子 agent（`_active_children`）
- [[session-search-and-sessiondb]] — SQLite SessionDB 提供 FTS5 搜索
- [[cron-scheduling]] — 会话 origin 用于 cron 投递路由
- [[memory-system-architecture]] — 过期会话触发 memory flush
