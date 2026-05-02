---
title: Persistent Goals (`/goal`) — Ralph Loop
created: 2026-05-02
updated: 2026-05-02
type: concept
tags: [agent, loop, persistence, ralph, judge, auxiliary, sessiondb, goal]
sources: [hermes_cli/goals.py, cli.py:7046-7140, gateway/run.py:7648-7790]
---

# Persistent Goals (`/goal`) — Ralph Loop

## 一句话

`/goal <text>` 让 Hermes 在**每次 turn 结束后**让辅助模型评判目标是否完成；未完成则自动续写 continuation prompt 进入下一轮，直到完成 / 被暂停 / 用户介入 / 预算耗尽。

> 实现源码：`hermes_cli/goals.py`（535 行，`hermes-agent` v0.12.0 新增）

## 设计不变量

源自 `goals.py:13-28`，逐字翻译：

1. **continuation prompt 是普通 user message**——通过 `run_conversation` 追加，**不动系统提示，不换 toolset**，prompt cache 完整保留
2. **Judge 失败 fail-OPEN**：返回 `continue`，turn budget 是 backstop——broken judge 不能堵死进展
3. **真实用户消息抢占** continuation prompt——并暂停 goal loop 那一 turn；turn 后仍重新评判，避免用户消息恰好完成 goal 时漏判
4. **零硬依赖** `cli.HermesCLI` 和 gateway runner —— 两侧都装同一个 `GoalManager`
5. 模块**完全不碰** agent 的系统提示或 toolset

## 状态机

```
                ┌──────────────┐
   /goal <txt>  │              │  judge=done
   ───────────→ │   active     │ ──────────→  done
                │              │
                └──┬────────┬──┘
                   │        │  budget exhausted
   /goal pause     │        ▼
   ───────────→ paused ─────→ /goal resume → active
                   │
   /goal clear     ▼
   ───────────→ cleared (审计保留)
```

`GoalState`（goals.py:89-119）字段：

```python
@dataclass
class GoalState:
    goal: str
    status: str = "active"          # active | paused | done | cleared
    turns_used: int = 0
    max_turns: int = DEFAULT_MAX_TURNS  # 20
    created_at: float = 0.0
    last_turn_at: float = 0.0
    last_verdict: Optional[str] = None  # "done" | "continue" | "skipped"
    last_reason: Optional[str] = None
    paused_reason: Optional[str] = None
```

## 持久化

存在 `SessionDB.state_meta` 表，key 为 `goal:<session_id>`：

```python
# goals.py:127-128
def _meta_key(session_id: str) -> str:
    return f"goal:{session_id}"
```

这意味着：
- `/resume <session>` 自动捡回 goal
- profile 切换不影响——`SessionDB` 走当前 `HERMES_HOME`
- `_DB_CACHE` 按 home 路径缓存 SessionDB 实例（goals.py:131-161）

`load_goal` / `save_goal` / `clear_goal`（goals.py:164-204）—— DB 不可用时 No-op，不抛异常。

## 三个 Prompt（编译时常量）

### Continuation prompt

`goals.py:52-58`：

```
[Continuing toward your standing goal]
Goal: {goal}

Continue working toward this goal. Take the next concrete step.
If you believe the goal is complete, state so explicitly and stop.
If you are blocked and need input from the user, say so clearly and stop.
```

模型有三条出路：完成 / 进一步 / 显式宣告 blocker。

### Judge system prompt

`goals.py:61-74`，要求模型做**严格判定**：

> A goal is DONE only when:
> - The response explicitly confirms the goal was completed, OR
> - The response clearly shows the final deliverable was produced, OR
> - The response explains the goal is unachievable / blocked / needs user input (treat this as DONE with reason describing the block).

返回格式严格固定为单行 JSON：`{"done": <true|false>, "reason": "<one-sentence rationale>"}`

### Judge user prompt template

`goals.py:77-81`：把 goal 和 last assistant response 喂给 judge。截断尺寸 4000 字符（`_JUDGE_RESPONSE_SNIPPET_CHARS`）。

## Judge 调用

`judge_goal`（goals.py:268-332）：

```python
def judge_goal(goal: str, last_response: str, *, timeout=30.0) -> Tuple[str, str]:
    # 1. 空 goal → "skipped"
    # 2. 空响应 → "continue"（无可评判）
    # 3. 拿辅助 client： get_text_auxiliary_client("goal_judge")
    # 4. 失败 → "continue"  ← fail-open
    # 5. 调 chat.completions.create(temperature=0, max_tokens=200, timeout=timeout)
    # 6. 解析 JSON → done bool → verdict "done" or "continue"
```

任何异常路径都 fail-open 到 `continue`——保证 judge 故障不堵死 loop。

**JSON 解析容错**（goals.py:223-265）：

