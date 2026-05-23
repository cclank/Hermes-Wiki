---
title: Skills System Architecture
created: 2026-04-07
updated: 2026-05-17
type: concept
tags: [skill, architecture, module, prompt-builder, skill-management]
sources: [tools/skills_tool.py, tools/skill_manager_tool.py, tools/skills_hub.py, tools/skills_guard.py, run_agent.py, agent/prompt_builder.py, hermes_cli/plugins.py, agent/skill_utils.py]
---

> **v2026.5.7 增量**：
>
> - **Curator 子命令扩展**：除 `status / run / pause / resume / pin / unpin / restore` 外新增：
>   - `hermes curator archive <skill>` —— 立即手工归档（`hermes_cli/curator.py:258` `_cmd_archive`）
>   - `hermes curator prune --days N` —— 批量归档 N 天闲置（line 295 `_cmd_prune`，默认 90 天，pinned 跳过）
>   - `hermes curator list-archived`（#21236）
>   - `hermes curator run` 现在**同步**返回结果（不再轮询）（#21216）
> - **Self-improvement loop 升级**（v2026.4.30）：class-first（rubric-based）、active-update biased、处理 `references/` / `templates/` 子文件、正确继承父 agent 的 live runtime（provider / model / 凭证）、限制在 memory + skills toolset。
> - **`[[as_document]]` 指令**（#21210）—— skill 输出可加此标记，强制平台以 document 投递。源码 `gateway/platforms/base.py:1899-1923`。
> - **`/reload-skills`**（v2026.4.23+）—— 不失效 prompt cache 的热重载（已在 04-29 covered）。

# 技能系统架构

## 概述

Hermes Agent 的技能系统是一个**渐进式披露（Progressive Disclosure）**架构，灵感来自 Anthropic 的 Claude Skills 系统。核心理念是：只在需要时加载完整指令，平时只保留轻量元数据，以节省 token 预算。

## 核心组件

### 1. 工具层 (`tools/skills_tool.py`)

提供两个工具：
- **`skills_list`** — 返回技能元数据列表（名称、描述、分类），token 效率高
- **`skill_view`** — 加载完整技能内容（SKILL.md + 可选引用文件）

### 2. Prompt 构建层 (`agent/prompt_builder.py`)

在每次系统提示构建时：
- 扫描 `~/.hermes/skills/` 目录
- 解析每个 SKILL.md 的 YAML frontmatter
- 构建技能索引清单注入到系统提示中
- 使用 [[prompt-builder-architecture]] 缓存结果

### 3. 技能目录结构

单个技能目录的结构：

```
my-skill/
├── SKILL.md              # 主指令文件（必需）
├── references/           # 支持文档
│   ├── api.md
│   └── examples.md
├── templates/            # 输出模板
└── assets/               # 补充文件（agentskills.io 标准）
```

**仓库内两棵顶层技能树**：除了 `~/.hermes/skills/`（用户/agent 技能），仓库本身现在有两棵独立的顶层树：

- **`skills/`** — 随仓库捆绑（bundled）的核心技能
- **`optional-skills/`** — 按分类组织的可选技能树，用户按需安装

`optional-skills/` 下的新增技能包括：

- `optional-skills/research/osint-investigation`
- `optional-skills/research/darwinian-evolver`
- `optional-skills/devops/pinggy-tunnel`
- `optional-skills/blockchain/evm`
- `optional-skills/finance/stocks`
- `optional-skills/creative/hyperframes`
- `optional-skills/software-development/rest-graphql-debug`（原 `api-testing` 已重命名为 `rest-graphql-debug`）

### 4. SKILL.md 格式

```yaml
---
name: skill-name                    # 必需，最多 64 字符
description: Brief description      # 必需，最多 1024 字符
version: 1.0.0                      # 可选
license: MIT                        # 可选
platforms: [macos]                  # 可选 — 限制 OS 平台
prerequisites:                      # 可选 — 运行时要求
  env_vars: [API_KEY]               #   环境变量
  commands: [curl, jq]              #   命令检查
setup:                              # 可选 — 交互式设置
  help: "Get key at https://..."    #   帮助文本
  collect_secrets:                  #   密钥收集
    - env_var: API_KEY
      prompt: "Enter your API key"
      secret: true
metadata:                           # 可选
  hermes:
    tags: [fine-tuning, llm]
    related_skills: [peft, lora]
---

# Skill Title

Full instructions and content here...
```

