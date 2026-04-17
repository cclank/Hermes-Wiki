---
title: Memory System Architecture
created: 2026-04-07
updated: 2026-04-08
type: concept
tags: [memory, architecture, module]
sources: [tools/memory_tool.py, agent/memory_manager.py, agent/memory_provider.py, agent/builtin_memory_provider.py, run_agent.py, agent/prompt_builder.py, plugins/memory/__init__.py]
---

# 记忆系统架构

## 概述

Hermes 的记忆系统是一个**三层架构**：存储层（MemoryStore）、编排层（MemoryManager）、插件层（MemoryProvider）。

```text
┌─────────────────────────────────────────────┐
│              run_agent.py                   │
│  (prefetch → 注入 → tool 拦截 → sync → flush) │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│           MemoryManager (编排层)             │
│  "内置 + 至多一个外部 Provider"               │
│  工具 schema 合并 / 生命周期钩子广播           │
└────────┬────────────────────┬───────────────┘
         │                    │
┌────────▼────────┐  ┌───────▼────────────────┐
│ BuiltinProvider │  │ External Provider (可选) │
│ MEMORY.md       │  │ honcho / mem0 / 8 种可选 │
│ USER.md         │  └────────────────────────┘
│ MemoryStore     │
└─────────────────┘
```

## 一、存储层：MemoryStore

文件路径：`tools/memory_tool.py`（561 行）

### 双文件存储

- **`MEMORY.md`**（默认上限 2200 字符）— Agent 的个人笔记（环境事实、项目约定、工具特性）
- **`USER.md`**（默认上限 1375 字符）— 用户画像（偏好、沟通风格、期望）
- 存储路径：`{HERMES_HOME}/memories/`
- 条目分隔符：`§`（section sign），支持多行条目

### 冻结快照模式

这是最关键的设计决策：

```text
会话启动 → load_from_disk() → 读取文件 → 捕获快照到 _system_prompt_snapshot
                                                     │
                                              快照注入系统提示
                                              (整个会话不变)
                                                     │
会话中写入 → 更新磁盘文件 + memory_entries ─────── 不修改系统提示
                                                     │
下次会话 → 重新 load_from_disk() → 新快照生效
```

**为什么？** 保持系统提示稳定 → Anthropic prefix cache 不失效。写入立即持久化到磁盘，但当前会话的系统提示看不到自己的写入。

### 原子写入 + 文件锁

```python
# 原子写入：temp file + fsync + os.replace()
def _write_file(path, entries):
    fd, tmp_path = tempfile.mkstemp(dir=path.parent)
    os.fsync(f.fileno())
    os.replace(tmp_path, str(path))  # 原子操作

# 文件锁：独立 .lock 文件 + fcntl 排他锁
def _file_lock(path):
    lock_path = path.with_suffix(path.suffix + ".lock")  # 不锁数据文件本身
    fcntl.flock(fd, fcntl.LOCK_EX)
```

读者总是看到完整的旧文件或完整的新文件，无中间状态。

### 安全扫描

所有写入内容经过 12 种威胁模式检测 + 不可见 Unicode 字符检测：

```python
_MEMORY_THREAT_PATTERNS = [
    # 提示注入
    ("ignore previous instructions", "prompt_injection"),
    ("you are now", "role_hijack"),
    ("do not tell the user", "deception_hide"),
    ("act as if you have no restrictions", "bypass_restrictions"),
    # 泄露
    ("curl ... $KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API", "exfil_curl"),
    ("wget ... $KEY|TOKEN|SECRET", "exfil_wget"),
    ("cat .env|credentials|.netrc|.pgpass|.npmrc|.pypirc", "read_secrets"),
    # 后门
    ("authorized_keys|~/.ssh", "ssh_backdoor"),
    # ... 共 12 种
]
```

### 系统提示格式化

