---
title: Goal Loop —— `/goal` Ralph 风格判官循环
created: 2026-05-14
updated: 2026-05-14
type: concept
tags: [goal, ralph-loop, judge, session, architecture, module]
sources: [hermes_cli/goals.py, hermes_cli/commands.py]
version: v0.13.0
---

# Goal Loop — `/goal` 持久目标 + 判官循环

## 概述

v0.13.0 把 *Ralph 循环* 升级为 first-class 原语：用户用 `/goal <text>` 设定持久目标，agent 在每个 turn 之后由辅助模型 *judge* 评判是否完成；未完成则注入续转 prompt 让 agent 继续。budget 用完、用户 pause / clear、或用户发新消息时退出（新消息抢占）。

**核心承诺**：

- **不改 system prompt，不改 toolset** → prompt cache 持续命中
- **judge 失败 fail-OPEN** → 续转，turn budget 是最后保险
- 用户新消息总是优先于续转 prompt
- 与会话 lifecycle 共享 lifetime：state 落 SessionDB `state_meta`，`/resume` 时无缝继承

## 文件清单

| 文件 | 行数 | 角色 |
|------|------|------|
| `hermes_cli/goals.py` | 722 | `GoalManager` + `GoalState` + 判官循环 |
| `hermes_cli/commands.py:105-108` | — | `/goal` + `/subgoal` 注册 |

## 数据结构

`GoalState`（`hermes_cli/goals.py:130`）：

```python
@dataclass
class GoalState:
    goal: str
    status: str = "active"              # active | paused | done | cleared
    turns_used: int = 0
    max_turns: int = DEFAULT_MAX_TURNS  # 20
    created_at: float = 0.0
    last_turn_at: float = 0.0
    last_verdict: Optional[str] = None  # "done" | "continue" | "skipped"
    last_reason: Optional[str] = None
    paused_reason: Optional[str] = None
    consecutive_parse_failures: int = 0
    subgoals: List[str] = field(default_factory=list)
```

**持久化**：SessionDB `state_meta` 表，key 为 `goal:<session_id>`（`_meta_key()` line 194）。

## 续转 prompt 模板

不带 subgoals（`CONTINUATION_PROMPT_TEMPLATE` line 62）：

```
[Continuing toward your standing goal]
Goal: {goal}

Continue working toward this goal. Take the next concrete step.
If you believe the goal is complete, state so explicitly and stop.
If you are blocked and need input from the user, say so clearly and stop.
```

带 subgoals（`CONTINUATION_PROMPT_WITH_SUBGOALS_TEMPLATE` line 73）：含 subgoals 编号列表 + 要求"complete the goal AND all additional criteria"。

> 关键设计：续转 prompt 作为 **普通 user message** 追加进会话——*不*改写 system prompt，*不*换 toolset。这让 prompt cache 在整个 Ralph 循环中持续命中。

## 判官（judge）

辅助模型，独立于主 session。系统 prompt（`JUDGE_SYSTEM_PROMPT` line 86）严格要求单行 JSON：

```json
{"done": true|false, "reason": "<one-sentence rationale>"}
```

判官输入：goal 文本（必要时含 subgoals block）+ agent 最近一次回复的 `_JUDGE_RESPONSE_SNIPPET_CHARS = 4000` 字符片段。

**DONE 的判断**（system prompt 直引）：

- 回复显式确认完成
- 回复明确展示最终交付物
- 回复说明目标 *不可达 / blocked / 需要用户输入* —— 算 DONE 但 reason 描述 block

含 subgoals 时（`JUDGE_USER_PROMPT_WITH_SUBGOALS_TEMPLATE` line 107）：每条 numbered criterion 必须找到 *具体证据*（文件片段、输出行、命令结果），泛化短语如 "all requirements met" 一律视为 NOT done。

## 容错链

### Fail-OPEN 哲学

判官失败（API error / transport error）→ verdict = `continue`，避免 broken judge wedge 进度。Turn budget 是最后保险。

