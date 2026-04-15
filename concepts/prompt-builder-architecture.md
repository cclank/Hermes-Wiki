---
title: Prompt Builder 系统提示构建架构
created: 2026-04-08
updated: 2026-04-08
type: concept
tags: [architecture, module, component, agent, prompt-builder]
sources: [agent/prompt_builder.py]
---

# Prompt Builder — 系统提示构建架构

## 概述

Prompt Builder 位于 `agent/prompt_builder.py`（44KB/959行），负责**组装系统提示**——身份定义、平台提示、技能索引、上下文文件。所有函数无状态，由 `AIAgent._build_system_prompt()` 调用拼接各模块。

核心理念：**系统提示是模块化拼接的，每个组件可独立测试和替换。**

## 架构原理

### 提示组件层次（实测结构）

`_build_system_prompt()` 按固定顺序拼接 `prompt_parts` 数组，最终 `"\n\n".join(prompt_parts)` 返回完整 system prompt。基于实际 API 请求抓包（约 36K chars / 10K tokens）验证的真实结构：

```
系统提示 =
  ① Agent 身份 — SOUL.md（~/.hermes/SOUL.md，存在则用，否则 DEFAULT_AGENT_IDENTITY）
  ② 工具使用强制（TOOL_USE_ENFORCEMENT_GUIDANCE，按模型族过滤）
  ③ 模型特定执行指导（OpenAI/Google 等专用，按模型族过滤）
  ④ 用户/Gateway 系统消息（若 run_conversation 传入 system_message）
  ⑤ Memory 指导（硬编码提示，告诉模型如何用 memory 工具）
  ⑥ MEMORY 快照 — ~/.hermes/memories/MEMORY.md（冻结，整会话不变）
  ⑦ USER PROFILE 快照 — ~/.hermes/memories/USER.md（冻结，整会话不变）
  ⑧ 外部 Memory Provider 块（mem0/honcho/holographic 等，若启用）
  ⑨ Skills 索引（build_skills_system_prompt，扫描 ~/.hermes/skills/）
  ⑩ 项目上下文文件（.hermes.md → AGENTS.md → CLAUDE.md → .cursorrules，first match wins）
  ⑪ 会话元数据（时间戳、Model、Provider、Session ID）
  ⑫ 平台提示（PLATFORM_HINTS，Telegram/Discord/CLI 等）
  ⑬ 会话上下文（Gateway 注入：来源、Home Channel、投递选项）
```

**关键点**：
- **SOUL.md 独立加载**，不参与"项目上下文文件"的 first-match-wins 竞争
- **记忆快照使用冻结模式**——system prompt 在会话内只构建一次并缓存（`self._cached_system_prompt`），仅在上下文压缩后才重建，保护 prefix cache
- **整个 system prompt 就是一条 message**（`role: "system"`），不是多个 message 拼接

### 上下文文件注入防护

```python
_CONTEXT_THREAT_PATTERNS = [
    (r'ignore\s+(previous|all|above|prior)\s+instructions', "prompt_injection"),
    (r'do\s+not\s+tell\s+the\s+user', "deception_hide"),
    (r'system\s+prompt\s+override', "sys_prompt_override"),
    (r'disregard\s+(your|all|any)\s+(instructions|rules|guidelines)', "disregard_rules"),
    (r'bypass_restrictions', ...),
    (r'curl\s+.*\${?\w*(KEY|TOKEN|SECRET)', "exfil_curl"),
    (r'cat\s+[^\\n]*(\\.env|credentials)', "read_secrets"),
]

_CONTEXT_INVISIBLE_CHARS = {
    '\u200b', '\u200c', '\u200d', '\u2060', '\ufeff',  # 零宽字符
    '\u202a', '\u202b', '\u202c', '\u202d', '\u202e',  # 双向文本控制
}
```

