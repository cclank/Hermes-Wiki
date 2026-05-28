---
title: Skills System Architecture
created: 2026-04-07
updated: 2026-05-28
type: concept
tags: [skill, architecture, module, prompt-builder, curator, bundles, skills-hub-health]
sources: [tools/skills_tool.py, tools/skill_manager_tool.py, tools/skills_hub.py, tools/skills_guard.py, tools/skill_usage.py, tools/skill_provenance.py, run_agent.py, agent/prompt_builder.py, agent/curator.py, agent/curator_backup.py, agent/skill_bundles.py, hermes_cli/curator.py, hermes_cli/plugins.py, agent/skill_utils.py, scripts/build_skills_index.py, .github/workflows/skills-index-freshness.yml]
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

## v0.12.0+ 重大变化

### 1. Background Review v2

`agent/background_review.py` 在 v0.12.0 大幅重写（PRs #16026 / #17213 / #16099 / #16569 / #16204 / #15057）：

- **rubric 化**（class-first），不再 free-form。
- **active-update biased**：偏好"刚加载的那个 skill"，避免漂移到无关 skill。
- 处理 `references/` 和 `templates/` 子文件。
- **正确继承父运行时**：provider / model / credentials 真正传播到 fork。
- **toolset 限制为 memory + skills**，杜绝 fork 跑去乱写文件。
- memory provider clean shutdown。
- prior-turn tool messages **不纳入摘要**，给 fork 干净 context。

### 2. Curator 升级到 1781 行

`agent/curator.py` 从 869 行涨到 **1781 行**。`hermes curator` 子命令族（`hermes_cli/curator.py`）：

```
hermes curator status         # 排序 skills（most-used / least-used）
hermes curator run            # 立即触发一次 review，**同步执行**，结果直接看
hermes curator pause          # 暂停 inactivity-triggered 自动 review
hermes curator resume         # 恢复
hermes curator pin <skill>    # 钉住，绕过自动转换
hermes curator unpin <skill>
hermes curator restore <skill> # 把归档的 skill 复活
hermes curator list-archived  # 看历史归档
hermes curator archive <skill> # 手动归档
hermes curator prune          # 手动剪枝
```

- 报告：`logs/curator/<run>/run.json` + `REPORT.md`。
- 状态分类：`consolidated`（合并到别的 skill）vs `pruned`（彻底剪掉）—— model + heuristic 双判定。
- 统一在 `auxiliary.curator` 配置：`hermes model` 单独选 curator 模型，dashboard 单独管理。
- **永远只动 agent-created skills**（`tools/skill_usage.is_agent_created`），bundled / hub-installed skills 双过滤保护。
- **永远只归档，不删除**，可恢复。
- Pinned skills **bypass 所有自动转换**。
- 用 aux client，**永远不污染主 session 的 prompt cache**。

### 3. `/reload-skills` —— prompt-cache-safe 重扫

v0.11.0 引入 `/reload-skills`，**关键设计**是：重扫 `~/.hermes/skills/` 后**不重建 system prompt** —— 因为 skill 按需 `skill_view` 加载，不常驻 system prompt。所以新装/卸载 skill 不会让 prompt cache 失效。重扫完后通过 **next-turn note** 通知 agent，每个 skill 附 60 字符描述。

> 注意 v0.11.0 早期一度有 `skills_reload` agent tool，refactor 中（commit `dd2d1ba5e`）删除 —— 因为它**会**失效 prompt cache。slash command `/reload-skills` 不动 cache。

### 4. `/reload-mcp` —— 显式失效 cache

MCP 工具会进系统提示，所以重载会失效 cache。CLI 弹一个 **"未来不再询问"** 的确认对话框。

### 5. Pinned Skills 写保护

`_pinned_guard()` 在 `skill_manage` 的 create/update/archive/delete 路径上拦截 —— curator pin 的 skill **任何手段都改不动**（包括 agent 自己想改）。

### 6. 新内置 skill