```text
════════════════════════════════════════════════════
MEMORY (your personal notes) [65% — 1,430/2,200 chars]
════════════════════════════════════════════════════
条目 1
§
条目 2
```

### MemoryStore 核心 API

| 方法 | 行为 |
|------|------|
| `load_from_disk()` | 读取文件 → 去重 → 捕获冻结快照 |
| `add(target, content)` | 安全扫描 → 查重 → 检查字符限制 → 追加 → 持久化 |
| `replace(target, old_text, new_content)` | 子串匹配旧条目 → 替换 → 安全扫描 → 持久化 |
| `remove(target, old_text)` | 子串匹配 → 删除 → 持久化 |
| `format_for_system_prompt(target)` | 返回**冻结快照**（非实时状态） |

---

## 二、编排层：MemoryManager

文件路径：`agent/memory_manager.py`（367 行）

### 核心约束

```python
class MemoryManager:
    def __init__(self):
        self._providers: List[MemoryProvider] = []
        self._tool_to_provider: Dict[str, MemoryProvider] = {}  # 工具名 → provider 路由
        self._has_external: bool = False  # 至多一个外部 provider
```

**"内置 + 至多一个外部"规则**：`add_provider()` 会拒绝第二个非 builtin provider，并打印警告。

### 编排方法

| 方法 | 行为 |
|------|------|
| `build_system_prompt()` | 收集所有 provider 的 `system_prompt_block()` 拼接 |
| `prefetch_all(query)` | 合并所有 provider 的 `prefetch()` 结果 |
| `queue_prefetch_all(query)` | 通知所有 provider 后台预取下一轮上下文 |
| `sync_all(user, assistant)` | 将完成的 turn 同步到所有 provider |
| `get_all_tool_schemas()` | 合并所有 provider 工具 schema（按名去重） |
| `handle_tool_call(name, args)` | 通过 `_tool_to_provider` 路由到正确 provider |
| `has_tool(name)` | 检查是否有 provider 处理该工具 |

### 生命周期钩子

所有钩子**广播给全部 provider**，每个 provider 的失败被隔离（try/except，不传播）：

| 钩子 | 触发时机 | 用途 |
|------|---------|------|
| `on_turn_start(turn_number, message)` | 每轮开始前 | 轮次计数、scope 管理 |
| `on_session_end(messages)` | 会话结束 | 提取持久事实、flush 队列 |
| `on_pre_compress(messages)` | 上下文压缩前 | 抢救即将被压缩掉的信息 |
| `on_memory_write(action, target, content)` | 内置 memory 工具写入后 | **仅通知外部 provider**（跳过 builtin），镜像写入 |
| `on_delegation(task, result)` | 子代理完成后 | 父 Agent 观察委派结果 |

### Memory Context Fence

```python
def build_memory_context_block(raw_context: str) -> str:
    # 用 <memory-context> 标签包裹，防止模型把召回内容当作用户输入
    return f"<memory-context>\n{sanitized}\n</memory-context>"
```

---

## 三、插件层：MemoryProvider ABC

文件路径：`agent/memory_provider.py`（232 行）

### 抽象接口

```python
class MemoryProvider(ABC):
    # 必须实现
    @abstractmethod
    def name(self) -> str: ...              # "builtin", "honcho", "mem0"
    @abstractmethod
    def is_available(self) -> bool: ...     # 无网络调用的快速检查
    @abstractmethod
    def initialize(self, session_id, **kwargs): ...  # 会话初始化
    @abstractmethod
    def get_tool_schemas(self) -> List[Dict]: ...    # 暴露给 LLM 的工具

    # 可选覆盖（默认 no-op）
    def system_prompt_block(self) -> str: ...     # 注入系统提示的静态文本
    def prefetch(self, query) -> str: ...         # 每轮前的快速召回
    def queue_prefetch(self, query): ...          # 后台预取
    def sync_turn(self, user, assistant): ...     # 持久化已完成 turn
    def handle_tool_call(self, name, args) -> str: ...  # 处理工具调用
    def shutdown(self): ...                       # 清理资源
    def on_turn_start(self, turn_number, message): ...
    def on_session_end(self, messages): ...
    def on_pre_compress(self, messages) -> str: ...
    def on_memory_write(self, action, target, content): ...
    def on_delegation(self, task, result): ...
```

