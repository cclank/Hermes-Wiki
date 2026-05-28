---
title: Memory System Architecture
created: 2026-04-07
updated: 2026-05-28
type: concept
tags: [memory, architecture, module, promptware-defense, honcho, hindsight, memory-provider]
sources: [tools/memory_tool.py, tools/threat_patterns.py, agent/memory_manager.py, agent/memory_provider.py, agent/builtin_memory_provider.py, run_agent.py, agent/conversation_loop.py, agent/prompt_builder.py, plugins/memory/__init__.py, plugins/memory/honcho/__init__.py, plugins/memory/honcho/client.py, plugins/memory/honcho/session.py, plugins/memory/honcho/cli.py, plugins/memory/hindsight/__init__.py, gateway/platforms/api_server.py]
---

> **v2026.5.7 增量**：
>
> - **API Server `X-Hermes-Session-Key` header**（#20199）—— 给 memory provider 一个稳定 session 标识，让长期记忆按 session 隔离。源码 `gateway/platforms/api_server.py:5` 注释。
> - **Hindsight provider** 增加 `update_mode='append'` probe API，跨进程 dedup（@nicoloboschi, #20222）。
> - `on_session_switch` 钩子已落地（v2026.4.23 引入）：源码确认 `cli.py:5339, 5447, 5583` + `run_agent.py:9540` 调用 `_memory_manager.on_session_switch(...)` —— 在 `/resume` / `/branch` / `/reset` / `/new` / 上下文压缩时通知 provider 刷新缓存。
>
> **2026-05-27 增量 — Honcho Memory Provider 全 identity-mapping wave**：
>
> Honcho 是首个具备 *AI-native 跨会话用户建模* 的外部 MemoryProvider：dialectic Q&A + semantic search + peer cards + persistent conclusions。15 个 honcho 子 commit 同日合入（commits `2e3c662` → `eccbbe4`），关键能力：
>
> - **5 个 honcho_* 工具**：`honcho_profile` / `honcho_search` / `honcho_reasoning` / `honcho_context` / `honcho_conclude`（`plugins/memory/honcho/__init__.py:33-188`）
> - **配置 chain**：`$HERMES_HOME/honcho.json`（profile-scoped）> `~/.honcho/config.json`（legacy 全局）> 环境变量
> - **Identity-mapping 三 shape**：`single` / `multi` / `hybrid` —— 控制 Telegram UID / Discord snowflake 等 runtime ID 如何映射到 Honcho peer。CLI wizard 在 `plugins/memory/honcho/cli.py:512-600`
> - **`pinUserPeer` ↔ `pinPeerName`** 别名链（`refactor(honcho): accept pinUserPeer as backwards-compatible alias`） + 4-key 解析优先级 `host_block.pinUserPeer > host_block.pinPeerName > root.pinUserPeer > root.pinPeerName`（`client.py:495-505`）
> - **修复簇**：peer-card read/write 路径对齐、user_id 进入 agent cache 签名（防 shared-thread peer 污染）、identity-mapping 继承到 cloned profile、pinPeerName transition 漏洞补全、user context peer 视角对齐
> - **`hermes honcho setup`** wizard：单步选 deployment-shape，单 → multi 转换会预警 peer pool orphan 并引导 hybrid
> - **gateway 集成**：`gateway/run.py:15109-15121` 暴露 honcho 配置到 doctor 视图（`peer_name` / `ai_peer` / `pin_peer_name` / `runtime_peer_prefix`）
>
> 详细见 [[2026-05-27-update#2-honcho-memory-provider]] 与 plugin README。

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

### 外部漂移防护（2026-05-23, PR #30877 / #26045）

原子写不能解决另一个问题：**MEMORY.md / USER.md 被 tool 之外的写者改了**（patch tool、用户手编、`cat >> MEMORY.md` 的 onboarding）。

生产事故：两个并发 session，A 用 patch tool 追加 ~8KB 结构化内容到 MEMORY.md（无 § 分隔符）。B 后来用 stale in-memory state（1 entry, ~331 chars）调 `memory(action=replace)`。`_read_file` 把 A 的 8KB 解析为一个 entry，replace 把它截到 333 字节 —— **8KB 内容静默被销毁**。

`tools/memory_tool.py:482-530 _detect_external_drift` 在每次 add/replace/remove 之前跑双信号检测：

```python
def _detect_external_drift(self, target):
    raw = read(path)
    parsed = self._parse(raw)
    roundtrip = self._serialize(parsed)
    max_entry_len = max(len(e.content) for e in parsed)
    # 信号 1：roundtrip 字节级不等价（分隔符 / 编码异常）
    # 信号 2：单 entry 超过整 store 限额（memory=2200, user=1375 chars）
    drift_detected = (raw.strip() != roundtrip) or (max_entry_len > char_limit)
    if not drift_detected: return None
    bak_path = path.with_suffix(path.suffix + f".bak.{ts}")
    shutil.copy2(path, bak_path)
    return str(bak_path)
```

**触发后**：

- `_reload_target` 写 `.bak.<ts>` 快照（`memory_tool.py:219-231, 530`）
- `add` / `replace` / `remove` **拒绝 flush**（`:277-282, 329-331, 381-383`）—— 原文件保持原样
- 错误字典携带 `.bak` 路径 + 模型可读的 remediation：`"integrate missing entries via memory(add=...) one at a time, then rewrite the file clean"`（`memory_tool.py:108-130 _drift_error`）

USER.md 同样保护。Tests 137 → 144（+7 个用例 pin 三种 mutator 的拒绝行为、`.bak.<ts>` 命名、false-positive 净化场景）。

### 安全扫描（2026-05-26 起：双层 + Load-Time Snapshot 净化）

写入扫描与 snapshot 净化合走 `tools/threat_patterns.py`（v0.14.0 安全 wave + 2026-05-26 promptware defense 提取出的**共享威胁模式库**）。

**Layer A — 写入扫描（旧路径，scope="strict"）**：每次 `memory(action=add/replace)` 调用 `first_threat_message(content, scope="strict")`，命中即 raise，content 永远到不了磁盘。Strict scope 包括经典 prompt injection / role-hijack / exfil curl-wget / read_secrets / authorized_keys / `update AGENTS.md` / hardcoded api_key 等。

**Layer B — Load-Time Snapshot 净化（2026-05-26 NEW，commit `0dee92df2`）**：`MemoryStore.load_from_disk()`（`tools/memory_tool.py:133-172`）读 `MEMORY.md` / `USER.md` 后调 `_sanitize_entries_for_snapshot()`（line 174-208），**每 entry 跑 `scan_for_threats(entry, scope="strict")`**。命中即在 frozen system-prompt snapshot 中替换为：

```text
[BLOCKED: MEMORY.md entry contained threat pattern(s): <ids>.
Removed from system prompt; use memory(action=read) to inspect
and memory(action=remove) to delete the original.]
```

**双轨设计原则**：

- `_system_prompt_snapshot["memory"]` / `["user"]`（line 167-171）—— 进系统提示，毒化条目被 BLOCKED 占位替换。
- `memory_entries` / `user_entries`（live state）—— 保留**原始**毒化文本。用户仍可 `memory(action=read)` 查看 + `memory(action=remove)` 删除。

> Silently dropping 会**对用户隐藏攻击**，违反 Hermes 的可见性原则。BLOCKED 占位向 agent 与用户都明示了"曾经有内容在这里且被拦"。

**Prefix cache 不变量保持**：scan 是 deterministic from disk bytes，snapshot 整 session 稳定 → 与冻结快照（[[prompt-caching-optimization]]）兼容。

**威胁模型覆盖（poison 来源）**：

- 供应链攻击（恶意 dependency 的 install hook 写 MEMORY.md）
- 被攻陷的工具（write 工具被诱使写 USER.md）
- 跨 session 污染（sister-session 把 prompt injection 写进 user-level memory）
- Brainworm 类 promptware（C2 node registration / heartbeat / `name yourself X` / `unset CLAUDE` 等，scope="strict" 继承自 `"context"` 集合）

```python
# tools/threat_patterns.py 内的 _PATTERNS (节选 strict 集)
("ignore previous instructions", "prompt_injection", "all"),
("you are now a/an/the ...", "role_hijack", "context"),  # context implies strict
("name yourself \w+", "identity_override", "context"),
("register (as) a? node", "c2_node_registration", "context"),
("you must (register|connect|report|beacon)", "forced_action", "context"),
("unset CLAUDE|CODEX|HERMES|AGENT|OPENAI|ANTHROPIC", "env_var_unset_agent", "context"),
("authorized_keys", "ssh_backdoor", "strict"),
("(update|modify|edit|write|append) ... AGENTS.md|CLAUDE.md", "agent_config_mod", "strict"),
("api_key|token|secret|password = \"...20+ chars...\"", "hardcoded_secret", "strict"),
```

完整 250+ 模式与 invisible-unicode 集见 `tools/threat_patterns.py:49-137`。

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
    def on_session_switch(self, new_session_id, parent_session_id, reset, **kw): ...  # v2026.4.23+
```

### `on_session_switch` — Session ID 中途切换通知（v2026.4.23+）

之前 provider 只在初始化时收到一次 `session_id`。但 `session_id` 会在 `/resume`、`/branch`、`/reset`、`/new`、上下文压缩等场景被**重新分配**——provider 不知道，后续写入会落到错误的 session 记录里。

`agent/memory_manager.py:on_session_switch()` 现在会在 session_id 改变时调用所有 provider 的 `on_session_switch(new_session_id, parent_session_id, reset, **kwargs)`，让 provider 刷新缓存的 per-session 状态。Provider 不需要 tear down 重建，只需要更新内部句柄。错误会被 swallow（log debug 不阻塞主流程）。

### `sync_turn` 完整回合消息契约（2026-05-28，v0.15.0，`5a95fb2e1`）

`sync_turn` 新增可选 `messages` 关键字，让外部/社区 memory plugin 收到 OpenAI 风格的**完整对话消息列表**（含 assistant 工具调用 + tool result content），不再只有最终 assistant 文本：

- **签名内省派发**：`agent/memory_manager.py:_provider_sync_accepts_messages` 只给声明了 `messages` 形参（或 `**kwargs`）的 provider 传该参数；所有现有 in-tree provider 保持 legacy `sync_turn(user, assistant)` 签名，调用不变（零行为变化）。
- **不在 core 加结构化 trace 信封** —— provider 自行从标准消息列表重建所需内容。
- 改动：`agent/conversation_loop.py`（+1）/ `agent/memory_manager.py`（+35）/ `agent/memory_provider.py`（+13）/ `run_agent.py`（+9）；并把 **Memori** 文档化为独立社区 memory provider（co-author Dave Heritage @ memorilabs.ai，salvage #28065）。merge HEAD `11d93096` 标题即 "salvage/memori-trace-messages"。

### Hindsight `recall_types` 默认 observation-only（2026-05-28，v0.15.0，`490b3e76b`）

自动召回过去把 Hindsight 的三类 fact（`world` / `experience` / `observation`）全部上屏 —— 三种 framing 重复同一信号、烧掉 `recall_max_tokens`、挤掉模型真正需要的事件。改为默认只召回 `observation`（已去重、密度更高、最贴近对话 ground truth）。现行 `plugins/memory/hindsight/__init__.py`：

| 行 | 内容 |
|----|------|
| `:590` | `self._recall_types: list[str] = ["observation"]`（原为 `None` = 服务端"全返回"） |
| `:867` | `get_config_schema()` 加 `recall_types` 键（`default: "observation"`，可发现于 `hermes config`） |
| `:1202-1209` | `initialize()`：缺失→`["observation"]`；逗号分隔字符串→split；显式 `recall_types=[]`→回退默认（不静默放宽） |
| `:1346-1347` | `if self._recall_types: recall_kwargs["types"] = self._recall_types` |

逐次 `hindsight_recall` 工具调用不受影响（仅当 caller 显式传 `types` 才转发）。配套 `4df62d239` docs 修正 scope。详见 [[2026-05-28-update]]。

### initialize() 的 kwargs

**始终提供**：`hermes_home`（HERMES_HOME 路径）、`platform`（"cli"/"telegram"/"discord"...）

**可能提供**：`agent_context`（"primary"/"subagent"/"cron"/"flush"）、`agent_identity`（profile 名）、`agent_workspace`（共享工作区名）、`parent_session_id`（子代理的父 session）、`user_id`（平台用户 ID）

### 8 个可用插件

| 插件          | 路径                                           |
| ----------- | -------------------------------------------- |
| honcho      | `plugins/memory/honcho/` — Honcho AI 辩证式用户建模 |
| mem0        | `plugins/memory/mem0/`                       |
| hindsight   | `plugins/memory/hindsight/` — long-term memory + knowledge graph + entity resolution |
| holographic | `plugins/memory/holographic/`                |
| openviking  | `plugins/memory/openviking/`                 |
| retaindb    | `plugins/memory/retaindb/`                   |
| supermemory | `plugins/memory/supermemory/`                |
| byterover   | `plugins/memory/byterover/`                  |

插件发现机制：扫描 `plugins/memory/` 目录，找到含 `__init__.py` 的子目录，调用 `is_available()` 快速检查。

### Hindsight Provider（v2026.5+ 增强）

`plugins/memory/hindsight/__init__.py`：长期记忆 with 知识图谱、实体消歧、多策略检索。**Cloud + Local 两种模式**。

| Env Var | 默认 | 说明 |
|---------|------|------|
| `HINDSIGHT_API_KEY` | — | Cloud API key |
| `HINDSIGHT_BANK_ID` | `hermes` | memory bank id |
| `HINDSIGHT_BUDGET` | `mid` | recall 预算: `low`/`mid`/`high` |
| `HINDSIGHT_API_URL` | `https://api.hindsight.vectorize.io` | API endpoint |
| `HINDSIGHT_MODE` | `cloud` | `cloud` / `local` |
| `HINDSIGHT_TIMEOUT` | 120s | API 请求超时 |
| `HINDSIGHT_IDLE_TIMEOUT` | 300s | local daemon 空闲关闭（0 = 不关）|
| `HINDSIGHT_RETAIN_TAGS` | — | 逗号分隔的 retain 标签 |

Config fallback 链：`$HERMES_HOME/hindsight/config.json` (profile-scoped) → `~/.hindsight/config.json` (legacy shared)。

**`update_mode='append'` 探测**（`feat(hindsight): probe API for update_mode='append' support, dedupe across processes` / 3082fa0）：

启动时 probe `<api_url>/version`，gate 在 Hindsight ≥ 0.5.0：
- **支持时**：稳定 session-scoped `document_id = session_id` + `update_mode='append'`，跨进程对同一 session 的 retain 合并到一条文档（不再产生 N 条 process-stamped 重复）
- **不支持时**：`f"{session_id}-{start_ts}"` 唯一 document_id（resume-overwrite 修复 #6654 仍生效）

`_append_capability_cache: Dict[str, bool]` 按 API URL 缓存能力，进程内 probe 一次。

Plugin manifest hook：`on_session_end`。

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
    └── on_pre_compress(messages) → 通知外部 provider 抢救信息
        # ⚠️ flush_memories 在 v2026.4.30 (refactor #15696) 完全移除——
        # 同等职责由 background-review fork（每 N 轮自动触发）承担。

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
- [[context-compressor-architecture]] — 压缩前 `on_pre_compress`（`flush_memories` 已在 v2026.4.30 移除，由 background-review fork 替代）
- [[prompt-caching-optimization]] — 冻结快照如何保护 prefix cache
- [[session-search-and-sessiondb]] — Session Search 工具（FTS5 + LLM 摘要）

## 相关文件

- `tools/memory_tool.py` — MemoryStore 类 + memory 工具 schema（含 2026-05-26 `_sanitize_entries_for_snapshot()` line 174-208）
- `tools/threat_patterns.py` — **NEW 2026-05-26** 共享威胁模式库（252 行），`scan_for_threats(scope="strict")` 是 memory load-time 净化与 write 时 block 共用入口
- `agent/memory_manager.py` — MemoryManager 编排层（367 行）
- `agent/memory_provider.py` — MemoryProvider ABC 接口（232 行）
- `agent/builtin_memory_provider.py` — 内置 Provider（114 行）
- `plugins/memory/` — 8 个外部 Provider 插件
- `run_agent.py` — Agent 集成（工具拦截、prefetch、sync；`flush_memories` 工具已删除）
- `agent/prompt_builder.py` — MEMORY_GUIDANCE 系统提示
- `tools/session_search_tool.py` — Session Search 工具（FTS5 + LLM 摘要，505 行）