| skill | 来源 |
|-------|------|
| **ComfyUI v5**（`skills/creative/comfyui/`） | v0.12.0 从 optional 升 bundled，重写为官方 CLI + REST，硬件 gate 本地装 |
| **TouchDesigner-MCP**（`skills/creative/touchdesigner-mcp/`） | v0.12.0 bundled + GLSL / post-FX / audio / geometry + 9 个 reference docs |
| **Humanizer** | v0.12.0 — 剥离 AI-isms |
| **claude-design** | v0.12.0 — HTML artifact + DESIGN.md Google spec |
| **bundled hermes-achievements** | v0.12.0 plugin，扫描完整 session 历史 |
| **direct-URL skill install** | v0.12.0 — `skill_manage install_from_url ...` |
| **external_dirs 写权** | v0.12.0 — 配置后可 `skill_manage` 改第三方 skill 树 |

---

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

## Curator — 自治技能维护（v2026.4.23 引入，v0.12+ 全面重构到 1781 行）

`agent/curator.py`（1781 行）+ `agent/curator_backup.py` + `hermes_cli/curator.py`（582 行）。从"被动清理过期 skill"演进到 **active umbrella consolidation + 多层安全网（backup / pin / dry-run）+ 统一 aux 模型路由**。

### 不变量（load-bearing invariants）

- **永不触碰** bundled 或 hub-installed 技能（`.bundled_manifest` + `.hub/lock.json` 双过滤，`tools/skill_usage.py:159-217`）
- **永不自动删除** —— 只归档（`.archive/` 子目录），可 `hermes curator restore <skill>` 恢复
- **Pinned skills 跳过所有自动转换**：`tools/skill_manager_tool.py:_pinned_guard()` 在 `skill_manage` 写入路径拦截
- 使用 aux client，**永不污染主 session 的 prompt cache**
- 跑前**自动 tarball 快照** `~/.hermes/skills/.curator_backups/{TS}/`，可 `hermes curator rollback`

### 统一 auxiliary.curator 配置（v0.12, `agent/curator.py:1557-1620`）

```yaml
auxiliary:
  curator:
    provider: openrouter
    model: anthropic/claude-haiku-4-5
    api_key: ...
    base_url: ...
    timeout: 300
```

- 主路径：`auxiliary.curator.*`
- 兼容回退：`curator.auxiliary.{provider,model}`（带 deprecation warning）
- 都没配 → fall through 到主 chat model
- 与 `hermes model` CLI + dashboard Models tab 完全整合

### Consolidated vs Pruned 分类（v0.12, `agent/curator.py:498-611, 1021-1049`）

报告显式区分两类归档：

| 类型 | 含义 |
|------|------|
| **Consolidated** | 内容被合并进 umbrella skill，归档但内容保留 |
| **Pruned** | 纯过期，无目标 umbrella，直接归档 |

三步启发式分类：

1. 解析模型的结构化 YAML 块（`consolidations:` / `prunings:` + rationale）
2. 工具调用启发式（detect `write_file`/`patch`/`create` 引用已删 skill）
3. Reconcile：模型给意图，启发式验证（umbrella 存在 + 内容保留）

`_extract_absorbed_into_declarations()` 读取 `skill_manage` delete 调用上的 `absorbed_into` 参数 ground truth。

### 触发与执行

默认开启，**inactivity-triggered**（无 cron 守护进程）：CLI / Gateway 启动时检查：

1. 上次跑 > `interval_hours`（默认 `DEFAULT_INTERVAL_HOURS = 24 * 7` 即 7 天，`agent/curator.py:56`）
2. agent 闲置 > `min_idle_hours`（默认 `DEFAULT_MIN_IDLE_HOURS = 2`，`agent/curator.py:57`）
3. 状态机阈值：`DEFAULT_STALE_AFTER_DAYS = 30`（line 58）/ `DEFAULT_ARCHIVE_AFTER_DAYS = 90`（line 59）

Gateway 也 hook 进 cron-ticker 定期检查。

### 状态机（pure auto, 无 LLM）

