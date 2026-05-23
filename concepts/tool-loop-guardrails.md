---
title: 工具调用循环护栏
created: 2026-05-04
updated: 2026-05-04
type: concept
tags: [guardrails, tool-loop, safety, controller, warning-first]
sources: [agent/tool_guardrails.py, run_agent.py, tests/agent/test_tool_guardrails.py]
---

# 工具调用循环护栏（Tool Call Loop Guardrails）

## 概述

`agent/tool_guardrails.py`（455 行）实现一个**纯函数式控制器**，跟踪每轮内 agent 的 tool call 模式，发现"loop"时给出 warning（默认）或 hard stop（opt-in）。设计原则：**warning-first**——默认只警告不阻止，hard stop 必须显式开启。

源码：

```
agent/tool_guardrails.py:1-7
The controller in this module is intentionally side-effect free: it tracks
per-turn tool-call observations and returns decisions. Runtime code owns
whether those decisions become warning guidance, synthetic tool results, or
controlled turn halts.
```

## 三种 loop 模式

### 1. Exact Failure Loop — 同 args 重复失败

签名 = `(tool_name, sha256(canonical_json(args)))`。同签名调用累计失败次数。

| 触发 | 默认阈值 | 行为 |
|------|---------|------|
| `exact_failure_warn_after` | 2 | warn |
| `exact_failure_block_after` | 5 | block（仅 hard_stop_enabled=true） |

### 2. Same Tool Failure Loop — 同工具任意 args 失败

按 `tool_name` 聚合该轮失败计数。

| 触发 | 默认阈值 | 行为 |
|------|---------|------|
| `same_tool_failure_warn_after` | 3 | warn |
| `same_tool_failure_halt_after` | 8 | halt（仅 hard_stop_enabled=true） |

### 3. Idempotent No-Progress Loop — 只读工具同 args 同结果

只对 `IDEMPOTENT_TOOL_NAMES`（read_file / search_files / web_search / web_extract / session_search / browser_snapshot / mcp_filesystem_*）生效。结果用 `_result_hash()` 哈希——先 `safe_json_loads` 规范化后 sha256。

| 触发 | 默认阈值 | 行为 |
|------|---------|------|
| `no_progress_warn_after` | 2 | warn |
| `no_progress_block_after` | 5 | block（仅 hard_stop_enabled=true） |

## 工具分类

`tool_guardrails.py:19-59`：

```python
IDEMPOTENT_TOOL_NAMES = frozenset({
    "read_file", "search_files",
    "web_search", "web_extract",
    "session_search",
    "browser_snapshot", "browser_console", "browser_get_images",
    "mcp_filesystem_read_file", "mcp_filesystem_read_text_file",
    "mcp_filesystem_read_multiple_files",
    "mcp_filesystem_list_directory", "mcp_filesystem_list_directory_with_sizes",
    "mcp_filesystem_directory_tree",
    "mcp_filesystem_get_file_info",
    "mcp_filesystem_search_files",
})

MUTATING_TOOL_NAMES = frozenset({
    "terminal", "execute_code", "write_file", "patch",
    "todo", "memory", "skill_manage",
    "browser_click", "browser_type", "browser_press",
    "browser_scroll", "browser_navigate",
    "send_message", "cronjob", "delegate_task", "process",
})
```

`_is_idempotent()` 双重检查：先排除 mutating，再确认在 idempotent 集合内。无标签的工具（MCP/插件）一律不算 idempotent，no-progress 检测不会误伤。

## 决策结构

### `ToolGuardrailDecision`（`tool_guardrails.py:143-172`）

```python
@dataclass(frozen=True)
class ToolGuardrailDecision:
    action: str = "allow"  # allow | warn | block | halt
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

**关键属性**：`warn` 仍允许执行（`allows_execution=True`），只附加运行时指引。`block` 在调用前拦截，`halt` 在调用后停止该轮。

### `ToolCallSignature`（`tool_guardrails.py:126-141`）

```python
@dataclass(frozen=True)
class ToolCallSignature:
    tool_name: str
    args_hash: str   # sha256 of canonical_tool_args(args)
```

`canonical_tool_args` 用 `sort_keys=True, separators=(",", ":"), default=str` 序列化，确保 args 顺序无关。`to_metadata()` 只暴露 hash，**不暴露 raw args** 到 telemetry。

## 工作流程

`ToolCallGuardrailController` 在每轮开始 `reset_for_turn()`：

```python
def reset_for_turn(self):
    self._exact_failure_counts: dict[ToolCallSignature, int] = {}
    self._same_tool_failure_counts: dict[str, int] = {}
    self._no_progress: dict[ToolCallSignature, tuple[str, int]] = {}
    self._halt_decision: ToolGuardrailDecision | None = None
