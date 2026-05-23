---
title: Prompt Caching 优化架构
created: 2026-04-07
updated: 2026-05-20
type: concept
tags: [architecture, module, performance, cost-optimization, anthropic]
sources: [agent/prompt_caching.py, agent/agent_init.py, run_agent.py]
---

# Prompt Caching — Anthropic 缓存优化架构

## 概述

Prompt Caching 位于 `agent/prompt_caching.py`（79 行，HEAD），实现 **Anthropic `system_and_3` 缓存策略**，在多轮对话中减少约 75% 的输入 token 成本。

> **历史说明**：此期间曾试验一个长期（1h）跨会话前缀缓存（`apply_anthropic_cache_control_long_lived`），但因易变的系统提示尾部会在会话中途变动、破坏上游缓存而被回退（#24778）。当前各处统一使用单一 `system_and_3` 布局，`apply_anthropic_cache_control` 是唯一的公开函数。

## TTL 档位（v0.14.0 起）

Anthropic 支持两档 TTL：

| 档位 | 写入成本 | 适用 |
|------|---------|------|
| `5m` (默认) | 1.25× 正常输入价 | 普通短对话、回合间停顿 < 5 分钟 |
| `1h` | 2× 正常输入价 | 长对话、回合间停顿超过 5 分钟、跨 session 复用 |

源码事实（`agent/prompt_caching.py:42-45`）：

```python
def _build_cache_marker(ttl: str = "5m") -> dict:
    """Build a cache_control marker dict for the given TTL ('5m' or '1h')."""
    marker = {"type": "ephemeral"}
    if ttl == "1h":
        marker["ttl"] = "1h"
    return marker
```

启用方式（`agent/agent_init.py:413-422`）：

```yaml
# config.yaml
prompt_caching:
  cache_ttl: 1h          # 默认 5m，已知值仅 {5m, 1h}
```

> **跨 session 1h 复用（v0.14.0 重点）**：通过 Anthropic / OpenRouter / Nous Portal 用 Claude 时，system prompt + skills + memory 这段 prefix 在 1 小时内对所有 session 都热 cache。`/new` 起新 session，首次 response 直接从 warm cache 起。背景 memory review fork 也命中同一 cache（PR #23828 / #24778 / #25434）。

## 架构原理

> **演进备注（2026-05）**：曾短暂引入过一个跨会话 1 小时长效前缀缓存布局（`feat(prompt-cache)` #23828），把工具数组 + 稳定系统前缀单独标 `ttl=1h`、易变内容（时间戳 / memory / USER profile）拆到尾部独立块。但实测发现易变层每轮都在变，导致**系统消息字节在会话中途变化**，反而打穿了上游缓存（OpenRouter / Nous Portal / Anthropic）。该长效布局已被 `fix(cache)` #24778 **整体回退**，回到下文描述的单一 `system_and_3` 布局，并确立不变量：**系统提示在一个会话内字节级静态（byte-static）** —— 见下文「系统提示字节静态不变量」。

| 策略 | 函数 | TTL 布局 | 适用路径 |
|------|------|----------|----------|
| **`system_and_3`** | `apply_anthropic_cache_control` | 4 断点全部同 TTL（5m 或 1h） | 默认路径（非长前缀） |
| **`prefix_and_2`** | `apply_anthropic_cache_control_long_lived` | 1h 稳定前缀 + 5m 滚动尾 | Claude on Anthropic / OpenRouter / Nous Portal（v2026.5.x+） |

可配置项：`prompt_caching.cache_ttl`（5m 默认，1h 可选；v0.12.0 起从硬编码改成 config）。

## system_and_3：原始策略

Anthropic 允许在消息中标记 `cache_control` 断点；断点前的内容会缓存，命中时只收 cache_read 费用（约正常费用的 10%）。Anthropic 限制**最多 4 个断点**。

| 断点 | 位置 | 缓存内容 | 稳定性 |
|---|---|---|---|
| 1 | 系统提示 | 身份 + 平台提示 + 技能索引 | 最高（轮内不变） |
| 2 | 倒数第 3 条非系统消息 | 早期对话 | 高 |
| 3 | 倒数第 2 条非系统消息 | 中期对话 | 中 |
| 4 | 倒数第 1 条非系统消息 | 最近对话 | 低（每轮滚动） |

四个断点全部使用同一个 TTL（5m 或 1h），由 `cache_ttl` 参数决定（源码 `agent/prompt_caching.py:59-89`）。

### 滚动窗口

