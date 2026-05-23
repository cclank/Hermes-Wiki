---
title: Skills System Architecture
created: 2026-04-07
updated: 2026-05-09
type: concept
tags: [skill, architecture, module, prompt-builder, curator, watchers, platforms-frontmatter]
sources: [tools/skills_tool.py, tools/skill_manager_tool.py, tools/skills_hub.py, tools/skills_guard.py, run_agent.py, agent/prompt_builder.py, hermes_cli/plugins.py, agent/skill_utils.py, agent/curator.py, hermes_cli/curator.py]
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

```
~/.hermes/skills/
├── my-skill/
│   ├── SKILL.md              # 主指令文件（必需）
│   ├── references/           # 支持文档
│   │   ├── api.md
│   │   └── examples.md
│   ├── templates/            # 输出模板
│   └── assets/               # 补充文件（agentskills.io 标准）
└── category/                 # 分类目录
    └── another-skill/
        └── SKILL.md
```

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

通过 `platforms` frontmatter 字段限制技能只在特定 OS 上加载：
- `macos` → `sys.platform == "darwin"`
- `linux` → `sys.platform == "linux"`
- `windows` → `sys.platform == "win32"`

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

## Curator — 后台技能维护（v2026.4.23 引入，v0.12.0 升级）

新增**辅助模型驱动的后台维护机制**（`agent/curator.py` + `hermes_cli/curator.py` + `tools/skill_usage.py`）。定期审查**agent 创建的**技能，跟踪使用情况，并把闲置 skill 经过状态机转换归档。

### v0.12.0 升级要点

- **作为后台 agent 运行**：跑在 gateway 的 cron-ticker 上，**默认 7 天周期**（`DEFAULT_INTERVAL_HOURS = 24 * 7`，`agent/curator.py:56`），unbounded iterations，umbrella-first prompt。
- **每轮报告**：`logs/curator/run.json` + `REPORT.md`。
- **consolidated vs pruned 分类**：归档 skill 用模型 + 启发式区分"被合并"和"被剪枝"。
- **`hermes curator status` 排序**：按使用频次显示 most-used / least-used。
- **统一在 `auxiliary.curator`**：在 `hermes model` 选 curator 模型；可在 dashboard 配置 `auxiliary.curator.{provider, model, timeout, ...}`。源：`agent/curator.py:1483` 的迁移提示和 `_resolve_review_runtime()`。
- **bump_use() 接入 skill 调用 + preload + skill_view**（v0.12.0 #17932）。
- **`restore_skill` 扫描嵌套 archive 子目录**（@0xDevNinja，#17951）。

### 不变量（load-bearing invariants）

- **永不触碰** bundled 或 hub-installed 技能（`.bundled_manifest` + `.hub/lock.json` 双过滤）
- **永不自动删除** —— 只归档，可通过 `hermes curator restore <skill>` 恢复
- **Pinned skills 跳过所有自动转换**：`tools/skill_manager_tool.py:_pinned_guard()` 在 `skill_manage` 写入路径上拦截 pinned skill 修改
- 使用 aux client（统一在 `auxiliary.curator` 配置），**永不污染主 session 的 prompt cache**

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

### CLI（11 个子命令，2026-05 扩展）

```bash
hermes curator status              # 当前状态、待处理 skill
hermes curator run                 # 立即跑一轮
hermes curator pause/resume        # 暂停/恢复
hermes curator pin <skill>         # 钉住某个 skill（跳过自动归档）
hermes curator unpin <skill>
hermes curator restore <skill>     # 从归档恢复
hermes curator archive <skill>     # 立即手动 archive（不等周期）
hermes curator prune --days 90     # 批量 archive >= N 天未用 skill（pinned 跳过）
hermes curator backup              # 整 skills 目录 backup
hermes curator rollback            # 回滚到上一次 backup
```

`/curator` 斜杠命令暴露相同子命令。

