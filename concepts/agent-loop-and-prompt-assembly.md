---
title: Agent Loop and Prompt Assembly
created: 2026-04-07
updated: 2026-05-18
type: concept
tags: [agent-loop, prompt-builder, architecture, component]
sources: [hermes-agent 源码分析 2026-04-07, 2026-05-15 增量验证]
---

# Agent Loop and Prompt Assembly

## AIAgent 核心循环

`AIAgent` 类仍定义在 `run_agent.py:326`，但 `run_agent.py`（约 4096 行）已不再是单块实现：核心逻辑已抽到 `agent/` 子模块。`__init__`（`run_agent.py:349`）是一个 5 行转发器，委派给 `agent/agent_init.py` 的 `init_agent()`（1469 行）；`run_conversation`（`run_agent.py:3840`）同样是转发器，委派给 `agent/conversation_loop.py` 的 `run_conversation()`（4018 行）。

```python
# run_agent.py — AIAgent 类（对话循环本体已抽取到 agent/conversation_loop.py）
class AIAgent:
    def __init__(self,
        model: str = "",  # 默认空字符串，运行时解析（run_agent.py:358）
        max_iterations: int = 90,
        enabled_toolsets: list = None,
        disabled_toolsets: list = None,
        quiet_mode: bool = False,
        save_trajectories: bool = False,
        platform: str = None,           # "cli", "telegram", etc.
        session_id: str = None,
        skip_context_files: bool = False,
        skip_memory: bool = False,
        # ... 更多参数
    ): ...

    def chat(self, message: str) -> str:
        """简单接口 — 返回最终响应字符串"""

    def run_conversation(self, user_message, system_message=None,
                         conversation_history=None, task_id=None) -> dict:
        """完整接口 — 返回 dict {final_response, messages}"""
```

## 对话循环

对话循环本体位于 `agent/conversation_loop.py:598`：

```python
while (api_call_count < agent.max_iterations and agent.iteration_budget.remaining > 0) or agent._budget_grace_call:
    # 预算耗尽后仍允许一次性 grace 迭代（_budget_grace_call）
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=tool_schemas
    )
    if response.tool_calls:
        for tool_call in response.tool_calls:
            result = handle_function_call(tool_call.name, tool_call.args, task_id)
            messages.append(tool_result_message(result))
        api_call_count += 1
    else:
        return response.content  # 最终响应
```

- `_budget_grace_call` 是一次性的宽限迭代：预算耗尽后仍允许模型再调用一次，之后循环退出
- `iteration_budget.consume()` 在循环体**内部**单独调用（`conversation_loop.py:619`），用于原子地检查并递减剩余预算——而非在 while 条件里

- 完全同步执行
- 消息格式遵循 OpenAI 标准：`{"role": "system/user/assistant/tool", ...}`
- 推理内容存储在 `assistant_msg["reasoning"]`

## 每轮文件变更校验页脚（2026-05-15）

某些模型会在一轮内发起多个并行 `patch` / `write_file` 调用，部分失败
（如 `Could not find old_string`），却在最终文本响应里声称"已修改全部
文件"。为结构性地杜绝这种过度声称，Agent 在每轮结束时追加一个**文件变更
校验页脚**（commit `c594a23`，#24498）。

### 工作方式

- **纯事后检查**：只读取本轮的工具结果，不发起新的 LLM 调用、不向历史
  注入合成消息（保持 prefix cache），也不改动工具参数派发。
- `_record_file_mutation_result()` 在每个工具调用后被调用（`blocked`
  的调用不计入）。文件变更工具集由共享模块的 `FILE_MUTATING_TOOL_NAMES`
  定义 —— 即 `{"write_file", "patch"}`（commit `c3094b4` 把它抽到
  `agent/tool_result_classification.py`，与 `file_mutation_result_landed()`
  助手一起）。
- 按路径维护本轮状态字典 `_turn_failed_file_mutations`：首个失败胜出
  （first-error-wins），对同一路径的**后续成功写入会清除该失败条目**，
  因此单文件重试恢复不会被误报。
- `_extract_file_mutation_targets()` 从工具参数解析受影响路径，覆盖
  `write_file`、`patch-replace`、`patch-v4a`（单文件与多文件）。