```
轮次 1: [系统提示★] [用户1★] [助手1★] [助手2★]
轮次 2: [系统提示★] [用户1] [助手1] [用户2★] [助手2★] [用户3★]
                                       ↑断点向后滚动
```

★ = cache_control 标记。每个新请求新断点位置后移。

## prefix_and_2：跨会话长前缀策略（v2026.5.x+ 新增）

**触发条件**：Claude 模型且 provider 为 Anthropic、OpenRouter、Nous Portal（含 Portal-Claude 路径，v0.11+ 起 Portal Qwen 也走此路径）。`run_agent.py:12472` 处分支。

**核心思想**：把 4 个断点拆分成两层 TTL：

| 断点 | 位置 | TTL | 目的 |
|---|---|---|---|
| 1 | `tools[-1]` 数组末尾 | **1h** | tools array 整体缓存（Anthropic 缓存顺序 tools → system → messages） |
| 2 | 系统消息 `content[0]`（稳定前缀块） | **1h** | 跨会话稳定前缀（身份 + 工具描述 + 标准指导） |
| 3 | 倒数第 2 条非系统消息 | **5m** | 滚动窗口 |
| 4 | 倒数第 1 条非系统消息 | **5m** | 滚动窗口 |

**关键不变量**：
- 系统消息必须被**预先切分**成有序 content blocks，`block[0]` 是字节级稳定的跨会话前缀，后续块带上下文文件 / 易变后缀。若未切分则整段标 1h（fallback 路径，仍正确但 hit rate 降低）。
- 滚动窗口从 3 收缩到 2，腾出第 4 个断点给 tools。
- 标记 tools 最后一个 dict 缓存整个 tools 数组（Anthropic 文档：marker 放在你想包进缓存前缀的最后一块上）。OpenAI-wire 边界上，marker 在 OpenRouter/Nous Portal 转发到 Anthropic 时保留。

为什么用 OpenAI-wire 也能用？因为 marker 字段直接出现在 tool / message dict 上，OpenRouter 和 Nous Portal 透传该字段；最终由 Anthropic 后端读取生效。原生 Anthropic 路径由 `convert_tools_to_anthropic` 显式转换 marker（`mark_tools_for_long_lived_cache`，行 178-200）。

### 收益

第一次会话：tools + system prefix 写入 1h 缓存。第二次会话**冷启动**：系统提示和 tools 数组直接 cache_read 命中（不再付正常 token 费用），即使消息历史完全不同也能省下大头开销。Hermes 在 `prompt_builder` 中保证系统消息的 prefix block 字节稳定（同一 user config 下，第 0 块永远一样的 byte stream）。

## 核心组件

### `_apply_cache_marker`

```python
def _apply_cache_marker(msg, cache_marker, native_anthropic=False):
    # tool 角色：只在 native_anthropic 模式下标记
    # 空内容：在消息级别标记
    # 字符串内容：转换为 [{"type": "text", "text": ..., "cache_control": ...}]
    # 列表内容：在最后一个元素添加 cache_control
```

统一处理 Anthropic API 的多种消息格式变体（字符串、对象列表、tool result）。

### `_build_marker`

```python
def apply_anthropic_cache_control(
    api_messages,
    cache_ttl="5m",        # 缓存 TTL: 5分钟 或 1小时
    native_anthropic=False # 是否使用原生 Anthropic 格式
):
    """
    1. 深拷贝消息（不修改原始数据）
    2. 用 _build_marker(ttl) 创建 marker:
       {"type": "ephemeral"} 或 {"type": "ephemeral", "ttl": "1h"}
    3. 系统提示添加断点（如果是第一条消息）
    4. 从后向前找最后 3 条非系统消息（断点预算 4 - 已用），添加断点
    5. 返回标记后的消息列表
    """
```

`_build_marker(ttl)` 是独立的辅助函数：默认返回 `{"type": "ephemeral"}`，仅当 `ttl == "1h"` 时附加 `"ttl": "1h"`。模块只有这一种布局（`apply_anthropic_cache_control`）；早期版本曾有的 `apply_anthropic_cache_control_long_lived()` / `mark_tools_for_long_lived_cache()` 已随 #24778 删除。

### 3. 不同角色的处理

### `_mark_system_stable_block`

只标记系统消息 `content[0]`（稳定前缀块）。如果系统消息还是单段字符串（未切分），降级把整段包成单 block 标记——仍然正确，只是失去 prefix vs suffix 分离的 hit rate 收益。

## 配置入口

```yaml
# config.yaml
prompt_caching:
  cache_ttl: "5m"   # 或 "1h"
```