### initialize() 的 kwargs

**始终提供**：`hermes_home`（HERMES_HOME 路径）、`platform`（"cli"/"telegram"/"discord"...）

**可能提供**：`agent_context`（"primary"/"subagent"/"cron"/"flush"）、`agent_identity`（profile 名）、`agent_workspace`（共享工作区名）、`parent_session_id`（子代理的父 session）、`user_id`（平台用户 ID）

### 8 个可用插件

| 插件          | 路径                                           |
| ----------- | -------------------------------------------- |
| honcho      | `plugins/memory/honcho/` — Honcho AI 辩证式用户建模 |
| mem0        | `plugins/memory/mem0/`                       |
| hindsight   | `plugins/memory/hindsight/`                  |
| holographic | `plugins/memory/holographic/`                |
| openviking  | `plugins/memory/openviking/`                 |
| retaindb    | `plugins/memory/retaindb/`                   |
| supermemory | `plugins/memory/supermemory/`                |
| byterover   | `plugins/memory/byterover/`                  |

插件发现机制：扫描 `plugins/memory/` 目录，找到含 `__init__.py` 的子目录，调用 `is_available()` 快速检查。

---

## 四、Agent 集成链路

### Memory 工具的特殊拦截

Memory 工具**不在 tool registry 中**。它在 `run_agent.py` 中被显式拦截：

```python
# run_agent.py:6078-6100 — 特殊分支，不走 registry.dispatch()
elif function_name == "memory":
    result = memory_tool(
        action=args.get("action"),
        target=args.get("target", "memory"),
        content=args.get("content"),
        old_text=args.get("old_text"),
        store=self._memory_store,
    )
    # 通知外部 provider 镜像写入
    if self._memory_manager and args.get("action") in ("add", "replace"):
        self._memory_manager.on_memory_write(action, target, content)
```

**为什么不走 registry？** 因为 memory 工具需要直接访问 `self._memory_store` 实例，而 registry 的 handler 签名不传 agent 内部状态。

### 完整生命周期

```text
会话启动
    │
    ├── MemoryStore.load_from_disk() → 冻结快照
    ├── MemoryManager.add_provider(builtin)
    ├── MemoryManager.add_provider(honcho)  ← 如果配置了
    ├── provider.initialize(session_id, hermes_home=..., platform=...)
    └── 系统提示 = builtin.system_prompt_block() + external.system_prompt_block()

每轮对话
    │
    ├── [API 调用前]
    │   ├── prefetch_all(user_message) → 合并所有 provider 召回
    │   └── 用 <memory-context> fence 包裹 → 注入到当前 turn 的用户消息中
    │       （临时注入，不修改原始消息，不持久化到 session）
    │
    ├── [工具调用]
    │   ├── "memory" → 特殊拦截 → MemoryStore.add/replace/remove
    │   │                        → on_memory_write() 通知外部 provider
    │   └── "honcho_*" 等 → MemoryManager.handle_tool_call() → 路由到外部 provider
    │
    └── [API 调用后]
        ├── sync_all(user_message, assistant_response) → 持久化到所有 provider
        └── queue_prefetch_all(user_message) → 后台预取下一轮上下文

上下文压缩前
    │
    ├── flush_memories(messages) → 让模型把重要信息写入 memory
    └── on_pre_compress(messages) → 通知外部 provider 抢救信息

会话结束
    │
    ├── on_session_end(messages) → 全量历史交给 provider
    └── shutdown_all() → 清理资源
```

### 后台记忆 Review

系统每 10 轮（`_memory_nudge_interval`）自动触发一次后台 review：

