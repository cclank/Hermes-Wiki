---
title: 轨迹保存与训练数据生成
created: 2026-04-07
updated: 2026-04-14
type: concept
tags: [architecture, data-generation, training, trajectory, batch-runner]
sources: [agent/trajectory.py, batch_runner.py, toolset_distributions.py, environments/, run_agent.py]
---

# 轨迹保存与训练数据生成

## 这个系统解决什么问题

Hermes 仓库内置了一套**训练数据生产基础设施**（默认关闭，需显式启用）。核心思路：用 Agent 真实执行任务，把对话过程（含工具调用和推理）保存为标准格式，供 Nous Research 训练下一代工具调用模型。日常使用完全不涉及此功能。

```
批量任务数据集（JSONL）
    ↓ batch_runner.py（多进程并行执行）
AIAgent 真实执行每个任务
    ↓ save_trajectories=True
对话轨迹格式转换（ShareGPT 格式）
    ↓ trajectory.py
JSONL 训练数据
    ↓ environments/ + Atropos
RL 强化学习训练
```

## 什么场景会用到

| 场景 | 说明 |
|------|------|
| **Nous Research 内部** | 批量生成工具调用训练数据，迭代 Hermes 系列模型 |
| **模型微调** | 想训练自己的工具调用模型时，用 batch_runner 生成高质量 SFT 数据 |
| **单次调试** | `--save_trajectories` 保存单次对话轨迹，方便分析 Agent 行为 |
| **RL 训练** | 通过 environments/ 接入 Atropos 框架做强化学习 |
| **日常使用** | 默认关闭（`save_trajectories=False`），不影响正常对话 |

## 轨迹保存（trajectory.py）

当 `save_trajectories=True` 时，每次对话结束后自动保存。

**触发位置**：`run_agent.py` 的 `_save_trajectory()` 方法（line 2358），在 `run_conversation()` 结束时调用。

**输出格式**：ShareGPT 格式的 JSONL，每条记录包含：

```json
{
  "conversations": [
    {"from": "system", "value": "You are a function calling AI model..."},
    {"from": "human", "value": "用户问题"},
    {"from": "gpt", "value": "<think>\n推理过程\n</think>\n<tool_call>\n{...}\n</tool_call>"},
    {"from": "tool", "value": "<tool_response>\n{...}\n</tool_response>"},
    {"from": "gpt", "value": "<think>\n...\n</think>\n最终回答"}
  ],
  "timestamp": "2026-04-14T...",
  "model": "qwen3.6-plus",
  "completed": true
}
```

**输出文件**：
- 成功的对话 → `trajectory_samples.jsonl`
- 失败的对话 → `failed_trajectories.jsonl`

### 格式转换细节

`_convert_to_trajectory_format()`（`run_agent.py:2193`）负责将内部 OpenAI 格式转为训练格式：

| 转换规则 | 说明 |
|----------|------|
| `role: assistant` → `from: gpt` | 角色映射 |
| `role: user` → `from: human` | 角色映射 |
| `role: tool` → `from: tool` | 工具结果用 `<tool_response>` XML 包裹 |
| reasoning 字段 → `<think>` 标签 | 原生思维链保留 |
| `<REASONING_SCRATCHPAD>` → `<think>` | 非原生推理也统一格式 |
| 无推理内容 → 空 `<think></think>` | 保证每个 gpt turn 格式一致，方便训练 |
| tool_calls → `<tool_call>` XML | 工具调用用 XML 包裹 |

## Batch Runner（batch_runner.py）

规模化数据生成的核心组件，1287 行。

**使用方式**：

```bash
# 基本用法：从数据集批量执行
python batch_runner.py --dataset_file=data.jsonl --batch_size=10 --run_name=my_run

# 恢复中断的运行
python batch_runner.py --dataset_file=data.jsonl --batch_size=10 --run_name=my_run --resume

# 指定工具集分布
python batch_runner.py --dataset_file=data.jsonl --batch_size=10 --run_name=my_run --distribution=image_gen
```

**关键特性**：

| 特性 | 实现 |
|------|------|
| 并行执行 | `multiprocessing.Pool`（非线程池），真正的多进程 |
| 断点续传 | 检查点机制，中断后可 `--resume` 恢复 |
| 工具集采样 | 通过 `toolset_distributions.py` 按概率分布随机选择工具集 |
| 轨迹自动保存 | 每个子任务 `save_trajectories=True`，`skip_context_files=True` |
| 工具统计 | 汇总所有批次的工具使用统计 |
| HuggingFace 兼容 | 输出 JSONL schema 归一化，可直接上传 HF datasets |

### 工具集分布（toolset_distributions.py）

控制数据生成时启用哪些工具组合及其出现概率：

```python
DISTRIBUTIONS = {
    "default": {...},        # 所有工具 100%
    "image_gen": {...},      # 侧重图像生成工具
    "web_research": {...},   # 侧重网页搜索工具
    ...
}
```

这样可以定向生成特定工具组合的训练数据。

### 数据生成配置示例

`datagen-config-examples/` 目录提供现成配置：

```
trajectory_compression.yaml    # 轨迹压缩配置
web_research.yaml              # Web 研究任务配置
run_browser_tasks.sh           # 浏览器任务批量脚本
example_browser_tasks.jsonl    # 浏览器任务数据集示例
```

## RL 训练环境（environments/）

与 Tinker-Atropos 框架集成的强化学习环境：

| 环境 | 用途 |
|------|------|
| `hermes_base_env.py` | 基础 Agent 环境 |
| `agentic_opd_env.py` | Agentic 交互环境 |
| `web_research_env.py` | Web 研究任务环境 |
| `terminal_test_env/` | 终端命令测试环境 |
| `hermes_swe_env/` | 软件工程任务环境 |
| `tool_call_parsers/` | 工具调用解析器 |
| `agent_loop.py` | Agent 循环与环境的桥接 |

## 普通用户需要关心吗

**一般不需要**。这套系统默认全部关闭，日常聊天完全不受影响。

如果你想用到它：

```bash
# 单次对话保存轨迹（调试用）
python run_agent.py --save_trajectories --query="你的问题"

# 批量生成训练数据（模型训练用）
python batch_runner.py --dataset_file=your_tasks.jsonl --batch_size=10 --run_name=run1
```

## 相关页面

- [[agent-loop-and-prompt-assembly]] — `save_trajectories` 参数和 `_convert_to_trajectory_format()` 方法
- [[multi-agent-architecture]] — Batch Runner 作为大规模批量处理引擎
- [[context-compressor-architecture]] — 压缩后的轨迹数据更紧凑

## 相关文件

- `agent/trajectory.py` — 轨迹文件写入和格式转换工具函数
- `run_agent.py:2193-2371` — `_convert_to_trajectory_format()` + `_save_trajectory()`
- `batch_runner.py` — 批量运行器（1287 行）
- `toolset_distributions.py` — 工具集概率分布定义
- `environments/` — RL 训练环境
- `datagen-config-examples/` — 数据生成配置示例