TTL 由 `config.yaml` 的 `prompt_caching.cache_ttl` 控制（默认 `"5m"`），只接受 `"5m"` 或 `"1h"` 两个 Anthropic 支持的档位，其他值被忽略并保持 `"5m"`：

```yaml
# config.yaml
prompt_caching:
  cache_ttl: "5m"   # 长会话且轮次间有停顿可设为 "1h"
```

**使用场景**：
- **5m（默认）**：适合快速连续对话，缓存命中率高
- **1h**：适合长时间对话间隔，容忍更高的缓存未命中（写入成本 2x，5m 是 1.25x，长 session 摊销下来更划算）

> 此 `cache_ttl` 是**会话内滚动窗口**的 TTL。它并不提供跨会话的前缀复用——短暂存在过的 `long_lived_prefix` / `long_lived_ttl` 配置键已随 #24778 移除。

## 系统提示字节静态不变量

Hermes 不变量：**系统提示在一个会话内必须字节级静态（byte-static）**。`run_agent.py` 中系统提示在会话首轮构建一次，缓存在 `self._cached_system_prompt` 上，之后每一轮**原样逐字节重放**。

- 续接会话（gateway 为每条消息新建 `AIAgent`）时，从 session DB 读回**已存储的系统提示**，而不是重建——重建会把模型自己写入的 memory 变化重新读进来，产生不同的系统提示从而打穿前缀缓存。
- 系统提示作为**单个 content 字符串**发送，保证字节稳定。

之所以确立这条不变量，是因为 #24778 诊断出：旧的长效前缀布局把系统提示拆成「稳定 / 上下文 / 易变」三块并每轮重新派生，易变块（时间戳 + memory 快照 + USER profile）每轮都变，导致 8 轮对话中系统块在分钟边界处 sha 翻转、当轮 `cached_tokens` 掉到 0。回退到单块布局后，会话内缓存在每个 provider 上才真正稳定生效。

v2026.5.x：`cache_ttl` 从 `config.yaml` 的 `prompt_caching.cache_ttl` 读取（`run_agent.py`），传给 `apply_anthropic_cache_control`；`_build_marker(ttl)` 抽出为辅助函数。Claude 在 Anthropic / OpenRouter / Nous Portal 上支持跨 session 的 1h prefix cache。OpenRouter 另有独立的响应缓存——`agent/auxiliary_client.py:build_or_headers()` 从 `openrouter.{response_cache, response_cache_ttl}`（默认开启，300s）发出 `X-OpenRouter-Cache*` 头。

### `prompt_caching.cache_ttl` 配置（v0.12.0+）

`agent/prompt_caching.py:51` 引入 `cache_ttl` 配置项，默认 `"5m"`：

```yaml
# config.yaml
auxiliary:
  prompt_caching:
    cache_ttl: 1h         # opt-in 1h tier (Anthropic 多 2x 价格但 12x 寿命)
```

加载位置：`agent/agent_init.py:475-485` 从 `auxiliary.prompt_caching.cache_ttl` 取值；config stub 在 `hermes_cli/config.py:820-822`。Bursty session 保持 cache 暖时省钱。

### 跨 Session 1h Claude Prefix Cache（v0.14.0+）

`agent/model_metadata.py:1268` `_CODEX_OAUTH_CONTEXT_CACHE_TTL = 3600  # 1 hour`：

用 Claude 走 Anthropic / OpenRouter / Nous Portal 时，**system prompt + skills + memory 的 prefix 在 session 之间复用 1 小时**：
- `/new` session 第一次回复又快又便宜，因为上次 cache 仍然热
- 后台 memory review 也吃 cache，不再每轮全价

> 等同于 v0.10.0 引入的 "冻结快照"机制扩展到跨 session 维度：之前一个 session 内多轮 turn 共享前缀；现在多个 session 共享同一前缀。

## 成本效益

`config.yaml` 中 `prompt_caching.cache_ttl: "1h"` 开启 1 小时 TTL，让 system prompt 的 cache prefix 可以**跨 session 命中**。覆盖 Anthropic 原生、OpenRouter、Nous Portal 三条 Claude 路径。

`run_agent.py:1455-1470` 读取配置（未知值回退 `"5m"`），实际生效值会在启动 banner 打印：`💾 Prompt caching: ENABLED (<source>, <ttl> TTL)`。

### 系统提示在 session 内字节稳定（PR #24778，b06e999）