`fix(curator): protect hub skills by frontmatter name` (68c1a08) —— 除路径过滤（`.hub/lock.json`）外，按 frontmatter `name` 字段二次过滤，避免 hub-installed skill 被改名后绕过保护。

## /reload-skills 和 /reload-mcp（v2026.4.23+）

**`/reload-skills`**：重新扫描 `~/.hermes/skills/` 发现新装/卸载的 skill，无需重启进程。**用户发起的 rescan**——不重置 prompt cache（skills 是按需通过 `/skill-name`、`skills_list`、`skill_view` 调用，不需要常驻系统提示）。重扫后通过 next-turn note 通知 agent，每个新增/移除的 skill 附带 60 字符描述。

> 说明：原 PR 包含一个 `skills_reload` agent 工具，但在后续 refactor（`dd2d1ba5e`）中被显式删除——agent 已经能通过 `skill_view` / `skills_list` 看到磁盘上新装的 skill，不需要额外 schema surface。

**`/reload-mcp` 加确认提示**：MCP 重载会失效 prompt cache，gateway 现在弹出确认对话框（包含"未来不再询问"的 opt-out 选项），避免误操作清掉昂贵的缓存。

## Pin 语义：仅保护删除（v2026.5.5 收窄）

### 当前行为（2026-05-05 之后，#20220）

`tools/skill_manager_tool.py:_pinned_guard()` **仅在 `skill_manage(action='delete')` 路径触发**。Patch、edit、supporting-file write 在 pinned skill 上**全部放行**。

```python
def _pinned_guard(name: str) -> Optional[str]:
    """Return a refusal message if *name* is pinned, else None.

    Only applies to delete; the agent can still patch/edit pinned skills;
    pin only guards against deletion."""
    rec = _index_record(name)
    if rec.get("pinned"):
        return (
            f"Skill '{name}' is pinned and cannot be deleted by "
            f"skill_manage(action='delete'). Patches and edits are allowed "
            f"on pinned skills; only delete is blocked."
        )
    return None
```

调用位点（`tools/skill_manager_tool.py:571`）只剩 delete handler。

### 为什么收窄

之前 `_pinned_guard` 是 hard fence，**任何写操作（edit/patch/delete/write_file/remove_file）都拒**。设计混淆了两件事：

1. **Pin as deletion protection**——保护 skill 不被 curator/agent 删（用户实际想要的）
2. **Pin as content freeze**——禁止 agent 改 skill（造成 unpin → patch → re-pin 麻烦舞步，鼓励 skill 失修）

现在分开处理：**Curator 自身的 pinned-skip 不变**（`agent/curator.py:271` 自动归档 + `:349` LLM review prompt 都仍跳过 pinned），所以 pin 仍然防自动删除/归档；agent 仍可改 pinned skill 维护它。

## v0.12.0 新增/晋升的技能

| 技能 | 状态 | 说明 |
|------|------|------|
| `comfyui` | **从 optional 升级为 built-in by default**（`skills/creative/comfyui/`） | v5：官方 CLI + REST + 硬件门控的本地安装；ComfyUI 文档"先问云 vs 本地，再硬件检查" |
| `touchdesigner-mcp` | **bundled by default**（`skills/creative/touchdesigner-mcp/`） | 扩展 GLSL / post-FX / audio / geometry，9 篇新参考文档 |
| `humanizer` | 新增 | 移植自 OpenClaw，剥离 AI-isms |
| `claude-design` | 新增 | HTML artifact 技能；与其他 design 技能消歧 |
| `design-md` | 新增 | Google `DESIGN.md` 规范 |
| `airtable` | 新增（salvage） | skill API key 写入 `.env` |
| `pretext` / `spike` / `sketch` | 新增 | 创意/HTML mockup |
| `kanban-video-orchestrator` | 新增（重命名自 `video-orchestrator`） | 视频编排创意技能 |