## 技能发现流程

```python
# 1. 获取所有技能目录
get_all_skills_dirs() → [Path, Path, ...]

# 2. 解析每个 SKILL.md 的 frontmatter
parse_frontmatter(raw_content) → (dict, body)

# 3. 检查平台兼容性
skill_matches_platform(frontmatter) → bool

# 4. 提取条件激活规则
extract_skill_conditions(frontmatter) → {
    "requires_tools": [...],
    "requires_toolsets": [...],
    "fallback_for_tools": [...],
    "fallback_for_toolsets": [...]
}

# 5. 构建技能索引注入到系统提示
_build_skills_index(available_tools, available_toolsets) → str
```

## 条件激活机制

技能可以根据当前可用的工具/工具集条件性显示：

- **`requires_tools`** — 需要特定工具才显示
- **`requires_toolsets`** — 需要特定工具集才显示
- **`fallback_for_tools`** — 当主工具可用时隐藏（作为备选）
- **`fallback_for_toolsets`** — 当主工具集可用时隐藏

## 平台过滤

通过 `platforms` frontmatter 字段（YAML 列表，如 `platforms: [macos, linux]`）限制技能只在特定 OS 上加载：
- `macos` → `sys.platform == "darwin"`
- `linux` → `sys.platform == "linux"`
- `windows` → `sys.platform == "win32"`

执行逻辑在 `agent/skill_utils.py:92` 的 `skill_matches_platform(frontmatter)`：字段**为空或缺失视为兼容所有平台**（向后兼容），`PLATFORM_MAP` 把友好名映射到 `sys.platform` 前缀。在 prompt 组装阶段（`agent/prompt_builder.py:1050`）把不匹配的 skill 过滤出系统提示。v2026.5.x 给全部 79 个内置 + 63 个 optional skill 补齐了 `platforms` frontmatter，并把 7 个 Linux/macOS-only skill 对 Windows 做了 gate。

## 插件命名空间技能（2026-04-14）

除了 `~/.hermes/skills/` 的扁平目录扫描,插件还可以注册**带命名空间的技能**,避免与内置技能重名冲突。

### 注册方式

```python
# 插件的 __init__.py
def register(ctx):
    ctx.register_skill(
        name="deploy",
        path=Path(__file__).parent / "skills" / "deploy" / "SKILL.md",
        description="Deploy a service to production",
    )
```

`PluginContext.register_skill()` 内部把它存为 `{plugin_name}:{name}` 格式的 qualified name,例如插件 `myops` 注册的 `deploy` 技能实际名字是 `myops:deploy`。

**校验规则**(`hermes_cli/plugins.py:267`):
- `name` 不能含 `:`(命名空间由插件名自动派生)
- `name` 必须匹配 `[a-zA-Z0-9_-]+`
- `path` 指向的 SKILL.md 必须存在

### 调度逻辑

`skill_view(name)` 在 `tools/skills_tool.py:822` 检测 `:` 分隔符:
- **带 `:` 的名字** → `parse_qualified_name(name)` → 路由到 `_serve_plugin_skill(namespace, bare)`
- **裸名字** → 继续走原有的 `~/.hermes/skills/` 扁平树扫描

插件技能加载时会跑完整防护:
1. 插件被 disable → 返回错误(含 `hermes plugins enable` 提示)
2. 平台不匹配(`skill_matches_platform`) → 返回 UNSUPPORTED
3. 注入模式扫描(`_INJECTION_PATTERNS`) → 记日志但仍加载(与本地技能一致)
4. 返回时附带 **bundle context banner**,列出同一插件的其他技能供 agent 参考

### 不进系统提示索引