之前为了榨干 cache hit 用过 "long-lived prefix layout"（保留 prefix 在多次系统提示重建间稳定），但维护成本高且容易因细微差异破坏命中。新策略：**系统提示在一个 session 内保证 byte-static**——即工具索引、技能索引、内存快照都在 session 启动时冻结一份，turn-by-turn 不再重新组装。这样：

- 不需要 "long-lived prefix" 那套 patch / preserve-prefix 逻辑
- 缓存命中等价于 "system prompt 字节完全一致"——更鲁棒，调试更直接
- 跨 session（1h TTL 模式下）只要系统提示 + 工具 schema 没变，仍然能复用

提交信息原文："kill long-lived prefix layout — system prompt is now byte-static within a session"。

之前（v0.11 及更早）TTL 是硬编码的，v0.12.0 起改成可配置（PR #15065，salvage of #12659）。1h TTL 对**间歇性突发**会话特别有用（用户离开 30 分钟后回来，缓存未过期）。

## 成本对比（示意）

假设系统提示 + tools 共 8000 tokens，每轮消息平均 2000 tokens：

| 场景 | 无缓存 | system_and_3（5m） | prefix_and_2（1h prefix） |
|---|---|---|---|
| 单一会话 10 轮 | 100K tokens | ~30K tokens（命中） | ~28K tokens |
| 30 分钟后冷启动 1 轮 | 10K tokens | 10K（缓存过期） | **1K cache_read + 2K** |

prefix_and_2 的真正价值在**冷启动**：会话切换、`/new`、新进程，第一轮就能复用上一次会话留下的 1h 前缀缓存。

## 设计原则

| 维度 | 无缓存 | Prompt Caching |
|---|---|---|
| 系统提示成本 | 每次付费 | 仅首次付费 |
| 早期对话成本 | 每次付费 | 命中时仅付 cache_read |
| 延迟 | 无影响 | 缓存命中时降低 |
| 代码复杂度 | 低 | 79 行纯函数 |
| 适用场景 | 所有模型 | 仅 Anthropic 模型 |

### 纯函数设计

```python
# 无类状态，无 AIAgent 依赖
# 输入消息列表 → 输出标记后的消息列表
# 深拷贝确保不修改原始数据
```

这使得缓存逻辑可以独立测试，且不影响主对话流程。

## 集成点与 Provider 适用范围

Prompt caching 在 `run_agent.py` 构建 API 请求时被调用：
1. 构建完整消息列表，把 `_cached_system_prompt` 作为单字符串 system 消息插到最前
2. 如果 `self._use_prompt_caching` 为真 → 调用 `apply_anthropic_cache_control(api_messages, cache_ttl=self._cache_ttl, native_anthropic=self._use_native_cache_layout)`
3. 兜底清理孤立 tool 结果后发送给 API

是否启用、用哪种布局由 `_anthropic_prompt_cache_policy()` 决定，返回 `(should_cache, use_native_layout)`：

| 端点 | should_cache | 布局 |
|---|---|---|
| 原生 Anthropic（含 OAuth 订阅） | True | native（标记打在 content 内层块上） |
| OpenRouter 上的 Claude | True | envelope（标记打在消息外层） |
| Nous Portal 上的 Claude | True | envelope（Portal 代理到 OpenRouter） |
| Nous Portal 上的 Qwen（如 qwen3.6-plus） | True | envelope |
| Alibaba / Qwen 系（OpenCode 等） | True | envelope |
| 其他 provider | False | 不缓存 |

> **Portal Qwen 的 TTL 限制（#24702）**：Nous Portal Qwen 最终代理到 Alibaba DashScope，其 Context Cache 只支持单一 5 分钟 ephemeral TTL，`ttl="1h"` 会被上游静默丢弃。因此 Portal Qwen 走标准 `system_and_3` 5m 布局——`cache_ttl="1h"` 对它无效。1h TTL 仅对 Anthropic / OpenRouter 的 Anthropic 路由真正生效。

## 与其他系统的关系

- [[prompt-builder-architecture]] — 必须保证系统消息 `content[0]` 字节稳定，否则 1h 前缀缓存命中率会大幅下降
- [[provider-transport-architecture]] — `AnthropicTransport` / `ChatCompletionsTransport` 在 build_kwargs 阶段透传 marker
- [[auxiliary-client-architecture]] — 辅助模型不使用 prompt caching（避免污染主会话 prefix cache，且辅助任务通常一次性）
- [[context-compressor-architecture]] — 压缩会冻结快照保留 prefix cache，详见 prefix-cache 友好的 OpenClaw 对比段
- [[smart-model-routing]] — 缓存价格信息来自 models.dev