```
active ──≥ stale_after_days (默认 30)─→ stale ──≥ archive_after_days (默认 90)─→ archived
   ↑                                                                              │
   └────────────────── 重新使用 ───────────────────────────────────────────────────┘
```

转换在 `agent/curator.py:256-296`。Pinned skill 永远跳过自动转换。

### Umbrella-Building Prompt（v0.12, `agent/curator.py:330-445`）

LLM review pass 的指令：

- **目标**：建 class-level umbrella，禁止"一 bug 一 skill"碎片化
- **策略**：扫 PREFIX CLUSTER（同首词/同域 skill）→ 合并到 umbrella / 创建新 umbrella + archive sibling / 降级为 support files（references/templates/scripts）
- **结构化输出（必需）**：

```yaml
consolidations:
  - from: <old-skill>
    into: <umbrella>
    reason: <one sentence>
prunings:
  - name: <skill>
    reason: <one sentence>
```

- **硬规则**：bundled/hub 不可删，pinned 不可动，archives only，**基于 CONTENT 合并**（不看 use_count）

### Per-run 报告（v0.12, `agent/curator.py:452-471, 970-1070`）

每次跑写 `~/.hermes/logs/curator/{YYYYMMDD-HHMMSS}/`：

- `run.json` —— 机器可读（before/after 计数、状态转换、工具调用、分类）
- `REPORT.md` —— 人类可读叙述（auto-transitions、LLM review 总结、consolidated → umbrella map、pruned + stale 时间戳）

`state.last_report_path` 指向最新报告，`hermes curator status` 直接显示路径。

### Sidecar telemetry（`tools/skill_usage.py:1-150`）

每个 skill 维护 `.usage.json` sidecar：

- **计数器**：`use_count` / `view_count` / `patch_count`
- **时间戳**：`last_used_at` / `last_viewed_at` / `last_patched_at` / `created_at` / `archived_at`
- **生命周期**：active / stale / archived（与 pinned 正交）
- **派生**：`latest_activity_at()` 取最新（**故意排除创建**），`activity_count` 累加
- **原子写**：tempfile + `os.replace`；所有 bump 都是 best-effort，绝不破坏底层 tool

`bump_use()` 在 `skill_view` / 预加载 / skill 调用三处都触发（`#17932`），驱动状态机。

### Provenance（`tools/skill_provenance.py:1-79`）

- `get_current_write_origin()` 返回 `"background_review"`（curator fork）或 `"foreground"`（用户发起 agent）
- `skill_manage(action="create")` 自动 `mark_agent_created()`，置 `created_by: "agent"`
- Curator **只动 agent-created skill**，从不动用户手写或 hub-installed

### Dry-run（v0.12, `agent/curator.py:303-327, 1386-1405`）

```bash
hermes curator run --dry-run
```

跳过自动转换，给 LLM 加 `CURATOR_DRY_RUN_BANNER`，LLM 被指示"描述将要做什么，不做"。报告照写，`state.last_report_path` 更新，`run_count` 不增。用户读完决定提交。

### Backup / Rollback（v0.12, `agent/curator_backup.py`）

- 非 dry-run 每跑前自动打 tarball
- 包含：所有 SKILL.md + 目录 / `.usage.json` / `.archive/` / `.bundled_manifest` / `.curator_state` / cron-jobs.json 快照（仅 skill 引用部分）
- 排除：`.curator_backups/` 自身、`.hub/`（保 hub 纯净）
- 位置：`~/.hermes/skills/.curator_backups/{YYYYMMDD-HHMMSS-NN}/{tar.gz, manifest.json}`
- `hermes curator rollback [--id <stamp>] [-y]` 还原 skills tree + cron 中的 skill 引用（cron 其他字段不动）
- Rollback **本身可撤销**：跑前先打 pre-rollback 快照

### CLI 全套（`hermes_cli/curator.py:39-582`）