**关键区别**:插件技能**不出现在** system prompt 的 `<available_skills>` 清单里,它们是**显式 opt-in**——agent 必须知道名字(通过文档或插件 README)才能调用 `skill_view("myops:deploy")`。

这样设计的原因:
- 避免插件污染主提示词(系统提示已经很大)
- 避免 prefix cache 因为第三方插件数量波动而失效
- 用户装了什么插件,agent 不应该自动全部感知

### 相关 API

| 符号 | 位置 | 用途 |
|---|---|---|
| `PluginContext.register_skill()` | `hermes_cli/plugins.py:267` | 插件注册入口 |
| `PluginManager._plugin_skills` | `hermes_cli/plugins.py` | 注册表存储 |
| `parse_qualified_name()` | `agent/skill_utils.py:451` | 分解 `ns:bare` |
| `is_valid_namespace()` | `agent/skill_utils.py` | 命名空间合法性校验 |
| `_serve_plugin_skill()` | `tools/skills_tool.py:718` | 加载 + 防护 + banner |
| `_INJECTION_PATTERNS` | `tools/skills_tool.py`(模块级) | 与本地技能共享的注入检测

## 密钥管理

技能可以声明需要的环境变量，系统会：
1. 检查 `~/.hermes/.env` 是否已设置
2. 如果缺失且在 CLI 模式，通过回调交互式收集
3. 在 Gateway 模式，提示用户手动配置
4. 保存后持久化到 `.env` 文件

## 自动 Skill Review（Background Review）

Hermes 不只被动使用 Skill，还能**自主创建和更新 Skill**。这是 Hermes 的"自我进化"机制。

### 触发条件

三个条件同时满足时触发：

```python
if (self._skill_nudge_interval > 0                          # 功能未禁用
        and self._iters_since_skill >= self._skill_nudge_interval  # 工具调用累计达标
        and "skill_manage" in self.valid_tool_names):        # skill_manage 工具可用
```

```yaml
# config.yaml
skills:
  creation_nudge_interval: 15   # 每累计 15 次工具调用触发一次 review（0 = 禁用）
```

注意：计数器累加的是**工具循环次数**（不是对话轮次），跨轮次持续累加。agent 主动调用 `skill_manage` 时计数器归零。

### 执行流程

```text
工具调用累计达到 15 次
    ↓
轮次结束后，派生后台 agent（独立线程，max_iterations=8）
    ↓
后台 agent 拿到完整对话快照，审查：
  "有没有经过试错、调整方向、或用户期望不同做法的非平凡经验？"
    ↓
三种结果：
  ├── 有现成 skill → 调用 skill_manage 更新
  ├── 没有但值得新建 → 调用 skill_manage 创建
  └── 没什么值得存的 → "Nothing to save." 结束
    ↓
终端打印：💾 Skill "docker-network-debug" created
```

### 设计特点

- **不阻塞用户**：在回复用户之后才启动，不占用对话延迟
- **不修改主对话**：后台 agent 独立运行，不影响主 agent 的消息历史
- **共享记忆存储**：后台 agent 与主 agent 共享 `_memory_store`，skill 写入立即可用
- **与 Memory Nudge 可合并**：当 skill review 和 memory review 同时触发时，使用合并 prompt 一次处理

### 与手动创建的区别

| | 手动创建（用户指令） | 自动创建（Background Review） |
|---|---|---|
| 触发方式 | 用户说"帮我创建一个 skill" | 系统计数器自动触发 |
| 内容来源 | 用户指定 | 后台 agent 从对话中提炼 |
| 质量 | 用户控制 | agent 自主判断，可能创建也可能跳过 |
| LLM 消耗 | 主对话的一部分 | 额外消耗（后台 agent 最多 8 轮迭代） |

## Curator — 后台技能维护（v2026.4.23+，v0.12.0 大幅扩展）

新增**辅助模型驱动的后台维护机制**（`agent/curator.py` + `hermes_cli/curator.py` + `tools/skill_usage.py`）。定期审查**agent 创建的**技能，跟踪使用情况，并把闲置 skill 经过状态机转换归档。

