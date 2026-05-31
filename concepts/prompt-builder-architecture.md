---
title: Prompt Builder 系统提示构建架构
created: 2026-04-08
updated: 2026-05-31
type: concept
tags: [architecture, module, component, agent, prompt-builder, promptware-defense, prompt-size-diagnostic]
sources: [agent/prompt_builder.py, agent/system_prompt.py, tools/threat_patterns.py, hermes_cli/prompt_size.py]
---

# Prompt Builder — 系统提示构建架构

## 概述

Prompt Builder 位于 `agent/prompt_builder.py`（约 1456 行），提供**系统提示的组件构建器**——身份定义、平台提示、技能索引、上下文文件、环境提示。所有函数无状态。

实际的**组装编排层**是 `agent/system_prompt.py`（333 行）：`AIAgent._build_system_prompt()` 现在只是转发器，委派给 `system_prompt.py` 的 `build_system_prompt()`，后者才是真正的编排者，调用 prompt_builder 的各个组件构建器（`build_skills_system_prompt`、`build_context_files_prompt`、`build_environment_hints`、`PLATFORM_HINTS` 等）并拼接结果。`prompt_builder.py` 本身不再负责整体拼接，只提供单个组件。

核心理念：**系统提示是模块化拼接的，每个组件可独立测试和替换。**

## 架构原理

### 提示组件层次（实测结构）

`system_prompt.py` 的 `build_system_prompt_parts()` 产出一个**三层 dict**（`stable` / `context` / `volatile`），`build_system_prompt()` 用 `"\n\n"` 连接成完整 system prompt。基于实际 API 请求抓包（约 36K chars / 10K tokens）验证的真实结构：

```
系统提示 = stable + context + volatile（"\n\n" 连接）

stable（稳定层，会话内不变，最大化 prefix cache）=
  ① Agent 身份 — SOUL.md（~/.hermes/SOUL.md，存在则用，否则 DEFAULT_AGENT_IDENTITY）
  ② 工具使用强制（TOOL_USE_ENFORCEMENT_GUIDANCE，按模型族过滤）
  ③ 模型特定执行指导（OpenAI/Google 等专用，按模型族过滤）
  ④ Skills 索引（build_skills_system_prompt，扫描 ~/.hermes/skills/）
  ⑤ 环境提示（build_environment_hints）
  ⑥ 平台提示（PLATFORM_HINTS，Telegram/Discord/CLI 等）

context（上下文层）=
  ⑦ 用户/Gateway 系统消息（若 run_conversation 传入 system_message）
  ⑧ 项目上下文文件（.hermes.md → AGENTS.md → CLAUDE.md → .cursorrules，first match wins）

volatile（易变层）=
  ⑨ Memory 指导 + MEMORY 快照（~/.hermes/memories/MEMORY.md，冻结）
  ⑩ USER PROFILE 快照（~/.hermes/memories/USER.md，冻结）
  ⑪ 外部 Memory Provider 块（mem0/honcho/holographic 等，若启用）
  ⑫ 会话元数据（时间戳、Model、Provider、Session ID）
```

**关键点**：
- **SOUL.md 独立加载**，不参与"项目上下文文件"的 first-match-wins 竞争
- **记忆快照使用冻结模式**——system prompt 在会话内只构建一次并缓存（`self._cached_system_prompt`），仅在上下文压缩后才重建，保护 prefix cache
- **整个 system prompt 就是一条 message**（`role: "system"`），不是多个 message 拼接

### 上下文文件注入防护（2026-05-26 起：共享威胁模式库）

威胁正则与 invisible-unicode 集合自 2026-05-26（commit `0dee92df2`，PR #32269）起**迁移到统一模块** `tools/threat_patterns.py`（252 行），由 Prompt Builder / `MemoryStore.load_from_disk` / `tools/skills_guard.py` 三方共用。Prompt Builder 在上下文文件加载时调：

```python
from tools.threat_patterns import scan_for_threats

findings = scan_for_threats(content, scope="context")
if findings:
    content = f"[BLOCKED: {filename} contained potential prompt injection: {', '.join(findings)}]"
```