```python
# run_agent.py — 轮次计数器
self._turns_since_memory += 1
if self._turns_since_memory >= 10:
    _should_review_memory = True  # 在主循环结束后触发 _spawn_background_review()
```

Review Agent 以 `_MEMORY_REVIEW_PROMPT` 审视对话历史，自动调用 memory 工具提取持久事实。

---

## 五、LLM 看到的 Memory 工具

```python
# tools/memory_tool.py:489-538 — 工具 schema
{
    "name": "memory",
    "description": "Save durable facts about the user or environment...",
    "parameters": {
        "action": "add | replace | remove",
        "target": "memory | user",
        "content": "要添加/替换的内容",
        "old_text": "要匹配的旧文本（replace/remove 时必填）"
    }
}
```

系统提示中的指导（`prompt_builder.py:144-156`）：

```text
MEMORY_GUIDANCE:
- 保存用户偏好、环境细节、工具特性、稳定约定
- 优先保存"能减少用户未来纠正"的信息
- 不要保存：任务进度、会话结果、完成的工作日志、临时 TODO
- 发现新方法？用 skill 工具保存，不用 memory
```

---

## 六、配置

```yaml
# config.yaml
memory:
  memory_enabled: true           # 启用 MEMORY.md（默认 false）
  user_profile_enabled: true     # 启用 USER.md（默认 false）
  memory_char_limit: 2200        # MEMORY.md 字符上限
  user_char_limit: 1375          # USER.md 字符上限
  nudge_interval: 10             # 多少轮触发一次后台 memory review
  flush_min_turns: 6             # 压缩前至少经过多少轮才允许 flush
  provider: honcho               # 外部 provider 名称（可选）
```

---

## 七、设计要点

### 失败隔离

MemoryManager 中每个 provider 方法调用都在 try/except 中。一个 provider 崩溃不影响其他 provider，不阻塞 Agent 执行。

### 内置 memory 写入镜像

当 LLM 调用 `memory(action="add", target="user", content="用户偏好暗色模式")` 时：
1. MemoryStore 写入 `USER.md`（本地文件）
2. `on_memory_write("add", "user", "用户偏好暗色模式")` 通知外部 provider
3. 外部 provider（如 Honcho）可以将此事实同步到自己的后端

**仅 add 和 replace 触发镜像，remove 不触发。**

### 预取缓存

`prefetch_all()` 在每次 API 调用前调用一次，结果缓存到 `_ext_prefetch_cache`。同一轮内多次 tool call 不会重复预取（避免 10 次工具调用 = 10 倍延迟）。

---

## 八、FAQ

### Q1：冻结快照下，当前会话怎么看到刚写入的记忆？

**通过工具返回值兜底。** 每次 `memory(action="add/replace/remove")` 调用后，返回值包含**实时的全部条目**：

```json
{
  "success": true,
  "entries": ["条目1", "条目2", "刚新增的条目3"],
  "usage": "65% — 1,430/2,200 chars",
  "entry_count": 3
}
```

模型在对话上下文中已经能看到最新内容，不需要系统提示更新。

```text
Turn 1:  系统提示包含冻结快照 [条目1, 条目2]
Turn 3:  LLM 调用 memory(add, "条目3")
         → 返回值包含 [条目1, 条目2, 条目3]  ← 模型能看到
Turn 5:  LLM 调用 memory(replace, old="条目1", new="更新的条目1")
         → 返回值包含 [更新的条目1, 条目2, 条目3]

系统提示始终显示 [条目1, 条目2]  ← 冻结不变，保护 prefix cache
对话上下文里有完整实时状态        ← 功能不受影响
```

### Q2：超过字符限制会怎样？

**硬拒绝 + 返回当前条目让模型自己管理空间。** 没有自动淘汰、没有 LRU、没有溢出。