### 不变量（load-bearing invariants）

- **永不触碰** bundled 或 hub-installed 技能（`.bundled_manifest` + `.hub/lock.json` 双过滤；v0.12.0 进一步加入 **frontmatter name 保护**——68e4664，避免重命名后绕过 hub 检查）
- **永不自动删除** —— 只归档，可通过 `hermes curator restore <skill>` 恢复
- **Pinned skills 跳过所有自动转换**：curator 永不对 pinned 技能做自动归档或 LLM review（`agent/curator.py`）。`skill_manage` 侧，`tools/skill_manager_tool.py:_pinned_guard()` 仅拦截 **delete**（见下文「pinned skill 的删除保护」）
- 使用 aux client，**永不污染主 session 的 prompt cache**
- `.archive/` 在 skill index walk 和 skills_tool 中**全部跳过**（eda1d51 + a845177），不再误把归档当作活跃 skill 推给 agent

### 触发逻辑

默认开启，**inactivity-triggered**（无 cron 守护进程）：CLI 启动 + gateway 启动时检查，满足两条件才跑：
1. 上次运行 > `interval_hours`（默认 `24 * 7 = 168`，即 7 天，`agent/curator.py:39 DEFAULT_INTERVAL_HOURS`）
2. agent 已闲置 > `min_idle_hours`（默认 `2`，`agent/curator.py:40`）

Gateway 模式下也 hook 进 cron-ticker 线程定期检查。

### v2026.4.30 自治化升级

- **每轮报告**：`logs/curator/run.json` + `REPORT.md` 落盘（`agent/curator.py:431-562`）
- **consolidated vs pruned 分类**：`_classify_removed_skills()` 用 model + 启发式区分"整合归档"（吸收到 umbrella skill）vs"真正归档"（不再使用）；用 `_extract_absorbed_into_declarations()` 提取 `absorbed_into` 字段权威记录吸收去向
- **rollback 恢复 cron skill 链接**：`hermes curator rollback` 不仅恢复文件，还修复 cron 引用
- **`bump_use()` 接入 `skill_view` / preload / 调用路径** —— 真实使用频次计数，不只看创建/编辑时间
- **跳过 `.archive/` 子目录的 skill 索引扫描**

### 状态机

```
active ──不用 N 天──> stale ──继续不用──> archived
   ↑                                         │
   └──────── 重新使用 ────────────────────────┘
```

纯函数式（`agent/curator.py` 内的 state-machine 转换），无 LLM 调用。Forked AIAgent 仅在需要**整合重叠 + 修补漂移**时才介入。

### sidecar telemetry

`tools/skill_usage.py`（506 行）给每个 skill 维护 `.usage.json` sidecar 文件：
- 原子写入 + provenance filter
- 记录使用次数（`bump_use()` 在 `skill_view`、preload、显式调用路径都触发）和最近使用时间
- 是状态机的输入信号，也是 `hermes curator status` 排名依据

### CLI 子命令（hermes_cli/curator.py 的 `_cmd_*` 函数）

Curator CLI（`hermes_cli/curator.py`）共有 12 个子命令：

```bash
hermes curator status              # 当前状态、待处理 skill
hermes curator run                 # 立即跑一轮（--sync / --background / --dry-run）
hermes curator pause/resume        # 暂停/恢复
hermes curator pin <skill>         # 钉住某个 skill（跳过自动转换）
hermes curator unpin <skill>
hermes curator restore <skill>     # 从归档恢复
hermes curator list-archived       # 列出已归档的 skill
hermes curator archive <skill>     # 手动归档某个 skill（移入 .archive/）
hermes curator prune               # 批量归档闲置 >= N 天的 agent skill
                                   #   --days（默认 90）、-y/--yes、--dry-run
hermes curator backup              # 手动 tar.gz 快照 ~/.hermes/skills/
                                   #   --reason 写入 manifest.json
hermes curator rollback            # 从 curator 快照恢复 ~/.hermes/skills/
                                   #   --list、--id、-y
```

