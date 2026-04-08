---
title: 轨迹保存与数据生成系统
created: 2026-04-07
updated: 2026-04-07
type: concept
tags: [architecture, data-generation, training, trajectory]
sources: [raw/articles/code-analysis-2026-04-07.md]
---

# 轨迹保存与数据生成系统

## 设计原理

Hermes 不仅是一个 Agent 框架，还是**ML 训练数据生成工具**。支持保存对话轨迹用于训练下一代工具调用模型。

## 轨迹保存

```python
# agent/trajectory.py

def save_trajectory(
    messages: list,
    model: str,
    task_id: str,
    output_path: str,
    format: str = "jsonl"
):
    """保存对话轨迹到文件"""
    
    trajectory = {
        "task_id": task_id,
        "model": model,
        "timestamp": datetime.now().isoformat(),
        "messages": messages,
        "tool_calls": extract_tool_calls(messages),
        "final_response": messages[-1].get("content"),
    }
    
    if format == "jsonl":
        with open(output_path, "a") as f:
            f.write(json.dumps(trajectory) + "\n")
```

## Scratchpad 转换为 Think

```python
# 将 scratchpad 转换为 <think> 标签
def convert_scratchpad_to_think(messages: list) -> list:
    for msg in messages:
        if msg.get("role") == "assistant" and "scratchpad" in msg:
            scratchpad = msg.pop("scratchpad")
            content = msg.get("content", "")
            msg["content"] = f"<think>{scratchpad}</think>\n\n{content}"
    return messages

def has_incomplete_scratchpad(message: dict) -> bool:
    """检查是否有未完成的 scratchpad"""
    scratchpad = message.get("scratchpad", "")
    return scratchpad and not scratchpad.strip().endswith("</think>")
```

## 上下文压缩

```python
# agent/context_compressor.py

class ContextCompressor:
    def __init__(self, model, context_length, threshold_percent=0.8):
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
    
    def __init__(self, tasks: list, output_path: str):
        self.tasks = tasks
        self.output_path = output_path
    
    def run(self, max_workers: int = 8):
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self._run_task, task): task
                for task in self.tasks
            }
            for future in as_completed(futures):
                task = futures[future]
                result = future.result()
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
| 批量运行器 | ✅ 多线程 | ❌ | ❌ |
| RL 环境 | ✅ Atropos 集成 | ❌ | ❌ |
| 上下文压缩 | ✅ 用于训练 | N/A | N/A |
| 数据生成配置 | ✅ 示例配置 | ❌ | ❌ |

## 相关文件

- `agent/trajectory.py` — 轨迹保存
- `agent/context_compressor.py` — 上下文压缩
- `batch_runner.py` — 批量运行器
- `environments/` — RL 训练环境