```bash
hermes curator status                              # 健康 + 配置 + 状态分布 + pinned + 最活跃/最少用
hermes curator run [--sync|--background] [--dry-run]
hermes curator pause / resume
hermes curator pin <skill> / unpin <skill>
hermes curator archive <skill> [--reason ...]
hermes curator restore <skill>                     # 从 .archive/ 恢复
hermes curator list-archived
hermes curator prune [--days N] [--dry-run] [-y]  # 批量按日龄归档，默认 90d
hermes curator backup [--reason ...]               # 手动快照
hermes curator rollback [--list|--id <stamp>] [-y]
```

`/curator` 斜杠命令暴露同名子命令。

## Skill Bundles（v0.14, `agent/skill_bundles.py`）

YAML 文件在 `~/.hermes/skill-bundles/` 定义 bundle：一个 `/<alias>` 一击加载多 skill。

- Slash 分发先查 bundle（bundle 在名字冲突时胜出，`agent/skill_bundles.py:29-31`）
- `build_bundle_invocation_message()` 把所有引用 skill 装一条消息 + bundle header（line 253-340）
- 缺失 skill 优雅跳过 + note（line 292-295）
- 每个被调 skill `bump_use()`（line 299-302）

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

## Skills Hub & 默认 taps（v0.14）

`tools/skills_hub.py:330-337` 默认 taps：

```python
DEFAULT_TAPS = [
    {"repo": "openai/skills", "path": "skills/"},
    {"repo": "anthropics/skills", "path": "skills/"},
    {"repo": "huggingface/skills", "path": "skills/"},      # v0.14 新增 trusted
    {"repo": "VoltAgent/awesome-agent-skills", "path": "skills/"},
]
```

`huggingface/skills` 享 **trusted** trust level（caution 验证通过即装）。

**Direct-URL install**（`tools/skills_hub.py:397+`）：
```bash
skills_hub install <github-raw-url>
```
任意 GitHub 仓库下载 + skills_guard 扫描。

**External dirs**（`agent/skill_utils.py:242-282`）：
```yaml
skills:
  external_dirs:
    - /path/to/team-skills
    - ~/.agents/skills
```
和 `~/.hermes/skills/` 并行扫描。

## Skills Guard — 安全扫描（`tools/skills_guard.py:1-933`）

每次 hub install 跑：

- **Trust level**：builtin（永不扫） / trusted（openai/anthropics/huggingface/skills） / community（其他）
- **Install policy**（`tools/skills_guard.py:41-51`）：safe 始终允许；caution 看 trust（trusted 放行，community 拦截）；dangerous 一律拦截（agent-created 询问确认）
- **~56 个威胁模式**（`tools/skills_guard.py:86-488`）：exfil（env vars / SSH/AWS dirs / base64+env）、injection（jailbreak / role-hijack / system prompt leak）、destructive（rm -rf / mkfs / dd）、persistence（cron / `~/.bashrc` / sudoers）、network（reverse shell / tunnel）、obfuscation（eval / base64 pipe）、supply chain（unpinned dep / 远程 fetch）、privilege escalation（sudo / setuid）、agent config tampering
- **结构检查**（`tools/skills_guard.py:738-852`）：文件数、总大小、二进制、symlink escape、可执行位
- **不可见 unicode 检测**（`tools/skills_guard.py:581-594`）：零宽连接符、方向覆盖、用于注入的 BOM
- **内容哈希**：skill 目录 SHA-256，完整性追踪

## AST 深度诊断（2026-05-23，`tools/skills_ast_audit.py:84`）

`hermes skills audit [name] --deep` 与 `hermes skills inspect <identifier>` 触发 `ast_scan_path(path)`（`hermes_cli/main.py:12324-12333` flag 定义；`hermes_cli/skills_hub.py:938-950` 接入）—— 在 Skills Guard 的 regex 之上补一层 **AST 级动态构造识别**：

- `importlib.import_module(computed)` / `__import__(computed)`
- `getattr(obj, computed)` / `obj.__dict__[computed]`
- 其他通过运行时 string 拼接绕开静态 regex 的 import / attribute access

输出 label 为 **"diagnostic hints"**，不是 "security verdict"：

| 文件 | 行 | pattern_id | 说明 |
|------|----|-----------|------|
| ... | ... | ... | ... |