- 同时接入 `_execute_tool_calls_concurrent` 与
  `_execute_tool_calls_sequential`，并行批量补丁与逐个编辑都被覆盖。

### 页脚渲染与时机

`_format_file_mutation_failure_footer()` 渲染最多 10 条路径
（每条带首个错误预览），多余的折叠为 `… and N more`：

```text
⚠️ File-mutation verifier: N file(s) were NOT modified this turn despite
any wording above that may suggest otherwise. Run `git status` or
`read_file` to confirm.
  • path/to/file — [patch] Could not find old_string
```

页脚在 Agent 循环退出后、`transform_llm_output` / `post_llm_call` 插件
钩子运行**之前**追加，因此插件仍能看到并修改这段增强后的文本。仅当本轮
存在真实文本响应且用户未中断时才追加。

**开关**：`display.file_mutation_verifier`（bool，默认 true），
`HERMES_FILE_MUTATION_VERIFIER` 环境变量可覆盖配置。

## 系统提示构建

`AIAgent._build_system_prompt()`（`run_agent.py:2156`）现在只是转发器 → `agent/system_prompt.py` 的 `build_system_prompt`。真正的组装由 `build_system_prompt_parts`（`agent/system_prompt.py:60`）完成：它返回一个含**三个有序层级**的 dict，在 `system_prompt.py:299` 用 `"\n\n".join(...)` 拼成完整 system prompt。三层的顺序是为最大化上游 prefix cache 命中率刻意设计的——越稳定的内容越靠前。

1. **`stable` 层**（进程/会话内不变）— SOUL.md / `DEFAULT_AGENT_IDENTITY` → `HERMES_AGENT_HELP_GUIDANCE`（指向 hermes-agent skill 与文档的指针）→ 工具指导（memory / session_search / skills / kanban）→ computer-use 指导 → nous 订阅块 → 工具使用强制指导 + Google/OpenAI 模型操作指导 → Skills 索引 → alibaba 模型身份补丁 → 环境提示 → 平台提示
2. **`context` 层**（随 cwd 变化）— 调用方传入的 `system_message` → 项目上下文文件（`.hermes.md → AGENTS.md → CLAUDE.md → .cursorrules`，first match wins）
3. **`volatile` 层**（每会话/每轮变化，从不缓存）— MEMORY 快照 → USER PROFILE 快照 → 外部 Memory Provider 块 → 时间戳行（含 Session ID / Model / Provider）

**缓存机制**：系统提示在会话内只构建一次（`self._cached_system_prompt`），只在上下文压缩后才重建（`invalidate_system_prompt`，`system_prompt.py:302`，重建时会从磁盘重新加载 memory），确保每轮对话复用同一份 → LLM prefix cache 命中率最大化。

**时间戳为日期精度**：时间戳行使用 `now.strftime('%A, %B %d, %Y')`（`system_prompt.py:267`），只精确到**日期**而非分钟。这是为 prefix-cache 稳定性的刻意改动（commit 4a3f13b）——分钟级精度会在每次重建时使 prefix-cache KV 失效；模型需要精确时间时可通过工具查询。

**记忆冻结模式**：`volatile` 层的 MEMORY.md / USER.md 内容是**加载时的快照**，即使对话中模型写入新记忆也不会反映到当前会话的 system prompt 里——下次会话（或压缩后重建）才生效。这是为保护 prefix cache 的刻意设计。

## 平台提示 (PLATFORM_HINTS)

为不同消息平台注入特定指导：

| 平台 | 关键指导 |
|------|----------|
| `telegram` | 不使用 markdown，MEDIA: 路径发送文件 |
| `discord` | 支持 markdown，文件作为附件 |
| `whatsapp` | 不使用 markdown，原生媒体 |
| `slack` | 文件作为附件 |
| `signal` | 不使用 markdown，纯文本 |
| `email` | 清晰结构化，适合邮件 |
| `cron` | 无用户在场，完全自主执行 |
| `cli` | 终端可渲染的纯文本 |
| `sms` | 纯文本，~1600 字符限制 |

## 执行指导

### 通用工具使用强制指导