**Scope 三分**（详见 [[security-defense-system]]）：

- `"all"` — 经典 prompt injection / exfiltration（`ignore previous instructions` / `system prompt override` / `curl $KEY` 等），所有扫描器都用。
- `"context"`（**Prompt Builder 默认**）— 上面 + 角色扮演 / 身份覆盖 / C2 verbiage（`name yourself X` / `register as a node` / `heartbeat to` / `pull tasking` / `unset CLAUDE|HERMES` / `praxis|cobalt strike|sliver|brainworm`）。
- `"strict"` — 上面 + 持久化后门（`authorized_keys` / `update AGENTS.md`）+ hardcoded secret，仅 memory write / skills install 这类 user-mediated 路径用。

**模式哲学**："anchor on C2-specific vocabulary or unambiguous attack behavior, NOT on bossy English" —— `you must X` / `you are obligated to` 等普通指令性短语被显式拒绝，因 AGENTS.md / CLAUDE.md 自身存在大量合法 instructional 语句。Multi-word bypass 用 `(?:\\w+\\s+)*` 容许 `ignore all prior instructions` 等 dilution。

**不可见 Unicode** 扩展到 17 个 codepoint（`threat_patterns.INVISIBLE_CHARS`，line 116-137）：5 种零宽 + 3 种 invisible math operator + 9 种 directional embedding / override / isolate / BOM。命中即报 `invisible_unicode_U+XXXX` 编码点便于审计。

检测到威胁时：替换为 `[BLOCKED: filename contained potential prompt injection: <pattern_ids>]`。原始文件**不进入** system prompt。

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

## 2026-05-31 增量 — `hermes prompt-size` 诊断命令

PR #35276 / `61268ff7a`，关闭 #34667（"哪个块吃掉了我的 token budget"）。

**新模块** `hermes_cli/prompt_size.py`（153 行）：

| 入口 | 行号 | 用途 |
|---|---|---|
| `cmd_prompt_size(args)` | `:141` | CLI subparser handler |

**CLI 注册**：`hermes_cli/main.py:14467-14486` `prompt-size [--platform NAME] [--json]` subparser。

### 报告内容

对**新会话**的**固定 prompt budget** 做完整拆分：

- **System prompt total** —— `agent/prompt_builder.py.build_system_prompt()` 输出的总 token / byte 数
- **Skills index** —— 渐进式披露最外层 catalog 的尺寸（常是最大单块，see issue #34667）
- **Memory** —— `MEMORY.md` + 临时 ENV memories（含 frozen snapshot 状态）
- **User profile** —— `USER.md` 内容
- **Prompt tiers** —— 静态分层（Identity / Persona / Tools / Environment / Skill index / Memory / User）逐层 byte 计数
- **Tool-schema JSON bytes** —— 所有注册工具的 JSON schema 总字节数（schema 大小 ≠ tool 实际 prompt 中显示的指导文字）

### 关键特性

- **零模型工具足迹**：顶层 CLI subcommand，不是 agent tool；不污染 agent 看到的 tool list。
- **离线运行**：模块内部用**假凭据**强制走 direct-construction path —— 不发任何网络请求即可得到完整尺寸。
- `--platform <name>` 模拟某 channel 的 platform hint（如 `--platform telegram` 让 prompt builder 加 telegram-specific 段落）。
- `--json` 输出机器可读 breakdown，可 grep / 写入监控时序。

### 典型使用场景

- "升级了几个 skill 之后 prompt 变大了多少？" —— 跑两次 `prompt-size`，比较差。
- "为什么我的 first-token latency 增加？" —— skills index 是嫌疑点（每次都重发，prefix cache 复用至关重要）。
- "为什么 my smaller-context model 拒绝接 prompt？" —— 看 system + tool-schema 总和。

[[cli-architecture]]

---

## 与其他系统的关系

- [[tool-registry-architecture]] — 技能条件激活依赖可用工具集
- [[context-compressor-architecture]] — 压缩后的消息列表传给 prompt builder 重建提示
- [[memory-system-architecture]] — memory 指导是提示的一部分
- [[agent-loop-and-prompt-assembly]] — prompt builder 被 agent 循环调用