**与 Skills Guard 的关系**：

- `tools/skills_guard.py` 是 **install gate**（block / allow / confirm）。
- `tools/skills_ast_audit.py` 是 **review aid**（人工审阅时辅助，不影响 install 决策）—— `--deep` 是 opt-in，不默认开启。

设计取舍（`7255050 feat` → `4254f7d refactor` 一日内裁掉 600 行）：原 PR 用 dataclass + severity field + 三个 entry point；refactor 合并为单 `ast_scan_path(path)` + `(file, line, pattern_id, description)` 元组，移除 severity（与 install gate 职责重叠）。

## Skills Hub 健康监控（2026-05-26 NEW，feat #32345）

`d8703e27f feat(skills-hub): health checks, freshness badge, and a watchdog cron` + `cea87d913 fix(skills-hub): show every catalog source` 引入**三层 silent-rot 防护**——commit body 引："a silent regression like 'OpenAI tap moved its skills' now fails the build instead of shipping a quietly broken catalog"。

### Build-time 健康下限 — `scripts/build_skills_index.py:330-348`

```python
EXPECTED_FLOORS = {
    "skills.sh":  100,
    "lobehub":    100,
    "clawhub":     50,
    "official":    50,
    "github":      30,    # collapsed across all GitHub taps
    "browse-sh":   50,
}

MIN_TOTAL = 1500
```

任一 source `count < floor` 或总数 `< MIN_TOTAL` → `sys.exit(2)`，CI 工作流 fail loud。失败文案明示：如果 source 真的下线，要在**同一个 PR**里下调 floor，避免 silently 接受退化的 catalog。

`skills-sh` 与 `skills.sh` 是同一 source 的两个 label，count 合并（line 343-345）。

### Page-level 新鲜度信号

`website/scripts/extract-skills.py` 同步生成 `website/src/data/skills-meta.json`，含 `generated_at` ISO timestamp + 每 source 当前条数。`website/src/pages/skills/index.tsx` 在 hero copy 下渲染 "Catalog refreshed N hours ago · auto-rebuilt twice daily"。Cron 停了 → 用户立刻看到 staleness 不必通过 issue 反馈链路。

### Watchdog Cron — `.github/workflows/skills-index-freshness.yml`（149 行）

每 4 小时拉一次 live `/docs/api/skills-index.json`：

- 校验 shape + age（>26h 算 stale）+ 同样的 per-source floors
- 任一项不对 → 开 issue（或追加 comment 到已有 `[skills-index-watchdog]` 前缀 issue，避免重复 issue spam）
- Live 探测确认：`total=2456, all 6 sources above floor, age 0.1h → issues=NONE`（commit body）

### Catalog Source 全显示修复（`cea87d913`）

之前 React 页面只显示部分 source（chunked 渲染逻辑漏 source mapping），现把 `skills.sh / ClawHub / browse.sh / OpenAI` 等全 6 source 都纳入页面 facets。涉及 `website/scripts/extract-skills.py` +229 / `website/scripts/prebuild.mjs` +71 / `website/src/pages/skills/index.tsx` +93。

## Skills 目录全量拉取（2026-05-28 NEW，v0.15.0）

两个 catalog source 此前都因分页/抓取限制只暴露目录极小一部分，本次修为全量——直接抬高 §Skills Hub 健康监控里那些 `EXPECTED_FLOORS` 的真实可达上限。

### skills.sh 走 sitemap（858 → 19,932，`7050c052e` #34025）

旧 `SkillsShSource` 跑 28 个硬编码关键词搜索（各 cap 50），只得 ~858。真实目录 ~20k，经 `sitemap-skills-{1,2}.xml`（各 ≤10k URL）暴露。现行 `tools/skills_hub.py`：