```text
# Tool-use enforcement
You MUST use your tools to take action — do not describe what you would do
or plan to do without actually doing it.
```

适用于模型（`prompt_builder.py` 中的 `TOOL_USE_ENFORCEMENT_MODELS`）：
`gpt`、`codex`、`gemini`、`gemma`、`grok`、`glm`。

> **2026-05-15 新增 GLM**（commit `afa5b81`）：GLM 系模型
> （`z-ai/glm-4.5-air`、`z-ai/glm-4.5-flash` 等）同样表现出
> "describe-instead-of-call" 故障模式 —— kanban dispatcher 派发的免费档
> GLM worker 会以 rc=0 干净退出却不调用 `kanban_complete` / `kanban_block`，
> 触发 "protocol violation"。把 `glm` 加入强制列表后即注入工具使用强制指导。

### OpenAI 模型额外指导

`OPENAI_MODEL_EXECUTION_GUIDANCE` 适用于 `gpt` / `codex` 模型，**同样也应用于 xAI `grok` 模型**（`system_prompt.py:162`）——grok 表现出相同的失败模式（未调用工具就声称完成、用替代方案而非现有工具、回复计划而非执行）。

```xml
<tool_persistence>
- Use tools whenever they improve correctness
- Do not stop early when another tool call would improve the result
- Keep calling tools until: task complete AND verified
</tool_persistence>

<prerequisite_checks>
- Check whether prerequisite discovery steps are needed
- Do not skip prerequisite steps
</prerequisite_checks>

<verification>
- Correctness: does output satisfy every requirement?
- Grounding: are factual claims backed by tool outputs?
- Formatting: does output match requested format?
- Safety: confirm scope before executing side effects
</verification>
```

### Google 模型操作指导

- 始终使用绝对路径
- 先验证再修改（read_file/search_files）
- 依赖检查（不假设库可用）
- 并行工具调用
- 非交互式命令（-y, --yes 标志）

## 上下文文件注入

**两条独立加载路径**：

| 文件 | 位置 | 搜索范围 |
|------|------|---------|
| **SOUL.md** | `~/.hermes/SOUL.md` | 全局唯一路径，独立加载（Agent 身份槽） |
| **.hermes.md** | cwd 向上到 git root | 项目级配置，优先级 1 |
| **AGENTS.md** | 仅 cwd | 代码库开发指南，优先级 2 |
| **CLAUDE.md** | 仅 cwd | 兼容 Anthropic 格式，优先级 3 |
| **.cursorrules** | 仅 cwd | 兼容 Cursor 格式，优先级 4 |

**项目上下文文件是互斥的**（first match wins）——找到第一个就停，后面的不加载。SOUL.md 不参与这个竞争，它始终与项目文件共存。

**控制加载的方式**：
- `TERMINAL_CWD` — Gateway 模式下，决定在哪个目录查找项目文件。默认 `Path.home()`
- `skip_context_files=True` — 完全跳过项目文件加载（子 Agent 常用）
- `build_context_files_prompt(skip_soul=True)` — 跳过 SOUL.md（已作为身份槽加载时使用）

扫描注入内容的安全威胁：
```python
_CONTEXT_THREAT_PATTERNS = [
    (r'ignore\s+(previous|all|above|prior)\s+instructions', "prompt_injection"),
    (r'do\s+not\s+tell\s+the\s+user', "deception_hide"),
    (r'system\s+prompt\s+override', "sys_prompt_override"),
    (r'curl\s+[^\n]*\$?\w*(KEY|TOKEN|SECRET)', "exfil_curl"),
    (r'cat\s+[^\n]*(\.env|credentials)', "read_secrets"),
    # ... 更多
]
```

## 技能索引注入

技能索引是**系统提示的一部分**，由 `build_system_prompt_parts()` 调用 `build_skills_system_prompt()` 拼入 `stable` 层，与身份、工具指导、平台提示等一起组成完整系统提示。

系统提示在会话内只构建一次（缓存在 `self._cached_system_prompt`），仅在上下文压缩后才重建，保证每轮对话复用同一份 → LLM prefix cache 命中率最大化。

## Skills Prompt 两层缓存

