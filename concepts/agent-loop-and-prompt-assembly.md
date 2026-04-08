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

`AIAgent._build_system_prompt()` 组装多个组件：

```python
def _build_system_prompt(self) -> str:
    pieces = []
    
    # 1. Agent 身份
    pieces.append(DEFAULT_AGENT_IDENTITY)
    
    # 2. 平台提示（如 "You are on Telegram..."）
    if self.platform in PLATFORM_HINTS:
        pieces.append(PLATFORM_HINTS[self.platform])
    
    # 3. SOUL.md / 个性文件
    # 4. 上下文文件（.hermes.md, AGENTS.md 等）
    # 5. 记忆（MEMORY.md + USER.md）
    # 6. 技能索引
    # 7. 行为指导
    # 8. 临时提示（如 TTS 模式提示）
    
    return "\n\n".join(pieces)
```

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

发现顺序：
1. 当前工作目录向上查找
2. 到 git 仓库根目录为止
3. 查找 `.hermes.md` 或 `HERMES.md`

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

技能以**用户消息**形式注入（不是系统提示），以保持 prompt caching 有效：

```python
# 技能注入为工具调用后的用户消息
# 这样不会破坏系统提示的 prefix cache
```

## Skills Prompt 缓存

```python
_SKILLS_PROMPT_CACHE: OrderedDict[tuple, str] = OrderedDict()
_SKILLS_PROMPT_CACHE_MAX = 8
_SKILLS_PROMPT_CACHE_LOCK = threading.Lock()
```

- 内存缓存最多 8 个条目
- 使用 mtime/size manifest 检测技能文件变更
- 磁盘快照持久化（`.skills_prompt_snapshot.json`）
- 技能文件变更时自动失效

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