**双重防护**：
1. **威胁模式检测**：10 种常见注入模式（忽略指令、隐藏行为、执行注入、密钥外泄等）
2. **不可见 Unicode 检测**：10 种零宽字符和双向文本控制字符（5 种零宽 + 5 种双向控制，可能用于视觉欺骗）

检测到威胁时：替换为 `[BLOCKED: filename contained potential prompt injection]`

## 核心组件

### 1. 上下文文件发现

**两条独立加载路径**：

```python
# 路径 A: SOUL.md — Agent 身份，固定路径，始终加载
load_soul_md()  → ~/.hermes/SOUL.md  (HERMES_HOME)

# 路径 B: 项目上下文文件 — 互斥，first match wins
project_context = (
    _load_hermes_md(cwd_path)    # .hermes.md / HERMES.md（向上遍历到 git root）
    or _load_agents_md(cwd_path) # AGENTS.md（仅 cwd）
    or _load_claude_md(cwd_path) # CLAUDE.md（仅 cwd）
    or _load_cursorrules(cwd_path) # .cursorrules / .cursor/rules/*.mdc（仅 cwd）
)
```

| 文件 | 位置 | 搜索范围 | 角色 |
|------|------|---------|------|
| **SOUL.md** | `~/.hermes/SOUL.md` | HERMES_HOME（全局唯一） | Agent 身份/人格，独立加载 |
| **.hermes.md** | cwd 向上到 git root | 遍历查找 | 项目级配置，优先级 1 |
| **AGENTS.md** | 仅 cwd | 不递归 | 代码库开发指南，优先级 2 |
| **CLAUDE.md** | 仅 cwd | 不递归 | 兼容 Anthropic 格式，优先级 3 |
| **.cursorrules** | 仅 cwd（含 `.cursor/rules/*.mdc`） | 不递归 | 兼容 Cursor 格式，优先级 4 |

**常见误区**：
- SOUL.md **不参与**项目上下文的优先级竞争——它是独立的身份槽
- 项目上下文文件是**互斥加载**（first match wins），不是"都加载"
- 如果当前 cwd 同时有 `.hermes.md` 和 `CLAUDE.md`，只有 `.hermes.md` 会被加载

**跳过机制**：
- `AIAgent(skip_context_files=True)` — 子 Agent 常用，避免继承父 Agent 的项目上下文
- 在不同目录下启动 Hermes（例如设 `TERMINAL_CWD=~`）— 天然跳过项目文件
- SOUL.md 也跳过：`build_context_files_prompt(skip_soul=True)` 当 SOUL.md 已作为身份槽加载时避免重复注入

**内容保护**：
- 每个文件内容上限 20,000 字符，超出自动头尾截断（`[...truncated...]`）
- 自动剥离 YAML frontmatter（结构化配置单独处理）
- 扫描威胁模式（见下节）

### 2. 技能索引与缓存

```python
_SKILLS_PROMPT_CACHE_MAX = 8
_SKILLS_PROMPT_CACHE: OrderedDict[tuple, str] = OrderedDict()

def build_skills_system_prompt(
    available_tools: set,
    available_toolsets: set,
    disabled_skills: set,
) -> str:
    """
    1. 扫描 skills 目录
    2. 解析每个 SKILL.md 的 frontmatter
    3. 检查平台兼容性 + 条件激活规则
    4. 构建技能清单提示
    5. 缓存结果（基于 mtime/size manifest）
    """
```

### 3. 技能快照持久化

```python
def _load_skills_snapshot(skills_dir: Path) -> Optional[dict]:
    """从磁盘加载快照，manifest 匹配则复用"""

def _write_skills_snapshot(skills_dir, manifest, skill_entries, category_descriptions):
    """原子写入快照（atomic_json_write）"""
```

**冷启动优化**：技能文件未变化时，直接从磁盘快照加载，无需重新解析所有 SKILL.md。

### 4. 技能条件激活