构建技能索引文本需要扫描 `~/.hermes/skills/` 下所有文件并解析 frontmatter，为避免重复文件 I/O，使用两层缓存加速：

| 层级 | 存储 | 命中条件 | 失效条件 |
|------|------|----------|----------|
| Layer 1 | 内存 LRU（`OrderedDict`，最多 8 条） | cache_key 匹配（skills_dir + tools + toolsets + platform） | 进程重启 |
| Layer 2 | 磁盘快照（`.skills_prompt_snapshot.json`） | mtime + size manifest 校验通过 | 技能文件变更 |

两层都未命中时，执行全量文件系统扫描 → 写回磁盘快照 + 写入内存缓存。

**注意区分**：此缓存优化的是"生成索引文本"的 I/O 速度，与 LLM API 层的 prefix cache（复用已计算的 token）是不同层面。

## Per-turn 文件修改验证 footer（v0.12.0+，PR #24498，c594a23）

每一轮 agent 调用结束时，Hermes 给 user 反方向附一段 verifier footer，列出**本轮内 write_file / patch 失败但 agent 没自己修好的文件**。模型由此能在下一轮立刻看到自己留的烂摊子，不会"忘记修"。

```python
# run_agent.py:5331-5395
def _record_file_mutation_result(self, tool_name, args, result, is_error):
    """write_file / patch 的成功/失败状态写入 self._turn_failed_file_mutations。

    - tool_name 不在 FILE_MUTATING_TOOL_NAMES → 跳过（统一从 agent/tool_result_classification 导入，c3094b4）
    - 失败 → 第一次失败的 error preview 存进 {path: {error_preview, tool}}
    - 同一 path 后续成功 → state.pop(path) 清掉
    - 同一 path 后续不同错误 → 不覆盖第一次的 error（避免噪声）
    """
```

**判定"成功"** 走 `file_mutation_result_landed(tool_name, result)`——并非靠 `is_error` flag，而是看 tool 结果里的 landed 状态。`fix(da0ddbf)` 起，landed mutation 即使 tool 报错也算成功（compaction 跑 patch 时 tool result 拿不到，但变更已落盘）。

**开关**：

| 来源 | Key | 默认 |
|------|-----|------|
| Config | `display.file_mutation_verifier` (bool) | `True` |
| Env | `HERMES_FILE_MUTATION_VERIFIER` (0/1/false/true/no/off) | — |

env > config > 默认。env 不接受时取 config，config 没设时默认 on。

**与 LSP 协同**（PR #24168，83b9389）：`write_file` / `patch` 落盘后跑 LSP 语义诊断（pyright / tsc / shellcheck），把 diagnostics 作为单独 channel 返回给 agent（不是错误）。配合 in-process linter（PR #20191，5168226，覆盖 JSON / YAML / TOML / Python）形成两层 post-write 检查：
1. **delta lint**（in-process）：写完立刻 lint，差量 diagnostic 直接附在 tool result 里
2. **LSP semantic**（external）：跑真正的 language server，结果作为 `lsp_diagnostics` 字段

## 角色切换

某些模型使用 `developer` 角色而不是 `system` 角色：

```python
DEVELOPER_ROLE_MODELS = ("gpt-5", "codex")
# 在 API 边界 _build_api_kwargs() 中切换
```

## 相关页面

- [[agent-loop-and-prompt-assembly]] — AIAgent 核心对话循环类（本页）
- [[prompt-builder-architecture]] — 系统提示模块化构建架构
- [[context-compressor-architecture]] — 上下文压缩与摘要机制

## 相关文件

- `run_agent.py` — AIAgent 类与转发器
- `agent/conversation_loop.py` — 对话循环本体
- `agent/tool_executor.py` — 工具执行
- `agent/system_prompt.py` — 系统提示三层组装（`build_system_prompt_parts`）
- `agent/prompt_builder.py` — 系统提示构建块（`load_soul_md`、`build_skills_system_prompt`、`build_context_files_prompt`、`build_environment_hints` 等），不再负责整体组装
- `model_tools.py` — 工具编排
- `agent/context_compressor.py` — 上下文压缩算法
- `agent/prompt_caching.py` — Anthropic prompt 缓存
