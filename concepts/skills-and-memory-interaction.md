---
title: Skills and Memory Interaction
created: 2026-04-07
updated: 2026-04-07
type: concept
tags: [skill, memory, architecture, best-practice]
sources: [raw/articles/code-analysis-2026-04-07.md]
---

# Skills and Memory Interaction

## 设计哲学

Skills 和 Memory 是 Hermes Agent 的两种**不同类型的持久化机制**，它们互补而非竞争：

| 维度 | Memory | Skills |
|------|--------|--------|
| **存储内容** | 事实、偏好、经验教训 | 程序化知识、工作流 |
| **容量** | MEMORY.md: 2200 字符<br>USER.md: 1375 字符 | 无硬性限制 |
| **格式** | 条目列表（§ 分隔） | Markdown 文档 + 文件结构 |
| **用途** | 快速查阅稳定事实 | 复杂任务的完整指南 |
| **加载方式** | 注入系统提示 | 渐进式披露（元数据 → 完整内容） |
| **何时使用** | 用户偏好、环境事实、工具特性 | 5+ 工具调用的复杂工作流 |

## 决策树

```
完成任务后，问：

这个知识是...
├─ 一个简单的稳定事实？ → 保存到 Memory
│   （如 "用户喜欢中文"、"服务器在 /root"）
│
└─ 一个复杂的程序化流程？ → 创建为 Skill
    （如 "部署 ML 模型的步骤"、"调试 X 问题的流程"）
```

## 行为指导

### Memory 指导（注入系统提示）

```
You have persistent memory across sessions. Save durable facts using the memory tool:
user preferences, environment details, tool quirks, and stable conventions.
Memory is injected into every turn, so keep it compact and focused on facts
that will still matter later.

Prioritize what reduces future user steering — the most valuable memory is one
that prevents the user from having to correct or remind you again.

Do NOT save task progress, session outcomes, completed-work logs, or temporary
TODO state to memory; use session_search to recall those from past transcripts.
```

### Skills 指导（注入系统提示）

```
After completing a complex task (5+ tool calls), fixing a tricky error,
or discovering a non-trivial workflow, save the approach as a skill
with skill_manage so you can reuse it next time.

When using a skill and finding it outdated, incomplete, or wrong,
patch it immediately with skill_manage(action='patch') — don't wait to be asked.
Skills that aren't maintained become liabilities.
```

## 技能自我改进循环

```
1. Agent 执行复杂任务（5+ 工具调用）
   ↓
2. 检测到新模式或工作流
   ↓
3. 使用 skill_manage(action='create') 创建技能
   ↓
4. 下次遇到类似任务 → skills_list 发现该技能
   ↓
5. skill_view 加载完整指令
   ↓
6. 执行过程中发现问题 → skill_manage(action='patch') 修复
   ↓
7. 技能持续改进
```

## Session Search 的作用

`session_search` 是第三种持久化机制，用于回忆**过去的对话**：

```
When the user references something from a past conversation or you suspect
relevant cross-session context exists, use session_search to recall it before
asking them to repeat themselves.
```

三种机制对比：

| 机制 | 内容 | 检索方式 |
|------|------|----------|
| **Memory** | 稳定事实 | 每轮自动注入系统提示 |
| **Skills** | 程序化知识 | 按需加载（渐进式披露） |
| **Session Search** | 过去对话记录 | FTS5 全文搜索 + LLM 摘要 |

## 实际示例

### 保存到 Memory

```python
# 用户纠正
memory(action='add', target='user', content='用户偏好使用中文交流')

# 环境事实
memory(action='add', target='memory', content='服务器是 Ubuntu 22.04，Python 3.11')

# 工具特性
memory(action='add', target='memory', content='patch 工具使用模糊匹配，minor whitespace 差异不会破坏它')
```

### 创建为 Skill

```python
# 复杂工作流
skill_manage(
    action='create',
    name='deploy-ml-model',
    content='---\nname: deploy-ml-model\n...'
)
```

## 维护优先级

```
Memory > Skills > Session Search
```

- **Memory** 最重要 — 每轮都注入，直接影响行为
- **Skills** 次之 — 按需加载，但影响复杂任务质量
- **Session Search** 最后 — 用于回忆上下文，不是核心行为

## 相关文件

- `agent/prompt_builder.py` — 指导文本定义
- `tools/memory_tool.py` — Memory 实现
- `tools/skills_tool.py` — Skills 实现
- `tools/session_search_tool.py` — Session Search 实现
- `hermes_state.py` — SessionDB（FTS5 搜索）