| 行 | 内容 |
|----|------|
| `:1215` | `class SkillsShSource(SkillSource)` |
| `:1224` | `SITEMAP_INDEX_URL = "https://www.skills.sh/sitemap.xml"` |
| `:1262` | 空查询路径改走 `self._sitemap_catalog(limit)`（替代 homepage featured strip 抓取） |
| `:1323` | `_sitemap_catalog()` — 走 sitemap 枚举全目录，sitemap 不可达时回退 `_featured_skills` |
| `:1342` | 处理 httpx + brotlicffi 交互：per-skill sitemap 显式用 `Accept-Encoding: gzip` |

`build_skills_index.crawl_skills_sh()` 现只调 `search("", limit=0)`（一次 HTTP 往返替代 28 次关键词搜索，同结果）。

### ClawHub 全目录分页（200 → 20k+，`fb9f3a4ef` #33748）

`ClawHubSource.search("")` 空查询走单次无分页请求，ClawHub API 单页 cap 200 并返回 `nextCursor`；旧逻辑抓第 1 页就停，缓存索引（hermes-agent.nousresearch.com 服务）静默截断 99%。修为按 `nextCursor` 翻页拉全量。

### 其他 Skills 修复
- `e0572a6de`（#33810）：skills-hub 标识符列不再省略号截断。
- `a1eaad2fc`（perf，#33809）：dashboard skills 页改懒加载目录，不再把 34MB 打进 JS bundle。

详见 [[2026-05-28-update]]。

## Skill Install 拒绝符号链接（2026-05-26 NEW，fix）

`tools/skills_hub.py:3046-3058`（commit `c26af4681`）：`install_from_quarantine()` 在 `shutil.move(quarantine_path, install_dir)` 之**前**用 `quarantine_path.rglob("*")` + `_is_path_redirect(entry)`（line 153-159，含 Windows directory junction `is_junction()`）扫整个 quarantined skill bundle。任一 symlink/junction 入口即：

```python
raise ValueError(
    f"Installed skill contains symlinks, which is not allowed: {rel}"
)
```

威胁模型（注释引）：恶意 skill bundle 可能含指向 skill tree 外的 symlink；其 target 内容会被 `shutil.move` 当成常规文件 copy 进 `skills/`，下次 `skill_view` 时 leak 给 agent。本提交是 v0.14 安全 wave 3 那"6 处 symlink 拒绝矩阵"在 **skill-install 路径**上的补完。`tools/skills_guard.py:738-852` 旧的结构检查只做 "symlink escape"（target 指向 quarantine 外）—— 现在升级为**任意 symlink 全拒**，因 skill view 是按 path 直读，符号链接的存在本身就有歧义。+47 行测试。

## 新增 Optional Skills（2026-05-26）

| 路径 | 描述 | 状态 |
|------|------|------|
| `optional-skills/security/web-pentest/SKILL.md` | 授权 Web 应用渗透测试，Shannon "No Exploit, No Report" 方法论 + 范围/授权/aux-client 泄漏护栏 | feat #32265 |
| `optional-skills/autonomous-ai-agents/openhands/SKILL.md` | 把 coding delegate 给 OpenHands CLI（model-agnostic via LiteLLM）。`claude-code` / `codex` / `opencode` 家族中的模型无关选项 | feat closes #477 |
| `optional-skills/software-development/code-wiki/SKILL.md` + 4 模板 | 生成 codebase wiki（overview + Mermaid flowchart + 每模块 deep-dive + class/sequence diagrams + getting-started + API ref）；输出默 `~/.hermes/wikis/<repo>/` | feat closes #486 |

设计原则：三者均归 `optional-skills/`（"when in doubt, optional"），install-on-demand 而非默认加载。`openhands` 的 SKILL.md 经 verified install (`uv tool install openhands --python 3.12`) 重写，因原 PR 的 SKILL.md 由 OpenHands agent 自身起草，幻觉了 `--model` / `--max-iterations` / `--workspace` / `--sandbox docker` 等不存在的 flag。

## BrowseShSource — 第 8 个 catalog 源（2026-05-27 NEW）

`tools/skills_hub.py:2429 BrowseShSource(SkillSource)`（commit `57145ca`）：

