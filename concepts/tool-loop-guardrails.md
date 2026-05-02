---
title: Tool-call Loop Guardrails
created: 2026-05-02
updated: 2026-05-02
type: concept
tags: [agent, guardrail, fault-tolerance, tool-call, loop, controller]
sources: [agent/tool_guardrails.py, run_agent.py:165-167, run_agent.py:1160-1657, run_agent.py:9152-9188]
---

# Tool-call Loop Guardrails

## 一句话

Per-turn 控制器，跟踪 tool call 的失败/无进展模式，按阈值返回 `allow` / `warn` / `block` / `halt` 决策——**决策模块零副作用**，运行时决定是否变成警告引导、合成 tool result 还是受控终止。

> 实现源码：`agent/tool_guardrails.py`（456 行，v0.12.0 新增）

## 设计动机

模型常陷入两种循环：

1. **重复失败**：同一 tool 同一 args 反复失败（典型：编辑不存在的行号、跑总报错的命令）
2. **无进展只读**：read-only tool 反复返回相同结果（典型：`web_search` 同一 query；`read_file` 同一区段）

旧 `ITERATION_BUDGET` 只能数 turns，不区分这种**死循环 vs 正常多 turn**。Guardrail 控制器精确捕捉。

## 核心数据结构

### 配置（`tool_guardrails.py:62-80`）

```python
@dataclass(frozen=True)
class ToolCallGuardrailConfig:
    warnings_enabled: bool = True
    hard_stop_enabled: bool = False        # ← 默认关闭
    exact_failure_warn_after: int = 2
    exact_failure_block_after: int = 5
    same_tool_failure_warn_after: int = 3
    same_tool_failure_halt_after: int = 8
    no_progress_warn_after: int = 2
    no_progress_block_after: int = 5
    idempotent_tools: frozenset[str] = IDEMPOTENT_TOOL_NAMES
    mutating_tools: frozenset[str] = MUTATING_TOOL_NAMES
```

> 默认警告启用、硬停止关闭——交互 CLI/TUI 用户得到温和提示；circuit-breaker 行为需要在 `config.yaml` 里显式开启。

### 工具分类（frozenset）

**Idempotent**（`tool_guardrails.py:19-38`）—— 这些工具的相同 args 应该返回相同结果：

```
read_file, search_files, web_search, web_extract, session_search,
browser_snapshot, browser_console, browser_get_images,
mcp_filesystem_{read_file, read_text_file, read_multiple_files,
                list_directory, list_directory_with_sizes,
                directory_tree, get_file_info, search_files}
```

**Mutating**（`tool_guardrails.py:40-59`）—— 永不视为 idempotent，重复调用合理：

```
terminal, execute_code, write_file, patch, todo, memory, skill_manage,
browser_{click, type, press, scroll, navigate},
send_message, cronjob, delegate_task, process
```

互斥分类（`_is_idempotent`，`tool_guardrails.py:377-380`）：mutating 永远赢——即便 tool name 同时在两个集合，也按 mutating 处理。

### 调用签名（`tool_guardrails.py:127-140`）

```python
@dataclass(frozen=True)
class ToolCallSignature:
    tool_name: str
    args_hash: str          # SHA256 of canonical JSON

    @classmethod
    def from_call(cls, tool_name, args):
        canonical = canonical_tool_args(args or {})
        return cls(tool_name=tool_name, args_hash=_sha256(canonical))
```

Canonical args（`tool_guardrails.py:175-185`）：sorted keys、紧凑 separators、`default=str`——保证语义等价的 args 哈希相同。

### 决策（`tool_guardrails.py:143-172`）

```python
@dataclass(frozen=True)
class ToolGuardrailDecision:
    action: str = "allow"   # allow | warn | block | halt
    code: str = "allow"
    message: str = ""
    tool_name: str = ""
    count: int = 0
    signature: ToolCallSignature | None = None

    @property
    def allows_execution(self) -> bool:
        return self.action in {"allow", "warn"}

    @property
    def should_halt(self) -> bool:
        return self.action in {"block", "halt"}
```

