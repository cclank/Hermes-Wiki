---
title: 持久化目标系统（/goal）
created: 2026-05-04
updated: 2026-05-04
type: concept
tags: [goals, ralph-loop, judge, auxiliary, session]
sources: [hermes_cli/goals.py, cli.py, gateway/run.py, tui_gateway/server.py]
---

# 持久化目标系统（/goal — Ralph Loop）

## 概述

`/goal <text>` 设置一个**跨轮持续推进**的目标。每个 turn 完成后，一个**辅助模型 judge** 判断 agent 的最后一条回复是否完成了目标。如果未完成，Hermes 自动喂一条**继续提示（continuation prompt）**回到同一会话，反复迭代直到：
- judge 判定 done
- turn 预算耗尽（默认 20）
- 用户 `/goal pause` / `/goal clear`
- 用户发了新消息（抢占，goal loop 暂停一轮）

源码：`hermes_cli/goals.py`（535 行）。

## 设计不变量

来自 `hermes_cli/goals.py:13-28` 的 docstring：

1. **continuation prompt 是普通 user 消息**——append 到会话，不改 system prompt，不切 toolset。**prompt cache 不失效**。
2. **judge 失败 fail-OPEN**：返回 `continue`。坏掉的 judge 不能卡住进度，turn 预算是兜底。
3. **真实用户消息抢占**：mid-loop 进来的 user message 优先处理，goal loop 暂停一轮（之后还会重新 judge）。
4. **零硬依赖**：不绑定 `cli.HermesCLI` 或 gateway runner——CLI、TUI、gateway 都注入同一个 `GoalManager`。

## 状态机

`GoalState`（`goals.py:90-119`）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `goal` | str | 用户目标文本 |
| `status` | str | `active` / `paused` / `done` / `cleared` |
| `turns_used` | int | 已用 turn 计数 |
| `max_turns` | int | turn 预算（默认 20） |
| `created_at` | float | 创建时间戳 |
| `last_turn_at` | float | 最后一轮时间戳 |
| `last_verdict` | str? | `done` / `continue` / `skipped` |
| `last_reason` | str? | judge 给的一句话理由 |
| `paused_reason` | str? | 自动暂停的原因（如预算耗尽） |

状态流转：

```
active ──[judge=done]──→ done
   │
   ├──[turns_used >= max_turns]──→ paused (paused_reason="turn budget exhausted")
   │
   ├──[user /goal pause]──→ paused (paused_reason="user-paused")
   │
   ├──[user /goal clear]──→ cleared
   │
paused ──[user /goal resume]──→ active (turns_used 重置为 0)
```

## 持久化

存到 SessionDB 的 `state_meta` 表，key = `goal:<session_id>`（`goals.py:127-128`）。`/resume` 自动恢复。

```python
def _meta_key(session_id: str) -> str:
    return f"goal:{session_id}"
```

`_DB_CACHE` 按 `hermes_home` 路径缓存 SessionDB 实例，避免每次 `/goal` 重开 DB（`goals.py:131-161`）。

## Judge 实现

### Prompts

**System prompt**（`goals.py:61-74`）：
> "You are a strict judge evaluating whether an autonomous agent has achieved a user's stated goal..."
>
> Goal is DONE only when:
> - 回复明确确认目标完成
> - 回复清楚展示最终交付物
> - 回复说明目标不可达 / 阻塞 / 需要用户输入（**视为 DONE**，原因是阻塞）

**Continuation prompt template**（`goals.py:52-58`）：
```
[Continuing toward your standing goal]
Goal: {goal}

Continue working toward this goal. Take the next concrete step.
If you believe the goal is complete, state so explicitly and stop.
If you are blocked and need input from the user, say so clearly and stop.
```

### Judge 调用

`judge_goal()`（`goals.py:268-332`）：
- 用 `agent.auxiliary_client.get_text_auxiliary_client("goal_judge")` 取**辅助模型客户端**——和主 session 完全隔离，不污染 prompt cache。
- `temperature=0`、`max_tokens=200`、超时 30s（`DEFAULT_JUDGE_TIMEOUT`）。
- 解析回复：先尝试整段 `json.loads`，失败则用正则 `_JSON_OBJECT_RE = re.compile(r"\{.*?\}", re.DOTALL)` 抠出第一个 JSON 对象。
- 任何异常都返回 `("continue", "...")`——**fail-open**。

### 输入截断

- goal 截到 2000 字符
- last_response 截到 4000 字符（`_JUDGE_RESPONSE_SNIPPET_CHARS`）

防止超长 prompt 把 judge 调用打爆。

## CLI 命令

`cli.py:7088-7152` 实现 `_handle_goal_command`：

| 子命令 | 行为 |
|--------|------|
| `/goal <text>` | 设新目标，立即把 goal 文本入队 `_pending_input`，直接开跑 |
| `/goal status` 或 bare `/goal` | 显示 `status_line()`：`⊙ Goal (active, 3/20 turns): <text>` |
| `/goal pause` | `paused_reason="user-paused"` |
| `/goal resume` | 重置 `turns_used=0`，`status=active` |
| `/goal clear` / `stop` / `done` | `status=cleared`，`_state=None` |

## 主循环挂钩

`cli.py:7154-7210` `_maybe_continue_goal_after_turn` 在每个 CLI turn 完成后调用：

1. 若没有 active goal → 返回。
2. **抢占检查**：`_pending_input.empty()` 为否（用户已排队新消息）→ 返回，让用户先走。
3. 提取最后一条 assistant 回复（多模态时拼 text/output_text 段）。
4. 调 `mgr.evaluate_after_turn(last_response, user_initiated=True)`：
   - 增加 `turns_used`
   - 调 judge
   - 根据 verdict 更新 status 并返回 decision dict
5. 打印 `decision["message"]`：
   - `done`: `✓ Goal achieved: <reason>`
   - `paused (budget)`: `⏸ Goal paused — N/M turns used. Use /goal resume to keep going...`
   - `continue`: `↻ Continuing toward goal (N/M): <reason>`
6. 若 `should_continue=True` → 把 `continuation_prompt` 入队 `_pending_input`。

## Gateway 集成

`gateway/run.py` 也通过 `GoalManager` 接入；TUI 走 `tui_gateway/server.py`（commit `d87fd9f`：`fix(goals): make /goal work in TUI and fix gateway verdict delivery`）。

## 配置

```yaml
# config.yaml
goals:
  max_turns: 20    # turn 预算（默认 20）
```

## 与其他系统的关系

| 系统 | 关系 |
|------|------|
| **Auxiliary Client** | judge 走 aux client，独立模型选择，不影响主 cache |
| **SessionDB** | goal state 持久化到 `state_meta`，`/resume` 自动接续 |
| **Compression** | continuation prompt 是普通 user message，照常进压缩流程 |
| **Memory / Skills** | 没有特殊耦合——goal 只是消息层的循环驱动 |

## 验证 PR

- `265bd59` `feat: /goal — persistent cross-turn goals (Ralph loop) (#18262)`
- `cf2b2d3` `docs: add Persistent Goals (/goal) feature page (#18275)`
- `d87fd9f` `fix(goals): make /goal work in TUI and fix gateway verdict delivery (#19209)`
- `0b76d23` `makes the Persistent Goals docs accessible in the docs nav (and llms.txt) (#18481)`

## 相关概念

- [[auxiliary-client-architecture]] — judge 调用的客户端路由
- [[session-search-and-sessiondb]] — `state_meta` 表持久化
- [[gateway-session-management]] — goal 在网关侧的会话绑定
