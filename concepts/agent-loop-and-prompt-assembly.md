---
title: Agent Loop and Prompt Assembly
created: 2026-04-07
updated: 2026-04-07
type: concept
tags: [agent-loop, prompt-builder, architecture, component]
sources: [hermes-agent 源码分析 2026-04-07]
---

# Agent Loop and Prompt Assembly

## AIAgent 核心循环

```python
# run_agent.py
class AIAgent:
    def __init__(self,
        model: str = "anthropic/claude-opus-4.6",
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

```python
while api_call_count < self.max_iterations and self.iteration_budget.remaining > 0:
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

- 完全同步执行
- 消息格式遵循 OpenAI 标准：`{"role": "system/user/assistant/tool", ...}`
- 推理内容存储在 `assistant_msg["reasoning"]`

## 系统提示构建

`AIAgent._build_system_prompt()` 按固定顺序拼接 `prompt_parts`，最终 `"\n\n".join(prompt_parts)` 返回完整 system prompt。实测结构见 [[prompt-builder-architecture]]，按这个顺序组装：

1. **SOUL.md** — Agent 身份（`~/.hermes/SOUL.md`，不存在则用 `DEFAULT_AGENT_IDENTITY`）
2. **工具使用强制指导** — 按模型族过滤
3. **模型特定执行指导** — OpenAI/Google 等专用
4. **用户/Gateway 系统消息** — 若 `run_conversation` 传入 `system_message`
5. **Memory 使用指导** — 告诉模型如何用 memory 工具
6. **MEMORY 快照** — `~/.hermes/memories/MEMORY.md`（冻结）
7. **USER PROFILE 快照** — `~/.hermes/memories/USER.md`（冻结）
8. **外部 Memory Provider 块** — mem0/honcho/holographic 等，若启用
9. **Skills 索引** — 扫描 `~/.hermes/skills/` 生成
10. **项目上下文文件** — `.hermes.md → AGENTS.md → CLAUDE.md → .cursorrules`（first match wins）
11. **会话元数据** — 时间戳、Model、Provider、Session ID
12. **平台提示** — `PLATFORM_HINTS[platform]`
13. **会话上下文** — Gateway 注入的来源、Home Channel、投递选项

**缓存机制**：系统提示在会话内只构建一次（`self._cached_system_prompt`），只在上下文压缩后才重建，确保每轮对话复用同一份 → LLM prefix cache 命中率最大化。

**记忆冻结模式**：MEMORY.md / USER.md 在第 6-7 层的内容是**加载时的快照**，即使对话中模型写入新记忆也不会反映到当前会话的 system prompt 里——下次会话才生效。这是为保护 prefix cache 的刻意设计。

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

适用于模型：`gpt`, `codex`, `gemini`, `gemma`, `grok`

### OpenAI 模型额外指导

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

技能索引是**系统提示的一部分**，由 `_build_system_prompt()` 调用 `build_skills_system_prompt()` 拼入 `prompt_parts`，与身份、记忆、上下文文件等一起组成完整系统提示。

系统提示在会话内只构建一次（缓存在 `self._cached_system_prompt`），仅在上下文压缩后才重建，保证每轮对话复用同一份 → LLM prefix cache 命中率最大化。

## Skills Prompt 两层缓存

构建技能索引文本需要扫描 `~/.hermes/skills/` 下所有文件并解析 frontmatter，为避免重复文件 I/O，使用两层缓存加速：

| 层级 | 存储 | 命中条件 | 失效条件 |
|------|------|----------|----------|
| Layer 1 | 内存 LRU（`OrderedDict`，最多 8 条） | cache_key 匹配（skills_dir + tools + toolsets + platform） | 进程重启 |
| Layer 2 | 磁盘快照（`.skills_prompt_snapshot.json`） | mtime + size manifest 校验通过 | 技能文件变更 |

两层都未命中时，执行全量文件系统扫描 → 写回磁盘快照 + 写入内存缓存。

**注意区分**：此缓存优化的是"生成索引文本"的 I/O 速度，与 LLM API 层的 prefix cache（复用已计算的 token）是不同层面。

## 角色切换

某些模型使用 `developer` 角色而不是 `system` 角色：

```python
DEVELOPER_ROLE_MODELS = ("gpt-5", "codex")
# 在 API 边界 _build_api_kwargs() 中切换
```

## 相关页面

- [[aiagent-class]] — AIAgent 核心对话循环类
- [[prompt-builder-architecture]] — 系统提示模块化构建架构
- [[context-compressor-architecture]] — 上下文压缩与摘要机制

## 相关文件

- `run_agent.py` — AIAgent 类实现
- `agent/prompt_builder.py` — 系统提示组装（959 行）
- `model_tools.py` — 工具编排
- `agent/context_compressor.py` — 上下文压缩
- `agent/prompt_caching.py` — Anthropic prompt 缓存