四种动作的语义：

| Action | allows_execution | should_halt | 说明 |
|--------|-----------------|-------------|------|
| `allow` | ✓ | ✗ | 默认通过 |
| `warn` | ✓ | ✗ | 通过但在 result 末尾追加警告 |
| `block` | ✗ | ✓ | 在 `before_call` 拒绝调用，返回合成 result |
| `halt` | ✗ | ✓ | `after_call` 触发，标记 turn 终止 |

## 三大检测维度

### 1. Exact Failure（同 tool + 同 args 反复失败）

`_exact_failure_counts: dict[ToolCallSignature, int]`

- 阈值 `exact_failure_warn_after` (默认 2) → 警告
- 阈值 `exact_failure_block_after` (默认 5) → block（仅 hard_stop_enabled）

### 2. Same-tool Failure（同 tool 名，args 不同也算）

`_same_tool_failure_counts: dict[str, int]`

- 阈值 `same_tool_failure_warn_after` (默认 3) → 警告
- 阈值 `same_tool_failure_halt_after` (默认 8) → halt

### 3. Idempotent No Progress（read-only 返回相同结果）

`_no_progress: dict[ToolCallSignature, tuple[str, int]]`

- key: signature
- value: `(result_hash, repeat_count)`
- 阈值 `no_progress_warn_after` (默认 2) → 警告
- 阈值 `no_progress_block_after` (默认 5) → block

仅对 `_is_idempotent(tool_name)` 为 True 的工具激活。

## 控制器生命周期

`ToolCallGuardrailController`（`tool_guardrails.py:221-380`）：

```python
def __init__(self, config=None):
    self.config = config or ToolCallGuardrailConfig()
    self.reset_for_turn()    # 每 turn 重置状态

def reset_for_turn(self):
    self._exact_failure_counts = {}
    self._same_tool_failure_counts = {}
    self._no_progress = {}
    self._halt_decision = None
```

**关键**：状态**按 turn** 重置——一个 turn 内 4 次 web_search 同 query 触发 warn，下个 turn 重新计数。

## 决策点

### `before_call`（`tool_guardrails.py:238-280`）

仅当 `hard_stop_enabled=True` 才主动 block。检查：

- exact failure count ≥ `exact_failure_block_after` → block
- idempotent + no-progress count ≥ `no_progress_block_after` → block

否则返回 `allow`。

### `after_call`（`tool_guardrails.py:282-375`）

```python
def after_call(self, tool_name, args, result, *, failed=None):
    if failed is None:
        failed, _ = classify_tool_failure(tool_name, result)

    if failed:
        # 同时累加 exact_failure 和 same_tool_failure 计数
        # 清除 no_progress（失败不算 progress）
        # 检查 halt 阈值（先 halt 后 warn）
        # 返回 warn/halt/allow
    else:
        # 清除失败计数
        # 非 idempotent → return allow
        # idempotent → 计 result_hash 重复次数；触发 warn
```

### `classify_tool_failure`（`tool_guardrails.py:188-218`）

> 安全 fallback。生产代码总是显式传 `failed=`（来自 `agent.display._detect_tool_failure`）；这里仅为独立测试 / 工具调用使用。

镜像 `_detect_tool_failure` 完全一致：

| Tool | 失败判定 |
|------|---------|
| `terminal` | JSON 解析后 `exit_code != 0` → `[exit N]` |
| `memory` | `success: False` 且 error 含 `exceed the limit` → `[full]` |
| 其他 | 前 500 chars lowercase 包含 `"error"` / `"failed"` 或 startswith `Error` → `[error]` |

## 输出整形

### 警告：追加到 result 末尾（`tool_guardrails.py:394-403`）

