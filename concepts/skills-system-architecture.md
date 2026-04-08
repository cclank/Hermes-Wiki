---
title: Skills System Architecture
created: 2026-04-07
updated: 2026-04-07
type: concept
tags: [skill, architecture, module, prompt-builder]
sources: [raw/articles/code-analysis-2026-04-07.md]
---

# Skills System Architecture

## Overview

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

## 相关文件

- `tools/skills_tool.py` — 技能工具实现（1378 行）
- `agent/prompt_builder.py` — Prompt 构建与技能索引
- `agent/skill_utils.py` — 技能解析工具函数
- `agent/skill_commands.py` — 技能斜杠命令
- `tools/skills_sync.py` — 技能同步机制
- `tools/skills_hub.py` — 技能中心（搜索/安装）
- `tools/skill_manager_tool.py` — 技能管理工具
