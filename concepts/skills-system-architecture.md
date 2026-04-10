---
title: Skills System Architecture
created: 2026-04-07
updated: 2026-04-10
type: concept
tags: [skill, architecture, module, prompt-builder]
sources: [tools/skills_tool.py, tools/skill_manager_tool.py, tools/skills_hub.py, tools/skills_guard.py, run_agent.py, agent/prompt_builder.py]
---

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