- **来源**：[browse.sh](https://browse.sh) — Browserbase 维护的 **200+ 站点专用浏览器自动化 SKILL.md** 目录（Airbnb / Amazon / arXiv / Discord / GitHub / Linkedin / Notion / Stripe ...）
- **API**：
  - 目录列表 `https://browse.sh/api/skills`
  - 单 skill 详细 `https://browse.sh/api/skills/{slug}` 返回 `skillMdUrl` CDN URL
- **设计取舍**：catalog 的 `sourceUrl` 是 GitHub HTML URL，但底层 repo 不一定公开，所以**不依赖**它作内容拉取
- **trust level**：`community`（同其它非 NousResearch 维护源）
- **source_id**：`browse-sh`
- 已纳入 `scripts/build_skills_index.py:264,297` + `hermes_cli/main.py:12451` 的 catalog source 表，与 `EXPECTED_FLOORS = 50`（`scripts/build_skills_index.py:336`）

加上既有的 7 个（GitHub / WellKnown / Url / SkillsSh / ClawHub / ClaudeMarketplace / LobeHub），共 **8 个 catalog source** 接入 Skills Hub。

## Skills 修复簇（2026-05-27 NEW）

| Commit | 修复 |
|--------|------|
| `0537e26` | **fix(skills): atomic lock write + drop dead `_validate_category_name`** —— 防止 lock 文件 race 留半成品 |
| `ee80dfd` | **fix: preserve skill packages during curator consolidation** —— curator 整合时不再误删 package skill |
| `f040710` | **fix: backfill official optional skill provenance** —— 老版本安装的官方 optional skill 在新 manifest 下补回 provenance |
| `a38e283` | **fix: preserve nested official skill install paths** —— 嵌套 install 路径在 consolidation 后保留 |
| `58591d9` | **feat: show names of user-modified skills in bundled skill sync summary** —— sync 摘要里高亮被用户改过的 skill |
| `7255050` | **feat(skills): add opt-in AST deep diagnostics** —— `audit --deep` / `inspect` 子命令开启 AST 深扫 |
| `291a158` | **fix(skills): move `platforms` key out of folded `description: >` scalars** —— YAML 折叠语法导致 `platforms` 误解析为 description 的部分（Windows 平台过滤跑空） |

### 7 个 Linux/macOS-only Skills 在 Windows 上 gate

`b18b17f`「feat(skills): gate 7 Linux/macOS-only skills from Windows via platforms frontmatter」+ `98db898` / `db22efb`（79 个内置 + 63 个 optional skill declare 平台）—— Windows 用户不再误装跑不通的 skill。

## 相关页面

- [[prompt-builder-architecture]] — 技能索引构建与条件激活
- [[skills-and-memory-interaction]] — 技能与记忆的交互设计
- [[security-defense-system]] — 技能安全扫描与信任级别策略
- [[kanban-multi-agent-board]] — 多 Agent 协作时配合 skills 分发

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
- `scripts/build_skills_index.py:330-348` — **NEW 2026-05-26** Skills Hub `EXPECTED_FLOORS` 健康下限 + `MIN_TOTAL=1500`
- `.github/workflows/skills-index-freshness.yml` — **NEW 2026-05-26** 每 4h Skills Hub watchdog cron（149 行）
- `website/src/data/skills-meta.json` — **NEW 2026-05-26** 新鲜度元数据（`generated_at` + per-source counts）
- `tools/skills_hub.py:3046-3058` — **NEW 2026-05-26** install_from_quarantine 拒 symlink
- `optional-skills/security/web-pentest/SKILL.md` — **NEW 2026-05-26** Web 渗透测试 skill
- `optional-skills/autonomous-ai-agents/openhands/SKILL.md` — **NEW 2026-05-26** OpenHands CLI delegation skill
- `optional-skills/software-development/code-wiki/SKILL.md` — **NEW 2026-05-26** 代码 wiki 生成 skill
- `tools/skills_hub.py:2429 BrowseShSource` — **NEW 2026-05-27** browse.sh 第 8 个 catalog 源（Browserbase 200+ 站点专用浏览器自动化 SKILL.md）