源：`/tmp/hermes-agent/skills/creative/` 及 `RELEASE_v0.12.0.md`。

## 技能安装/管理增强

- **直接 URL 安装**：`hermes skills install <https://...>` 一步装包
- **`hermes skills list`** 显示 enabled/disabled 状态
- **`skill_manage` 在 `external_dirs` 中原地编辑**（v0.12.0 #17512）
- **`.archive/` 目录从 skill index walk 排除**（v0.12.0 #17931）
- **bundled skill 同步到所有 profile 包括 active**（v0.12.0 #16176）

## Curator 子命令扩展（v0.13.0+）

`hermes curator` 在 `status / run / pause / resume / pin / unpin / restore` 之上新增：

| 子命令 | 作用 | 来源 PR |
|--------|------|---------|
| `archive <skill>` | 手动归档 skill（同 curator 自动归档路径） | #20200 |
| `prune` | 真正删除归档区里足够老的 skill（默认 14 天） | #20200 |
| `list-archived` | 列出归档区的 skill | #21236 |

**`hermes curator run` 现在同步执行**——返回前等结果，不再让用户 polling 后台进程（PR #21216）。

`/curator` 斜杠命令暴露相同子命令。

## `platforms` frontmatter 全覆盖（v0.13.0+）

PR `98db898c0`（79 个 built-in） + `db22efbe8`（63 个 optional）批量补 `platforms` 声明，PR `b18b17f9c` 把 7 个 Linux/macOS-only skill 在 Windows 上自动 gate（`platforms: [linux, macos]`）。

```yaml
---
name: my-skill
platforms: [linux, macos]    # 可选；省略 = 全平台
---
```

**用途**：Native Windows beta（PR #22115）启动后，运行时 platform 不在 `platforms` 列表的 skill 自动跳过 —— 不会出现 macOS-only 工具在 Windows 报错的脏体验。

## `watchers` skill —— RSS / HTTP / GitHub 看门狗（optional）

`optional-skills/devops/watchers/`（PR #21881）—— 配合 cron `no_agent` 模式（[[cron-scheduling]]）用：

- 三个独立脚本：RSS / Atom、HTTP JSON endpoint、GitHub repo（issues / pulls / releases / commits）
- watermark dedup helper —— 只投递新 item
- `requires_toolsets: [terminal]`

## 新增 skill（v0.13.0+）

| Skill | 类型 | 说明 |
|-------|------|------|
| `comfyui` | built-in | 从 optional 移到内置，重写为官方 CLI + REST API（v2026.4.23 提，本期固化） |
| `here.now` | built-in + optional | 双版本（PR `f7dfd4ae3` / `7cbe943d2`） |
| `shopify` | optional | Admin + Storefront GraphQL（PR #18116） |
| `shop-app` | optional | 个人购物助手（PR #20702） |
| `finance` | optional bundle | Anthropic financial-services 移植（PR #21180） |
| `linear` | built-in 增强 | + Documents 支持 + Python helper（PR #20752） |
| `searxng-search` | optional | 配 SearXNG backend |
| `kanban-video-orchestrator` | optional 创意 | (@SHL0MS) PR #19281 |
| `hyperframes` | optional 创意 | |
| `watchers` | optional devops | （见上） |

## 相关页面

- [[prompt-builder-architecture]] — 技能索引构建与条件激活
- [[skills-and-memory-interaction]] — 技能与记忆的交互设计
- [[security-defense-system]] — 技能安全扫描与信任级别策略

## 相关文件

- `tools/skills_tool.py` — 技能工具实现（1378 行）
- `agent/prompt_builder.py` — Prompt 构建与技能索引
- `agent/skill_utils.py` — 技能解析工具函数
- `agent/skill_commands.py` — 技能斜杠命令
- `tools/skills_sync.py` — 技能同步机制
- `tools/skills_hub.py` — 技能中心（搜索/安装）
- `tools/skill_manager_tool.py` — 技能管理工具