```

### `before_call(tool_name, args)`

`tool_guardrails.py:238-280`。**仅当 `hard_stop_enabled=True`** 才检查。
- 如果该签名 exact_failure_count ≥ block 阈值 → 返回 `block`，记录 `_halt_decision`。
- 如果是 idempotent 且 no_progress repeat_count ≥ block 阈值 → 返回 `block`。
- 否则 `allow`。

### `after_call(tool_name, args, result, failed=None)`

`tool_guardrails.py:282-375`。

**失败路径**：
1. 该签名 `_exact_failure_counts +1`
2. 该工具 `_same_tool_failure_counts +1`
3. 清掉该签名的 no_progress 记录
4. 检查 same_tool halt → halt 阈值 → `halt`
5. 检查 exact warn 阈值 → `warn`
6. 检查 same_tool warn 阈值 → `warn`

**成功路径**：
1. 清掉 exact_failure / same_tool 计数
2. 若不是 idempotent → `allow`
3. 计算 `_result_hash(result)`，与该签名上次记录比较：
   - 相同 → `repeat_count +1`
   - 不同 → `repeat_count = 1`
4. `repeat_count ≥ no_progress warn 阈值` → `warn`

## Failure 检测

`classify_tool_failure()`（`tool_guardrails.py:188-218`）镜像 `agent.display._detect_tool_failure`，**保证护栏判断和 CLI 用户可见的 `[error]` 标签一致**。生产路径上 `run_agent.py` 总是显式传 `failed=`；这个函数是测试和工具的兜底。

特殊处理：
- `terminal`: 解析 result 为 dict，`exit_code != 0` 视为失败
- `memory`: `success: false` + `"exceed the limit"` → `[full]`
- 通用：`"error"` / `"failed"` / 以 `Error` 开头 → `[error]`

## 输出

### `toolguard_synthetic_result(decision)` — block 时合成 tool 结果

```python
def toolguard_synthetic_result(decision):
    return json.dumps({
        "error": decision.message,
        "guardrail": decision.to_metadata(),
    }, ensure_ascii=False)
```

代替真实工具调用，让 agent 的 tool result 历史保持完整。

### `append_toolguard_guidance(result, decision)` — warn/halt 时附加运行时指引

```
[Tool loop warning: repeated_exact_failure_warning; count=3; <message>]
```

或

```
[Tool loop hard stop: same_tool_failure_halt; count=8; <message>]
```

附在原 result 末尾，让 agent 在下一步 reasoning 时看到 self-reflection 提示。

## 配置

```yaml
# config.yaml
tool_loop_guardrails:
  warnings_enabled: true       # 默认 true
  hard_stop_enabled: false     # 默认 false（opt-in）
  warn_after:
    exact_failure: 2
    same_tool_failure: 3
    idempotent_no_progress: 2
  hard_stop_after:
    exact_failure: 5
    same_tool_failure: 8
    idempotent_no_progress: 5
```

`ToolCallGuardrailConfig.from_mapping`（`tool_guardrails.py:82-123`）支持新的嵌套 key 和老的扁平 key 双向兼容。`_positive_int` 兜底，非法值回退到默认。

## 设计哲学

> **warnings_enabled: true, hard_stop_enabled: false**
>
> 警告默认开，硬停默认关，让交互式 CLI/TUI session 收到温和提示，除非用户在 config.yaml 明确开启 circuit-breaker 行为。

——`tool_guardrails.py:71-72`

理由：**hard stop 会破坏 agent 的探索能力**。loop 检测可能误报，warning 让模型自行判断是否调整策略；只在 batch / cron / 长任务这类没有人盯着的场景下才升级到 hard stop。

## 验证 PR

- `58b8996` `fix(agent): add tool-call loop guardrails`
- `0704589` `fix(agent): make tool loop guardrails warning-first`
- `8fa44b1` `fix(guardrails): preserve display _detect_tool_failure semantics`

## 相关概念

- [[tool-registry-architecture]] — 中央 tool 注册，guardrails 在 dispatch 边界拦截
- [[interrupt-and-fault-tolerance]] — error_classifier vs tool_guardrails 的分工：classifier 处理**单次错误分类**，guardrails 处理**多次重复模式**
- [[parallel-tool-execution]] — 并行执行不影响 guardrails，per-turn controller 是单线程聚合