`/curator` 斜杠命令暴露相同子命令。`status` 计算「最近不活跃」（按 `last_activity_at`）、「最活跃 / 最不活跃」（按 `activity_count` = use+view+patch）各 top-5。

**consolidated vs pruned 分类**（`agent/curator.py:_classify_removed_skills`）：被移除的 skill 分两类——**consolidated**（内容被并入某个 umbrella skill，返回 `{name, into, evidence}`）和 **pruned**（因陈旧归档、无合并目标，`{name}`）。`_reconcile_classification()` 调和三路信号：(a) 模型在 `skill_manage` 删除时声明的 `absorbed_into=`（权威）、(b) 模型写的 `## Structured summary` YAML 块里的 `consolidations:`/`prunings:`、(c) 扫描 `skill_manage` 调用的工具调用启发式。

#### archive / prune 子命令（#20200）

- **`archive`** — 手动归档单个 agent 创建的技能。遇到 pinned 技能会拒绝，并提示用 `hermes curator unpin`。
- **`prune`** — 批量归档闲置时长 ≥ `--days`（默认 90 天）的未钉技能。`last_activity_at` 为空时回退到 `created_at`，确保从未使用的技能也能被 prune。`--dry-run` 预览、`--yes` 跳过确认。

> 设计说明：`#19384` 原本还提议 `stats` 和 `restore` 两个动词，但它们已存在为 `curator status` / `curator restore`，因此只新增 `archive` 和 `prune`，所有技能生命周期命令统一在 `hermes curator` 命名空间下。

#### `curator status` 使用排行（#18033、#17941）

`hermes curator status` 除状态、`interval`、`stale after`、`archive after` 外，还展示三类技能排行：

- **least recently active (top 5)** — 按 `last_activity_at`（含 view/edit）升序，始终显示。
- **most active (top 5)** — 按 `activity_count`（use + view + patch）降序，全为 0 时隐藏（新装环境降噪）。
- **least active (top 5)** — 按 `activity_count` 升序。

此外，归档技能在 run 报告中被进一步拆分为 **consolidated（内容被吸收进新 umbrella 技能）** 与 **pruned（真正闲置归档）** 两类（`#17941`，通过当轮 `skill_manage` 工具调用做 model + 启发式分类）。这样用户不会把「被整合」的技能误认为「被删除」而错误 restore，造成技能重复。

#### 默认信任的 GitHub tap（#2549）

`tools/skills_hub.py` 的 `GitHubSource.DEFAULT_TAPS` 与 `tools/skills_guard.py` 的 `TRUSTED_REPOS` 现已加入 **`huggingface/skills`**，与 `openai/skills`、`anthropics/skills` 同列为 `trusted` 信任级别（第三方扫描不弹警告）。

> 内置技能目录也有变动：`comfyui` 已从 `optional-skills/` 移入 `skills/creative/`（`#17631`），成为随 Hermes 发行的 built-in 技能。新增的内容技能（如 EVM 多链、股票金融、api-testing 等）属于技能「内容」层，不影响本页描述的技能「系统」架构。

**自动快照**：curator 在每次真正运行（real run）之前都会自动对 `~/.hermes/skills/` 打一个 tar.gz 快照——`hermes curator rollback` 即从这些快照恢复。

## /reload-skills 和 /reload-mcp（v2026.4.23+）

**`/reload-skills`**：重新扫描 `~/.hermes/skills/` 发现新装/卸载的 skill，无需重启进程。**用户发起的 rescan**——不重置 prompt cache（skills 是按需通过 `/skill-name`、`skills_list`、`skill_view` 调用，不需要常驻系统提示）。重扫后通过 next-turn note 通知 agent，每个新增/移除的 skill 附带 60 字符描述。

> 说明：原 PR 包含一个 `skills_reload` agent 工具，但在后续 refactor（`dd2d1ba5e`）中被显式删除——agent 已经能通过 `skill_view` / `skills_list` 看到磁盘上新装的 skill，不需要额外 schema surface。

