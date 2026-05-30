---
title: Session Search and SessionDB
created: 2026-04-07
updated: 2026-05-30
type: concept
tags: [session-search, session-store, memory, architecture, state-db]
sources: [hermes_state.py, tools/session_search_tool.py, gateway/run.py]
---

# 会话搜索与 SessionDB

> **2026-05-30 增量（hermes-agent `5921d6678`，fixes #34850）— mid-session model 持久化**：
>
> 用户 `/model` mid-session 切换时，gateway 更新 in-memory agent 和 session override，但 DB 从未更新 —— `update_token_counts()` 里 `COALESCE(model, ?)` 只填 NULL，所以 dashboard 永远显示原始 model。
>
> 修复（`794519c6a fix(state): persist mid-session model switch to database`）：
>
> - 新增 `hermes_state.py:968-980 SessionDB.update_session_model(session_id, model)` —— 用 `UPDATE sessions SET model = ?` **无条件覆盖**，区别于 `update_token_counts` 的 `COALESCE` only-fill-NULL 语义
> - `gateway/run.py` +29 行：interactive picker 与直接 `/model` 命令两条路径都调用
> - 回归测试 `e1945ff69 test(state): cover update_session_model overwrite + getattr-guard text path`
>
> 详见 [[2026-05-30-update#9-session-model-中途切换持久化fixes-34850]]。

> **2026-05-29 增量（hermes-agent `689ef5e2`）**：
>
> `perf(state): merge FTS5 segments on VACUUM + add 'hermes sessions optimize'`（commit `38695254f`）落地索引维护能力：
>
> - `hermes_state.py:3267` 新增 `def optimize_fts(self) -> int:` —— 合并 FTS5 段（`INSERT INTO ...(fts) VALUES('merge', N)` 增量合并），缩减索引、加速查询；返回索引计数（`refactor(state): return FTS index count from vacuum()`，`904c0b479`）
> - `hermes_state.py:3306` 新增 `def vacuum(self) -> int:` —— 先 `optimize_fts()` 再 `VACUUM`，把空间还给 OS
> - CLI 新增 `hermes sessions optimize`（`hermes_cli/main.py:13414` help、`:13596-13598` 执行入口）
> - 可靠性：瞬时 EIO 时不再把 WAL 静默降级为 DELETE（`fix(state): never silently downgrade WAL to DELETE on transient EIO`，`5c49cd0ed`）
>
> 与既有 `vacuum()` / `maybe_auto_prune_and_vacuum()`（见下文 "启动时自动修剪 + VACUUM"）协作：本次的 `optimize_fts()` 是真正合并 FTS5 段（VACUUM 本身不动 FTS5），`vacuum()` 把两步连起来。详见 [[2026-05-29-update#6-sessiondb-fts5-段合并--hermes-sessions-optimize]]。

## 概述

`session_search` 提供**跨会话的对话回忆能力**，使用 SQLite FTS5 全文搜索。该工具经 #27590 重写为 **single-shape 工具**，**不做任何 LLM 调用** — 每种模式都直接从 DB 返回真实消息（`tools/session_search_tool.py:23`）。

## v0.13.0+ 起：SQLite `state.db` 是网关消息的**唯一权威**

post-v0.14.0 一系列 commit 把 gateway 历史上的双存储路径砍掉了：

```
33a3cf532  docs(sessions): state.db is canonical for gateway messages
9d793e8e5  docs(session-log): state.db is canonical; ~/.hermes/sessions/ is legacy
b4b118c20  refactor(gateway): drop _append_to_jsonl from mirror
351fdcc6e  refactor(gateway): stop writing JSONL in append_to_transcript / rewrite_transcript
971cfaa38  refactor(yuanbao): migrate recall to load_transcript()
024a8e3ee  refactor(gateway): drop JSONL fallback in load_transcript
1d27be0ff  test(gateway): pin SQLite-only load_transcript behaviour
ce2678518  refactor(session-log): delete _save_session_log and all callers
eeb747de2  feat(sessions): opt-in per-session JSON snapshot writer
```

含义：

- **网关消息 transcript 的权威来源**永远是 `~/.hermes/state.db`。
- `~/.hermes/sessions/*.json` 现在是 **legacy**，hermes **不再主动写**。已有目录不会被自动清理。
- 如果还想拿 JSON 快照（外部工具消费），打开**opt-in per-session JSON snapshot writer**。
- `platform_message_id` 现在持久化到 `state.db`（commit `31a0100`），yuanbao 等平台用此精确按消息 ID 召回。

> 这是 v2026.4 一直在推进的 cleanup：之前每次写消息都要 transcribe 到 SQLite + JSONL 两份，存在不一致风险（JSONL truncate / 锁竞争）。现在只有一处真理来源。

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

使用 SQLite 的 FTS5 扩展实现高效全文搜索。Hermes 维护**两张** FTS5 虚拟表（`hermes_state.py`）：

```sql
-- 主表（unicode61 tokenizer，覆盖 content + tool_name + tool_calls）
CREATE VIRTUAL TABLE messages_fts USING fts5(...);

-- 触发器索引内容：
-- COALESCE(content, '') || ' ' || COALESCE(tool_name, '') || ' ' || COALESCE(tool_calls, '')
```

```sql
-- Trigram 表（v2026.4.30+，CJK / 泰语等 substring 查询）
CREATE VIRTUAL TABLE messages_fts_trigram USING fts5(
    content,
    tokenize='trigram'
);
```

搜索语法支持：
- **关键词 OR** — `elevenlabs OR baseten`
- **短语匹配** — `"docker networking"`
- **布尔逻辑** — `python NOT java`
- **前缀匹配** — `deploy*`

### Trigram FTS5 索引（CJK 搜索，v2026.5.x）

默认的 `unicode61` tokenizer 会把中日韩文本切成**单字** token，破坏短语/子串匹配。`hermes_state.py` 新增 `messages_fts_trigram` 虚拟表（`FTS_TRIGRAM_SQL`，`tokenize='trigram'`），用重叠的 3 字节序列建索引，使**任意脚本**的子串查询都能命中——取代了原来对 CJK 的 `LIKE` 回退。

```sql
CREATE VIRTUAL TABLE messages_fts_trigram USING fts5(
    content, ..., tokenize='trigram'
);
```

schema 迁移 **v10** 建表并回填存量行，**v11** 重新索引以覆盖 `tool_name` / `tool_calls`。配套 insert/delete/update 触发器镜像 `messages` 表。

## Session Search 工具

`session_search` 是一个 **single-shape 工具**，没有显式的 `mode` 参数 —— 三种模式由传入的参数推断（`tools/session_search_tool.py:378-390`）：

```python
def session_search(
    query: str = "",
    role_filter: str = None,   # 默认 "user,assistant"
    limit: int = 3,            # clamp 到 [1,10]
    session_id: str = None,
    around_message_id: int = None,
    window: int = 5,           # clamp 到 [1,20]
    sort: str = None,          # "newest" / "oldest"
):
    """
    Discovery: 传 query
    Scroll:    传 session_id + around_message_id
    Browse:    什么都不传
    """
```

### 模式 1: DISCOVERY（传 `query`）

```text
FTS5 搜索 → 按 lineage root 去重 → 返回 top-N 命中：
- snippet
- 锚点前后 ±5 条消息窗口（锚点被标记）
- bookend_start（会话最前 3 条 user+assistant 消息）
- bookend_end（最后 3 条）
无 LLM 摘要，零 LLM 成本
```

### 模式 2: SCROLL（传 `session_id` + `around_message_id`）

```text
以锚点为中心返回 ±window 条消息（clamp 到 [1,20]，默认 5）：
- 拒绝当前会话 lineage 内的锚点
- 透明地把 parent 重绑定到 child lineage
- 无 FTS5，无 bookends
```

### 模式 3: BROWSE（不传参数）

```text
按时间倒序返回最近会话（标题、预览、时间戳）：
- 排除 child / delegation 会话
- 排除 HERMES_SESSION_SOURCE=tool 的会话
零 LLM 成本，即时返回
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
按 lineage root 去重 + 抽取消息窗口与 bookends
  ↓
返回真实消息（无 LLM 步骤）
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
        retention_days: int = 90,        # 清理 90 天以上已结束 session
        min_interval_hours: int = 24,    # 默认每天一次
        vacuum: bool = True,
    ) -> Dict[str, Any]:
        """幂等：state_meta 表记录 last_auto_prune，跨进程同一 HERMES_HOME 共享锁
        返回 {'skipped', 'pruned', 'vacuumed', 'error'?}"""
```

- 新增 `state_meta` key/value 表存储上次运行时间戳（key: `last_auto_prune`）
- 同一 `HERMES_HOME` 下所有 Hermes 进程共享，`min_interval_hours` 内 no-op
- **智能 VACUUM**：只有 `pruned > 0` 才真正执行 VACUUM（`hermes_state.py:1567`），空清理不浪费 I/O
- 永不抛异常——失败记 warning 不影响启动

## 更新 `/usage` 显示账户限制（v2026.4.18+）

`/usage` 命令在原有 token 表格下追加**账户级配额信息**（provider 侧返回的剩余额度、周期、限流）：

- CLI（`cli.py`）：`concurrent.futures.ThreadPoolExecutor(max_workers=1)` + 10s timeout 里 fetch，慢 provider 不会卡 prompt
- Gateway（`gateway/run.py`）：通过 `asyncio.to_thread` fetch；无 agent 驻留时从 `billing_provider` / `billing_base_url` 持久化字段解析 provider
- 新模块 `agent/account_usage.py`（326 行）提供 `fetch_account_usage(provider, base_url, api_key)` 和 `render_account_usage_lines(snapshot, markdown)` 两个入口

## 相关页面

- [[gateway-session-management]] — 网关会话管理（SessionStore 使用 SessionDB）
- [[cli-architecture]] — CLI 中的会话管理与搜索命令
- [[skills-and-memory-interaction]] — Session Search 作为第三种持久化机制

## 相关文件

- `hermes_state.py` — SessionDB 实现
- `tools/session_search_tool.py` — Session Search 工具
- `agent/trajectory.py` — 轨迹保存辅助