```python
def _skill_should_show(conditions, available_tools, available_toolsets):
    """
    fallback_for_toolsets: 主工具可用时隐藏（备用技能）
    fallback_for_tools: 主工具可用时隐藏
    requires_toolsets: 依赖的工具集不存在时隐藏
    requires_tools: 依赖的工具不存在时隐藏
    """
```

### 5. 平台提示

```python
PLATFORM_HINTS = {
    "telegram": "You are on Telegram. No markdown. MEDIA:/path for files...",
    "discord": "You are in Discord. MEDIA:/path for attachments...",
    "cli": "You are a CLI AI. Use simple text renderable in terminal.",
    "cron": "You are running as a cron job. No user present. Execute fully...",
    "whatsapp": "You are on WhatsApp. No markdown...",
    "slack": "You are in Slack...",
    "signal": "You are on Signal...",
    "email": "You are communicating via email. Plain text...",
    "sms": "You are communicating via SMS. ~1600 chars limit...",
}
```

### 6. 模型特定执行指导

#### OpenAI/GPT Codex 系列

```python
OPENAI_MODEL_EXECUTION_GUIDANCE = """
<tool_persistence>
- Use tools whenever they improve correctness
- Do not stop early
- If a tool returns empty, retry with different strategy
- Keep calling tools until task is complete AND verified
</tool_persistence>

<prerequisite_checks>
- Check prerequisite discovery before action
- Don't skip steps just because final action seems obvious
</prerequisite_checks>

<verification>
- Correctness: does output satisfy every requirement?
- Grounding: are claims backed by tool outputs?
- Formatting: does output match requested schema?
- Safety: confirm scope before side-effect operations
</verification>

<missing_context>
- Do NOT guess or hallucinate
- Use lookup tools for missing information
- Label assumptions explicitly
</missing_context>
"""
```

#### Gemini/Gemma 系列

```python
GOOGLE_MODEL_OPERATIONAL_GUIDANCE = """
- Absolute paths: always use absolute file paths
- Verify first: check file contents before changes
- Dependency checks: check package.json before importing
- Conciseness: keep text brief, focus on actions
- Parallel tool calls: batch independent operations
- Non-interactive: use -y, --yes flags
- Keep going: execute fully, don't stop with a plan
"""
```

### 7. Developer Role 切换

```python
DEVELOPER_ROLE_MODELS = ("gpt-5", "codex")
# OpenAI 新模型对 'developer' role 的指令遵循权重更高
# 在 API 边界自动切换，内部表示保持 "system" 一致
```

## 设计优越性

### 模块化优势

| 维度 | 单块提示 | 模块化 Prompt Builder |
|---|---|---|
| 测试 | 难以单元测试 | 每个组件独立测试 |
| 定制 | 需要全量替换 | 按平台/模型/技能动态组装 |
| 安全 | 注入难以检测 | 上下文文件独立扫描 |
| 维护 | 修改一处影响全局 | 各组件独立演化 |
| 缓存 | 无法缓存 | 技能索引可缓存 |

### 安全防护的优越性

传统的上下文文件注入没有防护。Prompt Builder 通过**多层检测**确保注入的内容不会改变 Agent 行为：
1. 威胁模式正则匹配
2. 不可见 Unicode 字符检测
3. 检测到威胁时替换为 BLOCKED 标记而非直接丢弃（让 Agent 知道有问题）

## 配置与操作

### 自定义 Agent 身份

创建 `~/hermes-agent/SOUL.md` 定义个性化身份。

### 项目级配置

在项目根创建 `.hermes.md`，内容会被注入到系统提示中。

### 禁用特定技能

```yaml
# config.yaml
skills:
  disabled: ["some-skill", "another-skill"]
```

## 与其他系统的关系

- [[tool-registry-architecture]] — 技能条件激活依赖可用工具集
- [[context-compressor-architecture]] — 压缩后的消息列表传给 prompt builder 重建提示
- [[memory-system-architecture]] — memory 指导是提示的一部分
- [[agent-loop-and-prompt-assembly]] — prompt builder 被 agent 循环调用