```json
{
  "success": false,
  "error": "Memory at 2,100/2,200 chars. Adding this entry (200 chars) would exceed the limit. Replace or remove existing entries first.",
  "current_entries": ["条目1", "条目2", "条目3"],
  "usage": "2,100/2,200"
}
```

**设计意图**：Memory 不是数据库，是**精心策展的小卡片盒**。限制空间逼模型做策展 — 过时的 replace、不重要的 remove、新发现的 add。

### Q3：更多历史信息怎么办？

Memory 只存**持久事实**（2200 + 1375 字符）。更大量的历史信息通过 **session_search 工具**检索。

两者分工明确，系统提示里显式指导模型：

```text
MEMORY_GUIDANCE:
  "Do NOT save task progress, session outcomes, completed-work logs...
   use session_search to recall those from past transcripts."
```

---

## 九、与 Session Search 的关系

Session Search 不是 Memory 的一部分，但是 Memory 系统的**互补机制**。

|          | Memory 工具          | Session Search 工具                        |
| -------- | ------------------ | ---------------------------------------- |
| **存什么**  | 持久事实（偏好、环境、约定）     | 所有历史对话原文                                 |
| **容量**   | 2200 + 1375 字符（有限） | 无限（SQLite，所有会话）                          |
| **检索方式** | 无检索（直接注入系统提示）      | FTS5 关键词检索 + LLM 摘要                      |
| **写入方**  | LLM 主动调用 memory 工具 | 自动（每轮对话自动持久化到 SQLite）                    |
| **读取成本** | 零（冻结快照在系统提示里）      | FTS5 查询 + Gemini Flash 摘要（每个会话一次 LLM 调用） |

### Session Search 的工作流程

```text
session_search(query="nginx 配置")
        │
  ┌─────▼──────┐
  │ FTS5 检索   │  BM25 排序，取 top 50 条匹配消息
  └─────┬──────┘
        │
  按 session 分组 → 去重 → 排除当前会话 → 取 top 3
        │
  ┌─────▼──────────────────┐
  │ LLM 摘要（并行）         │  每个会话截取匹配位置 ±50K 字符
  │ Gemini Flash, temp=0.1  │  生成聚焦于搜索词的结构化摘要
  └─────┬──────────────────┘
        │
  返回 per-session 摘要（不是原始对话文本）
```

**注意**：Session Search 是 FTS5 关键词匹配，不是语义向量搜索。搜 "nginx 配置" 不会匹配只写了 "反向代理" 的会话。搜索语法支持 `OR`、`NOT`、`"精确短语"`、`前缀*`。

两种模式：
- **空 query** → 列出最近会话（零 LLM 成本，只返回标题/预览/时间戳）
- **有 query** → FTS5 搜索 + 并行 LLM 摘要（最多 3-5 个会话）

## 相关页面

- [[memory-system-architecture]] — MemoryStore 核心类详细 API（本页）
- [[security-defense-system]] — 记忆内容安全扫描
- [[skills-and-memory-interaction]] — 技能与记忆的交互决策树
- [[context-compressor-architecture]] — 压缩前 flush_memories 和 on_pre_compress
- [[prompt-caching-optimization]] — 冻结快照如何保护 prefix cache
- [[session-search-and-sessiondb]] — Session Search 工具（FTS5 + LLM 摘要）

## 相关文件

- `tools/memory_tool.py` — MemoryStore 类 + memory 工具 schema（561 行）
- `agent/memory_manager.py` — MemoryManager 编排层（367 行）
- `agent/memory_provider.py` — MemoryProvider ABC 接口（232 行）
- `agent/builtin_memory_provider.py` — 内置 Provider（114 行）
- `plugins/memory/` — 8 个外部 Provider 插件
- `run_agent.py` — Agent 集成（工具拦截、prefetch、sync、flush）
- `agent/prompt_builder.py` — MEMORY_GUIDANCE 系统提示
- `tools/session_search_tool.py` — Session Search 工具（FTS5 + LLM 摘要，505 行）