**`/reload-mcp` 加确认提示**：MCP 重载会失效 prompt cache，gateway 现在弹出确认对话框（包含"未来不再询问"的 opt-out 选项），避免误操作清掉昂贵的缓存。

## pinned skill 的删除保护（v2026.4.23+，#20220 后收窄）

`tools/skill_manager_tool.py:137` 的 `_pinned_guard(name)` 在 `skill_manage` 写入路径上检查 pinned 状态。

**最初**（`#17562`）pin 是一道「硬围栏」，拦截 `skill_manage` 的所有写动作（edit、patch、write_file、remove_file、delete）。但 `#20220` 把它**收窄为只拦截 `delete`**：

```python
# tools/skill_manager_tool.py:_pinned_guard
if rec.get("pinned"):
    return (
        f"Skill '{name}' is pinned and cannot be deleted by "
        f"skill_manage. Patches and edits are allowed on pinned skills; "
        f"only deletion is blocked. Run `hermes curator unpin {name}` first."
    )
```

收窄原因：pin 混淆了两种关注点——「删除保护」（别让 curator 归档或 agent 删掉稳定技能）和「内容冻结」（别让 agent 中途改写）。实践中用户 pin 是为了前者；后者制造了「unpin → patch → 重新 pin」的摩擦，反而让 pinned 技能逐渐过时。

因此现在：

- **`skill_manage(action='delete')`** — pinned 技能被拒绝。
- **edit / patch / write_file / remove_file** — pinned 技能**允许通过**，agent 仍可持续改进它。
- **curator 自身** —— 仍完全不碰 pinned 技能（自动归档与 LLM review 均跳过，`agent/curator.py`）。
- **`hermes curator archive <skill>`** —— 这是删除等价的归档动作，遇 pinned 仍会拒绝。

要彻底删除一个 pinned 技能，需先 `hermes curator unpin <name>`。

## Skills Hub — 来源与信任（v2026.5.x）

`tools/skills_hub.py` 从多种来源安装 skill。

**Trusted "tap" 机制**：`GitHubSource.DEFAULT_TAPS` 是内置 tap 列表，v2026.5.x 加入 `huggingface/skills`（与 `openai/skills`、`anthropics/skills`、`VoltAgent/awesome-agent-skills` 并列）。用户 tap 由 `TapsManager` 管理，存 `~/.hermes/.hub/taps.json`。信任级别 `builtin` / `trusted` / `community`——`trust_level_for()` 仅对 `TRUSTED_REPOS` 内的仓库返回 `trusted`。

**直接 HTTP(S) URL 安装**：`UrlSource(SkillSource)`（`skills_hub.py:978`）——标识符就是 URL，认领以 `.md` 结尾的裸 HTTP(S) URL，仅支持单文件 SKILL.md，信任级别恒为 `community`，与其他来源一样跑安全扫描。

## 相关页面

- [[prompt-builder-architecture]] — 技能索引构建与条件激活
- [[skills-and-memory-interaction]] — 技能与记忆的交互设计
- [[security-defense-system]] — 技能安全扫描与信任级别策略

## 相关文件

- `tools/skills_tool.py` — 技能工具实现
- `agent/prompt_builder.py` — Prompt 构建与技能索引
- `agent/skill_utils.py` — 技能解析工具函数
- `agent/skill_commands.py` — 技能斜杠命令
- `tools/skills_sync.py` — 技能同步机制
- `tools/skills_hub.py` — 技能中心（搜索/安装），`DEFAULT_TAPS` 含 huggingface/skills
- `tools/skills_guard.py` — 技能安全扫描与信任级别，`TRUSTED_REPOS` 含 huggingface/skills
- `tools/skill_manager_tool.py` — 技能管理工具，`_pinned_guard()` 仅拦截 delete
- `agent/curator.py` — 后台技能维护（状态机、归档分类）
- `hermes_cli/curator.py` — `hermes curator` CLI（status/archive/prune/restore 等子命令）
- `tools/skill_usage.py` — 技能使用 sidecar telemetry（`.usage.json`）
