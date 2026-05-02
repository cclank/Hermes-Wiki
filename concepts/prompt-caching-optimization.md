---
title: Prompt Caching 优化架构
created: 2026-04-07
updated: 2026-05-02
type: concept
tags: [architecture, module, performance, cost-optimization, anthropic]
sources: [agent/prompt_caching.py, run_agent.py, hermes_cli/config.py]
---

# Prompt Caching — Anthropic 缓存优化架构

## 概述

Prompt Caching 位于 `agent/prompt_caching.py`（2KB/72行），实现 **Anthropic `system_and_3` 缓存策略**，在多轮对话中减少约 75% 的输入 token 成本。

核心理念：**最多 4 个 cache_control 断点 — 系统提示 + 最后 3 条非系统消息。**

## 架构原理

### system_and_3 策略

Anthropic 的 prompt cache 允许在消息中标记 `cache_control` 断点。断点前的内容会被缓存，后续请求命中缓存时只收取极低的 cache_read 费用（约为正常费用的 10%）。

Anthropic 限制**最多 4 个断点**，Hermes 的分配策略：

| 断点 | 位置 | 缓存内容 | 稳定性 |
|---|---|---|---|
| 1 | 系统提示 | 身份 + 平台提示 + 技能索引 | 最高（跨所有轮次不变） |
| 2 | 倒数第 3 条消息 | 早期对话内容 | 高（前 2 轮不变） |
| 3 | 倒数第 2 条消息 | 中期对话内容 | 中（前 1 轮不变） |
| 4 | 最后 1 条消息 | 最近的对话内容 | 低（每轮滚动） |

### 滚动窗口机制

```
轮次 1: [系统提示★] [用户1★] [助手1] [助手2]
                        ↑断点2 ↑断点3  ↑断点4

轮次 2: [系统提示★] [用户1] [助手1★] [用户2★] [助手2★]
                        ↑新断点2 ↑新断点3 ↑新断点4

轮次 3: [系统提示★] [用户1] [助手1] [用户2] [助手2★] [用户3★] [助手3★]
                                                      ↑新断点2 ↑新断点3 ↑新断点4
```

★ = cache_control 标记。每次新请求时，断点窗口向后滚动。

## 核心组件

### 1. cache_control 标记注入

```python
def _apply_cache_marker(msg, cache_marker, native_anthropic=False):
    """
    处理所有消息格式变体:
    
    1. tool 角色 → 只在 native_anthropic 模式下标记
    2. 空内容 → 直接在消息级别标记
    3. 字符串内容 → 转换为 [{"type": "text", "text": ..., "cache_control": ...}]
    4. 列表内容 → 在最后一个元素上添加 cache_control
    """
```

**设计考量**：Anthropic API 接受多种消息格式（字符串、对象列表、工具结果），`_apply_cache_marker` 统一处理所有格式。

### 2. 主函数

```python
def apply_anthropic_cache_control(
    api_messages,
    cache_ttl="5m",        # 缓存 TTL: 5分钟 或 1小时
    native_anthropic=False # 是否使用原生 Anthropic 格式
):
    """
    1. 深拷贝消息（不修改原始数据）
    2. 创建 marker: {"type": "ephemeral"} 或 {"type": "ephemeral", "ttl": "1h"}
    3. 系统提示添加断点（如果是第一条消息）
    4. 从后向前找最后 3 条非系统消息，添加断点
    5. 返回标记后的消息列表
    """
```

### 3. 不同角色的处理

| 角色 | 缓存策略 |
|---|---|
| system | 始终标记（最稳定的缓存点） |
| tool | 仅 native_anthropic 模式下在消息级别标记 |
| assistant/user | 在 content 的最后一个元素上标记 |

## TTL 配置

```python
marker = {"type": "ephemeral"}         # 默认: 5 分钟 TTL
marker = {"type": "ephemeral", "ttl": "1h"}  # 1 小时 TTL
```

**使用场景**：
- **5m（默认）**：适合快速连续对话，缓存命中率高
- **1h**：适合长时间对话间隔，容忍更高的缓存未命中

### `prompt_caching.cache_ttl` 配置（v2026.4.30+）

`hermes_cli/config.py:642-644` 暴露用户可配置：

```yaml
# config.yaml
prompt_caching:
  cache_ttl: "5m"   # 默认；唯一另一选项是 "1h"
```

**取值约束**：仅 Anthropic 支持的 tier `"5m"` / `"1h"`，其他值被忽略（在 `agent/prompt_caching.py:58` 显式比较 `if cache_ttl == "1h"`，不匹配则保留默认 `{"type": "ephemeral"}`）。

**何时改 1h**：突发会话需要长时间保温（用户间断回复但希望缓存不过期），定价上 1h tier 的写入成本更高，但跨长间隔的复用可以摊平成本。

## 成本效益

假设系统提示 2000 tokens，每次对话平均 5000 tokens：

| 场景 | 无缓存成本 | 缓存命中成本 | 节省 |
|---|---|---|---|
| 单轮（系统提示 + 1 条消息） | ~7000 tokens × 价格 | ~2000 tokens × cache_read + 5000 × 正常 | ~70% |
| 10 轮对话 | 10 × 7000 = 70K tokens | ~2000 × cache_read + (70K-2000) × 正常 | ~75% |
| 50 轮对话 | 50 × 7000 = 350K tokens | ~2000 × cache_read + (350K-2000) × 正常 | ~85% |

## 设计优越性

### 对比无缓存方案

| 维度 | 无缓存 | Prompt Caching |
|---|---|---|
| 系统提示成本 | 每次付费 | 仅首次付费 |
| 早期对话成本 | 每次付费 | 命中时仅付 cache_read |
| 延迟 | 无影响 | 缓存命中时降低 |
| 代码复杂度 | 低 | 72 行纯函数 |
| 适用场景 | 所有模型 | 仅 Anthropic 模型 |

### 纯函数设计

```python
# 无类状态，无 AIAgent 依赖
# 输入消息列表 → 输出标记后的消息列表
# 深拷贝确保不修改原始数据
```

这使得缓存逻辑可以独立测试，且不影响主对话流程。

## 集成点

Prompt caching 在 `run_agent.py` 的 `_build_api_kwargs()` 中被调用：
1. 构建完整消息列表
2. 如果当前 provider 是 Anthropic → 调用 `apply_anthropic_cache_control()`
3. 如果 `developer_role` 需要切换 → 将 system 消息转为 developer 角色
4. 发送给 API

## 与其他系统的关系

- [[smart-model-routing]] — 缓存成本信息来自 models.dev
- [[auxiliary-client-architecture]] — 辅助模型不使用 prompt caching
- [[context-compressor-architecture]] — 上下文压缩减少消息数量，间接影响缓存断点位置
