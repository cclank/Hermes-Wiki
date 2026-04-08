---
title: 轨迹保存与数据生成系统
created: 2026-04-07
updated: 2026-04-07
type: concept
tags: [architecture, data-generation, training, trajectory]
sources: [hermes-agent 源码分析 2026-04-07]
---

# 轨迹保存与数据生成系统

## 设计原理

Hermes 不仅是一个 Agent 框架，还是**ML 训练数据生成工具**。支持保存对话轨迹用于训练下一代工具调用模型。

## 轨迹保存

```python
# agent/trajectory.py

def save_trajectory(
    trajectory: List[Dict],
    model: str,
    completed: bool,
    filename: str = None,
):
    """保存对话轨迹到文件"""
    
    output = {
        "conversations": trajectory,
        "timestamp": datetime.now().isoformat(),
        "model": model,
        "completed": completed,
    }
    
    path = filename or _default_trajectory_path()
    with open(path, "a") as f:
        f.write(json.dumps(output) + "\n")
```

## Scratchpad 转换为 Think

```python
# 将 scratchpad 转换为 <think> 标签
def convert_scratchpad_to_think(content: str) -> str:
    """对单个字符串做标签替换"""
    content = content.replace("<REASONING_SCRATCHPAD>", "<think>")
    content = content.replace("</REASONING_SCRATCHPAD>", "</think>")
    return content

def has_incomplete_scratchpad(message: dict) -> bool:
    """检查是否有未完成的 scratchpad"""
    scratchpad = message.get("scratchpad", "")
    return scratchpad and not scratchpad.strip().endswith("</think>")
```

## 上下文压缩

```python
# agent/context_compressor.py

class ContextCompressor:
    def __init__(self, model, context_length, threshold_percent=0.50):
        self.model = model
        self.context_length = context_length
        self.threshold_tokens = int(context_length * threshold_percent)
        self.threshold_percent = threshold_percent
    
    def compress(self, messages, system_prompt, ...) -> tuple:
        """压缩对话历史"""
        
        # 保护首尾消息
        protect_first = self.protect_first_n
        protect_last = self.protect_last_n
        
        # 中间消息使用辅助模型生成摘要
        middle_messages = messages[protect_first:-protect_last]
        summary = self._generate_summary(middle_messages)
        
        # 构建压缩后的消息列表
        compressed = (
            messages[:protect_first] +
            [{"role": "assistant", "content": f"[Summary: {summary}]"}] +
            messages[-protect_last:]
        )
        
        return compressed, system_prompt
```

## Batch Runner

```python
# batch_runner.py

class BatchRunner:
    """批量运行任务，用于数据生成"""
    
    def __init__(
        self,
        dataset_file: str,
        batch_size: int,
        run_name: str,
        distribution: dict,
        max_iterations: int,
        num_workers: int = 4,  # 默认 4 个 worker
        ...
    ):
        self.dataset_file = dataset_file
        self.batch_size = batch_size
        self.run_name = run_name
        self.num_workers = num_workers
    
    def run(self):
        # 使用 multiprocessing.Pool（非 ThreadPoolExecutor）
        with multiprocessing.Pool(processes=self.num_workers) as pool:
            results = pool.map(self._run_task, self._load_batch())
            for task, result in zip(self._load_batch(), results):
                self._save_result(task, result)
    
    def _run_task(self, task: dict) -> dict:
        agent = AIAgent(
            model=task.get("model"),
            save_trajectories=True,
            skip_context_files=True,  # 避免污染轨迹
        )
        return agent.run_conversation(task["prompt"])
```

## 训练环境

```python
# environments/
# RL 训练环境

hermes_base_env.py       # 基础环境
agentic_opd_env.py       # Agentic 环境
web_research_env.py      # Web 研究环境
terminal_test_env.py     # 终端测试环境

# 与 Tinker-Atropos 集成
# git submodule: tinker-atropos
```

## 数据生成配置

```yaml
# datagen-config-examples/
trajectory_compression.yaml
web_research.yaml
run_browser_tasks.sh
example_browser_tasks.jsonl
```

## 优越性分析

### 与其他 Agent 框架对比

| 特性 | Hermes | Claude Code | OpenCode |
|------|--------|-------------|----------|
| 轨迹保存 | ✅ JSONL | ❌ | ❌ |
| 批量运行器 | ✅ 多进程 (multiprocessing.Pool) | ❌ | ❌ |
| RL 环境 | ✅ Atropos 集成 | ❌ | ❌ |
| 上下文压缩 | ✅ 用于训练 | N/A | N/A |
| 数据生成配置 | ✅ 示例配置 | ❌ | ❌ |

## 相关页面

- [[multi-agent-architecture]] — Batch Runner 大规模批量处理引擎
- [[context-compressor-architecture]] — 上下文压缩用于轨迹数据处理
- [[aiagent-class]] — AIAgent 的 save_trajectories 参数

## 相关文件

- `agent/trajectory.py` — 轨迹保存
- `agent/context_compressor.py` — 上下文压缩
- `batch_runner.py` — 批量运行器
- `environments/` — RL 训练环境
