---
title: 模型元数据缓存与智能路由
created: 2026-04-07
updated: 2026-04-07
type: concept
tags: [architecture, model-routing, performance, caching]
sources: [raw/articles/code-analysis-2026-04-07.md]
---

# 模型元数据缓存与智能路由

## 设计原理

Hermes 支持 200+ 模型和多个提供商。每个模型有不同的上下文窗口、定价、能力。Hermes 实现了**模型元数据缓存**和**提供商路由**，自动优化 API 调用。

## 模型元数据

```python
# agent/model_metadata.py

# 模型上下文窗口映射
MODEL_CONTEXT_LENGTHS = {
    "claude-opus-4.6": 200000,
    "claude-sonnet-4": 200000,
    "gpt-4o": 128000,
    "gemini-2.5-pro": 1000000,
    # ...
}

# Token 估算
def estimate_tokens_rough(text: str) -> int:
    """粗略 token 估算（4 字符/token）"""
    return len(text) // 4

def estimate_messages_tokens_rough(messages: list) -> int:
    """估算消息列表的 token 数"""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += estimate_tokens_rough(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and "text" in part:
                    total += estimate_tokens_rough(part["text"])
    return total

def estimate_request_tokens_rough(messages, system_prompt="", tools=None) -> int:
    """估算请求的总 token 数（含系统提示和工具 schema）"""
    total = estimate_tokens_rough(system_prompt or "")
    total += estimate_messages_tokens_rough(messages)
    if tools:
        total += estimate_tokens_rough(json.dumps(tools))
    return total
```

## 上下文窗口探测

```python
def get_next_probe_tier(current: int) -> int:
    """获取下一个探测层级"""
    tiers = [
        200000, 1000000,  # 常见层级
        128000, 256000, 512000,  # 中间层级
    ]
    tiers = sorted(set(tiers))
    for tier in tiers:
        if tier < current:
            return tier
    return tiers[0]  # 返回最小层级

def parse_context_limit_from_error(error_msg: str) -> Optional[int]:
    """从 API 错误消息中解析上下文限制"""
    # Anthropic: "prompt is too long: N tokens > M maximum"
    match = re.search(r'(\d+)\s*tokens?\s*>\s*(\d+)\s*maximum', error_msg)
    if match:
        return int(match.group(2))
    return None
```

## 定价估算

```python
# agent/usage_pricing.py

def estimate_usage_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """估算 API 调用成本"""
    pricing = {
        "claude-opus-4.6": {"input": 15.0, "output": 75.0},  # $/MTok
        "claude-sonnet-4": {"input": 3.0, "output": 15.0},
        "gpt-4o": {"input": 2.5, "output": 10.0},
        # ...
    }
    
    prices = pricing.get(model, {"input": 5.0, "output": 15.0})
    input_cost = (prompt_tokens / 1_000_000) * prices["input"]
    output_cost = (completion_tokens / 1_000_000) * prices["output"]
    return input_cost + output_cost
```

## OpenRouter 提供商路由

```python
# 提供商偏好
provider_preferences = {}
if self.providers_allowed:
    provider_preferences["order"] = self.providers_allowed
if self.providers_ignored:
    provider_preferences["ignore"] = self.providers_ignored
if self.providers_order:
    provider_preferences["order"] = self.providers_order
if self.provider_sort:
    provider_preferences["sort"] = self.provider_sort

# 发送到 OpenRouter
extra_body["provider"] = provider_preferences
```

### 提供商排序选项

```python
# sort 选项
"sort": "price"       # 按价格排序
"sort": "throughput"  # 按吞吐量排序
"sort": "latency"     # 按延迟排序
```

## 元数据缓存

```python
# OpenRouter 模型元数据缓存（1 小时 TTL）
_model_metadata_cache: dict = {}
_metadata_cache_time: float = 0
_METADATA_CACHE_TTL = 3600  # 1 小时

def fetch_model_metadata(model: str = None) -> dict:
    """获取模型元数据（带缓存）"""
    now = time.time()
    if now - _metadata_cache_time < _METADATA_CACHE_TTL:
        return _model_metadata_cache
    
    # 后台线程预温缓存
    threading.Thread(
        target=lambda: fetch_model_metadata(),
        daemon=True,
    ).start()
```

## 推理模型支持

```python
def _supports_reasoning_extra_body(self) -> bool:
    """判断是否可以安全发送 reasoning extra_body"""
    
    # 直接 Nous Portal
    if "nousresearch" in self._base_url_lower:
        return True
    
    # OpenRouter 路由
    if "openrouter" not in self._base_url_lower:
        return False
    
    # 已知支持推理的模型前缀
    reasoning_model_prefixes = (
        "deepseek/",
        "anthropic/",
        "openai/",
        "x-ai/",
        "google/gemini-2",
        "qwen/qwen3",
    )
    return any(self.model.lower().startswith(prefix) for prefix in reasoning_model_prefixes)
```

## 会话状态跟踪

```python
# 累积 token 使用量
self.session_prompt_tokens = 0
self.session_completion_tokens = 0
self.session_total_tokens = 0
self.session_api_calls = 0
self.session_input_tokens = 0
self.session_output_tokens = 0
self.session_cache_read_tokens = 0
self.session_cache_write_tokens = 0
self.session_reasoning_tokens = 0
self.session_estimated_cost_usd = 0.0
self.session_cost_status = "unknown"
self.session_cost_source = "none"

def reset_session_state(self):
    """重置所有会话级 token 计数器"""
    self.session_total_tokens = 0
    self.session_input_tokens = 0
    self.session_output_tokens = 0
    # ... 重置所有计数器
    self._user_turn_count = 0
```

## 优越性分析

### 与其他 Agent 框架对比

| 特性 | Hermes | Cursor | OpenCode |
|------|--------|--------|----------|
| 模型元数据缓存 | ✅ 1 小时 TTL | ❌ | ❌ |
| 提供商路由 | ✅ OpenRouter | ❌ | ❌ |
| 成本估算 | ✅ 实时 | ❌ | ❌ |
| 上下文探测 | ✅ 自动降级 | ❌ | ❌ |
| 推理模型支持 | ✅ 多提供商 | ✅ | ❌ |

## 相关文件

- `agent/model_metadata.py` — 模型元数据和上下文窗口
- `agent/usage_pricing.py` — 定价估算
- `hermes_cli/models.py` — 模型目录
