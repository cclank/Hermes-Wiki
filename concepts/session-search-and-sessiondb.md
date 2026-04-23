---
title: Session Search and SessionDB
created: 2026-04-07
updated: 2026-04-18
type: concept
tags: [session-search, session-store, memory, architecture]
sources: [hermes-agent 源码分析 2026-04-07]
---

# 会话搜索与 SessionDB

## 概述

`session_search` 提供**跨会话的对话回忆能力**，使用 SQLite FTS5 全文搜索 + LLM 摘要生成。

## SessionDB

```python
# hermes_state.py
class SessionDB:
    """SQLite 会话存储，支持 FTS5 搜索"""
    
    def __init__(self, db_path: str):
        # 创建会话表和 FTS5 虚拟表
        ...
    
    def save_session(self, session_id, messages, ...):
        """保存会话到数据库"""
    
    def search_sessions(self, query, ...):
        """FTS5 全文搜索"""
```

## FTS5 搜索

使用 SQLite 的 FTS5 扩展实现高效全文搜索：

```sql
-- FTS5 虚拟表（索引 messages 表）
CREATE VIRTUAL TABLE messages_fts USING fts5(
    content,
    content=messages,
    content_rowid=id
);

-- 搜索查询
SELECT * FROM messages_fts WHERE messages_fts MATCH 'elevenlabs OR baseten OR funding';
```

搜索语法支持：
- **关键词 OR** — `elevenlabs OR baseten`
- **短语匹配** — `"docker networking"`
- **布尔逻辑** — `python NOT java`
- **前缀匹配** — `deploy*`

## Session Search 工具

```python
def session_search(query: str, role_filter: str = None, limit: int = 3):
    """
    搜索过去的对话会话
    
    两种模式：
    1. 无 query — 浏览最近的会话（标题、预览、时间戳）
    2. 有 query — 关键词搜索 + LLM 摘要生成
    """
```

### 模式 1: 浏览最近会话

```text
调用无参数 → 返回最近会话列表：
- 会话标题
- 内容预览
- 时间戳
零 LLM 成本，即时返回
```

### 模式 2: 关键词搜索

```text
调用带 query → FTS5 搜索 → LLM 生成摘要：
- 搜索匹配的消息
- LLM 总结会话内容
- 返回结构化的摘要
```

## 搜索建议

```text
搜索时使用 OR 连接关键词以获得最佳结果：
  elevenlabs OR baseten OR funding

FTS5 默认使用 AND，会漏掉只提到部分关键词的会话。
如果广泛 OR 查询没有结果，尝试并行搜索单个关键词。
```

## 与 Memory 的区别

| 维度 | Memory | Session Search |
|------|--------|----------------|
| **内容** | 稳定事实、偏好 | 完整的对话历史 |
| **容量** | 有限（~3500 字符） | 无限制（SQLite） |
| **检索** | 每轮自动注入 | 按需搜索 |
| **格式** | 条目列表 | 结构化对话 |
| **用途** | 核心行为指导 | 回忆上下文 |

## 使用场景

```text
当用户说：
- "我们之前做过这个" → session_search
- "还记得什么时候..." → session_search
- "上次我们..." → session_search
- "我们关于 X 做了什么？" → session_search

当你怀疑：
- 相关上下文存在于过去的会话中 → session_search
- 不要让用户重复自己 → session_search
```

## 数据流

```text
会话结束
  ↓
SessionDB.save_session()
  ↓
写入 SQLite + FTS5 索引
  ↓
用户发起搜索
  ↓
FTS5 全文搜索
  ↓
LLM 生成摘要
  ↓
返回结构化结果
```

## Session 删除与修剪

`delete_session()` 和 `prune_sessions()` 采用 **orphan 策略**而非级联删除：

- 删除父 session 时，子 session 的 `parent_session_id` 被置为 `NULL`（孤立），而非一并删除
- 压缩分裂产生的子 session 在父 session 被清理后仍然可搜索
- `prune_sessions(older_than_days=90)` 只清理已结束的 session，活跃 session 不受影响

设计意图：保护历史数据完整性，避免清理操作误删有价值的对话记录。

### 启动时自动修剪 + VACUUM（v2026.4.18+）

`state.db` 之前无限增长——一个重度用户（gateway + cron）报告 384MB / 982 sessions / 68K 消息导致性能下降，手动 `hermes sessions prune --older-than 7` + `VACUUM` 后降到 43MB。v2026.4.18+ 在启动时自动执行：

```python
# hermes_state.py
class SessionDB:
    def vacuum(self): ...

    def maybe_auto_prune_and_vacuum(
        self,
        min_interval_hours: int = 168,   # 默认每周一次
        older_than_days: int = 180,
    ) -> None:
        """幂等：通过 state_meta 表记录上次运行时间，跨进程同一 HERMES_HOME 只执行一次"""
```

- 新增 `state_meta` key/value 表存储上次运行时间戳
- 同一 `HERMES_HOME` 下所有 Hermes 进程共享锁，`min_interval_hours` 内只执行一次
- 永不抛异常——清理失败只记日志不影响启动

## 更新 `/usage` 显示账户限制（v2026.4.18+）

`/usage` 命令在原有 token 表格下追加**账户级配额信息**（provider 侧返回的剩余额度、周期、限流）：

- CLI：在 1-worker `ThreadPoolExecutor`（10s 超时）里 fetch，慢 provider 不会卡 prompt
- Gateway：通过 `asyncio.to_thread` fetch；无 agent 驻留时从 `billing_provider` / `billing_base_url` 持久化字段解析 provider
- 新模块 `agent/account_usage.py` 提供 per-provider 账户限制抽象

## 相关页面

- [[gateway-session-management]] — 网关会话管理（SessionStore 使用 SessionDB）
- [[cli-architecture]] — CLI 中的会话管理与搜索命令
- [[skills-and-memory-interaction]] — Session Search 作为第三种持久化机制

## 相关文件

- `hermes_state.py` — SessionDB 实现
- `tools/session_search_tool.py` — Session Search 工具
- `agent/trajectory.py` — 轨迹保存辅助