1. 优先 `json.loads(整段)`
2. 失败时用 `_JSON_OBJECT_RE = r"\{.*?\}"` 抽 first JSON object
3. 兼容 `done` 字段为字符串 (`"true"`/`"yes"`/`"done"`) 的情况
4. 都解析失败 → 返回 `(False, "judge reply was not JSON: ...")`

## 主循环 — `evaluate_after_turn`

`GoalManager.evaluate_after_turn`（goals.py:441-518）—— 每次 turn 结束后调用：

```python
# 简化伪代码
def evaluate_after_turn(self, last_response, *, user_initiated=True):
    if state.status != "active":
        return {"should_continue": False, "verdict": "inactive", ...}

    state.turns_used += 1   # user 输入和 continuation 都算预算
    verdict, reason = judge_goal(state.goal, last_response)

    if verdict == "done":
        state.status = "done"
        return {"should_continue": False, "message": "✓ Goal achieved: ..."}

    if state.turns_used >= state.max_turns:
        state.status = "paused"
        state.paused_reason = "turn budget exhausted (...)"
        return {"should_continue": False, "message": "⏸ Goal paused — ..."}

    return {
        "should_continue": True,
        "continuation_prompt": self.next_continuation_prompt(),
        "verdict": "continue",
        "message": "↻ Continuing toward goal (...): ..."
    }
```

`user_initiated` 参数仅作语义标注——**两种 turn 都计入预算**（注释 goals.py:450-451）。

## 集成点

### CLI（`cli.py:7046-7140`）

`/goal` 命令在斜杠 dispatch 里被识别，绑定 `GoalManager(session_id=current_session_id, default_max_turns=cfg.goals.max_turns)`。

子命令：
- 裸 `/goal` 或 `/goal status` → `mgr.status_line()`
- `/goal pause` / `/goal resume` / `/goal clear`
- 其他文本 → `mgr.set(text)` —— 设置后**立即把 goal 文本作为下一个 user input** 投喂给 agent

### Gateway（`gateway/run.py:7648-7790`）

同样的 `_handle_goal_command`。设置新 goal 时通过 `_enqueue_fifo(_quick_key, kickoff_event, adapter)` 把 goal 文本立刻塞进消息队列——agent 下一 turn 就开干。

中途控制（`gateway/run.py:4779-4788`）：agent 跑动中允许 `/goal status / pause / clear`（仅 inspection），但 **`/goal <new_text>` 在跑动中被拒绝**——必须先 `/stop` 或等结束。

后置评判（`gateway/run.py:5256+`）：每次 turn 完成后调 `evaluate_after_turn`。返回 `should_continue=True` 时把 `continuation_prompt` enqueue 回 FIFO。

## Status 行格式

`GoalManager.status_line`（goals.py:374-386）：

| 状态 | 行 |
|------|-----|
| 无 goal | `No active goal. Set one with /goal <text>.` |
| active | `⊙ Goal (active, 3/20 turns): <goal>` |
| paused | `⏸ Goal (paused, 3/20 turns — user-paused): <goal>` |
| done | `✓ Goal done (5/20 turns): <goal>` |

## 与其它机制对比

| | `/goal` | Background Review | delegate_task |
|---|---|---|---|
| 触发 | 用户显式 `/goal` | 后台计数器 | LLM 自主 tool call |
| 后台 | 主 session 同 turn | fork 子 agent | spawn 子 agent |
| 系统提示 | 不变 | 受限工具集 | 隔离系统提示 |
| 预算 | turn 数 | 单 fork | iteration / 并行 3 |
| 持久化 | SessionDB.state_meta | skill 文件 | 无 |
| Judge | 辅助模型 | rubric 评分 | parent 验收 |

## 配置

`config.yaml`：

```yaml
goals:
  max_turns: 20    # 默认 turn budget；GoalManager(default_max_turns=...) 默认值
```

辅助模型：通过 `auxiliary.goal_judge`（或 fallback 到通用辅助 client）。`get_text_auxiliary_client("goal_judge")`（goals.py:290）—— 见 [[auxiliary-client-architecture]] 多 provider 解析链。

## 注意事项

- **Judge 是付费模型调用**：每 turn 都判一次。turn budget 设过大可能花钱，所以默认 20。
- **Judge 是 fail-open**：辅助模型不可达就保持 continue —— 这意味着 judge **下线时 turn budget 是唯一 backstop**。
- **prompt cache 友好**：continuation 是普通 user message，不动系统提示——主 session 的 prefix cache 不被破坏。
- **新用户消息进入时**：从 user 消息开始的 turn 仍参与评判（goals.py:444-451）—— user 偶然完成 goal 也能识别。

## 来源

- 模块文档：`hermes_cli/goals.py:1-28`
- 数据类：`hermes_cli/goals.py:89-119`
- 持久化：`hermes_cli/goals.py:127-204`
- Judge：`hermes_cli/goals.py:223-332`
- GoalManager：`hermes_cli/goals.py:340-523`
- CLI 集成：`cli.py:7046-7140`
- Gateway 集成：`gateway/run.py:7648-7790`
