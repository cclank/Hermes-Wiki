---
title: Gateway Session 会话管理架构
created: 2026-04-08
updated: 2026-04-08
type: concept
tags: [architecture, module, component, gateway, session-store, multi-platform]
sources: [gateway/session.py, gateway/config.py]
---

# Gateway Session — 网关会话管理架构

## 概述

Gateway Session 位于 `gateway/session.py`（44KB/1081行），管理网关的**会话生命周期**：会话上下文追踪、消息持久化、重置策略评估、动态系统提示注入。

核心理念：**每个平台/用户/线程的组合都有独立的会话，会话知道它从哪里来、要到哪里去。**

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

## 与其他系统的关系

- [[messaging-gateway-architecture]] — Session 是网关的核心组件
- [[session-search-and-sessiondb]] — SQLite SessionDB 提供 FTS5 搜索
- [[cron-scheduling]] — 会话 origin 用于 cron 投递路由
- [[memory-system-architecture]] — 过期会话触发 memory flush