```python
def append_toolguard_guidance(result, decision):
    if decision.action not in {"warn", "halt"} or not decision.message:
        return result
    label = "Tool loop hard stop" if decision.action == "halt" else "Tool loop warning"
    suffix = f"\n\n[{label}: {decision.code}; count={decision.count}; {decision.message}]"
    return (result or "") + suffix
```

### Block / 合成 result（`tool_guardrails.py:383-391`）

```python
def toolguard_synthetic_result(decision):
    return json.dumps({
        "error": decision.message,
        "guardrail": decision.to_metadata(),
    }, ensure_ascii=False)
```

模型看到的不是真 tool result，而是结构化错误 + guardrail metadata——可被推理出"我陷入循环了"。

## 在 `run_agent.py` 的集成

### 实例化（`run_agent.py:165-167, 1160, 1653-1657`）

```python
from agent.tool_guardrails import (
    ToolCallGuardrailConfig,
    ToolCallGuardrailController,
)
# __init__ 默认实例
self._tool_guardrails = ToolCallGuardrailController()
self._tool_guardrail_halt_decision: ToolGuardrailDecision | None = None
# 配置 override（行 1653-1657）
self._tool_guardrails = ToolCallGuardrailController(
    ToolCallGuardrailConfig.from_mapping(
        _agent_cfg.get("tool_loop_guardrails", {})
    )
)
```

### 集成方法（`run_agent.py:9152-9188`）

```python
def _set_tool_guardrail_halt(self, decision):
    if decision.should_halt and self._tool_guardrail_halt_decision is None:
        self._tool_guardrail_halt_decision = decision

def _toolguard_controlled_halt_response(self, decision):
    return (
        f"I stopped retrying {decision.tool_name} because it hit the tool-call "
        f"guardrail ({decision.code}) after {decision.count} repeated "
        "non-progressing attempts. ..."
    )

def _append_guardrail_observation(self, tool_name, args, result, *, failed):
    decision = self._tool_guardrails.after_call(
        tool_name, args, result, failed=failed
    )
    if decision.action in {"warn", "halt"}:
        result = append_toolguard_guidance(result, decision)
    if decision.should_halt:
        self._set_tool_guardrail_halt(decision)
    return result

def _guardrail_block_result(self, decision):
    self._set_tool_guardrail_halt(decision)
    return toolguard_synthetic_result(decision)
```

## 配置 schema

`config.yaml`：

```yaml
agent:
  tool_loop_guardrails:
    warnings_enabled: true        # 默认 true
    hard_stop_enabled: false       # 默认 false
    warn_after:
      exact_failure: 2
      same_tool_failure: 3
      idempotent_no_progress: 2
    hard_stop_after:
      exact_failure: 5
      same_tool_failure: 8
      idempotent_no_progress: 5
```

`ToolCallGuardrailConfig.from_mapping`（`tool_guardrails.py:82-123`）支持两种命名（嵌套 `warn_after.exact_failure` 或扁平 `exact_failure_warn_after`）。`_as_bool` 与 `_positive_int` 容错（quoted string、负数、非数）。

## 与 [[interrupt-and-fault-tolerance]] 的关系

| 层 | 职责 |
|---|------|
| Guardrails | turn 内细粒度循环检测 |
| Iteration budget | turn 总数限制 |
| Error classifier | API 级错误分类（rate limit / quota / auth）|
| Fallback chain | provider 切换 |

四层互不干扰。Guardrail 触发 halt 不消耗 fallback 重试预算。

## 来源

- 配置：`agent/tool_guardrails.py:62-123`
- 签名：`agent/tool_guardrails.py:127-185`
- 决策：`agent/tool_guardrails.py:143-172`
- 控制器：`agent/tool_guardrails.py:221-380`
- 失败分类：`agent/tool_guardrails.py:188-218`
- 输出整形：`agent/tool_guardrails.py:383-403`
- 集成：`run_agent.py:9152-9188`