### Parse-failure auto-pause

`DEFAULT_MAX_CONSECUTIVE_PARSE_FAILURES = 3`（line 56）—— 连续 3 次空回复 / 非 JSON 回复后 auto-pause，提示用户检查 `goal_judge` 配置。设计目标是防小模型（如 deepseek-v4-flash）无法遵守判官的 JSON 契约时把整个 turn budget 烧掉。

API / transport 错误**不**计入 parse failure（那些是 transient）—— 这是与 judge response 内容失败的关键区分。

### 用户消息抢占

任何真实的用户消息进来时：

- 抢占当前续转 prompt
- pause 本 turn 的循环
- turn 结束后**仍然**重新 judge —— 如果用户消息恰好让 agent 完成 goal，judge 会输出 done 自然退出

## `/subgoal` 中途追加标准

`/subgoal <text>`：把 criterion 追加到 `GoalState.subgoals`。

- `render_subgoals_block()` 渲染为 numbered list
- 续转 prompt 与判官 prompt **都**呈现 subgoals —— agent 看到要做什么，judge 评判要求都满足
- backwards-compatible：旧的 state_meta 行没有 `subgoals` 字段，`from_json()` 默认空 list

子命令：

```
/subgoal <text>          # 追加
/subgoal remove N        # 删除第 N 个
/subgoal clear           # 清空
```

> 历史插曲：v0.13.0 主线初版 `/goal checklist + /subgoal` 在 `3e7145e0b` (2026-05-11) 被 revert，最终 `/subgoal` 在 `8f19078c6` (2026-05-13) 重新落地。当前 main 是落地版本。

## 命令注册

`hermes_cli/commands.py:105-108`：

```python
CommandDef("goal",    "Set a standing goal Hermes works on across turns until achieved",
           "Session", args_hint="[text | pause | resume | clear | status]"),
CommandDef("subgoal", "Add or manage extra criteria on the active goal",
           "Session", args_hint="[text | remove N | clear]"),
```

CLI / 网关共享同一命令。

## Lifecycle

```
/goal write a blog post about LLM caching
  ↓
GoalState created, status=active, turns_used=0
  ↓
Agent 处理用户初始消息，回复
  ↓
Judge:  {"done": false, "reason": "no draft yet"}
  ↓
注入续转 prompt（user message）
  ↓
Agent 写第一稿，回复
  ↓
Judge:  {"done": false, "reason": "missing examples"}
  ↓
... 直到 done 或 turn budget 用完
  ↓
status → done | paused(budget) | cleared
```

## 集成点

- **CLI**：`hermes chat` 主循环在 turn 结束时调用 `GoalManager.maybe_continue()`，决定是否注入续转 prompt
- **Gateway runner**：同一 `GoalManager` 被 gateway runner wire 进去，messaging 平台同样支持 `/goal`
- **零硬依赖 `cli.HermesCLI` 或 gateway 模块**：单元可测，docstring 明确声明

## 已知局限

- `/goal` 不会改 toolset —— 若用户想约束 agent "只能用 web_search"，得用 `/tools disable` 单独操作
- judge 上下文限于 4000 字符片段 —— 长报告型回复可能被截断；release notes 指可调 `goal_judge.snippet_chars`
- 默认 `max_turns=20`：可作 `/goal --max-turns N` 覆盖

## 相关页面

- [[agent-loop-and-prompt-assembly]] — 主 agent loop；续转 prompt 是普通 user message
- [[multi-agent-architecture]] — Goal loop 与 Delegate / MoA / Background Review 不同：它**不 fork**，全程在主 session 里跑
- [[prompt-caching-optimization]] — 为什么续转 prompt 不动 system prompt
- [[session-search-and-sessiondb]] — `state_meta` 表的 `/resume` 接续

## 相关文件

- `hermes_cli/goals.py` — `GoalManager` / `GoalState` / 判官 / `continue` 决策
- `hermes_cli/commands.py` — `/goal` `/subgoal` 注册
