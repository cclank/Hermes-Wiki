---
title: 大型工具结果处理与上下文保护
created: 2026-04-07
updated: 2026-04-07
type: concept
tags: [architecture, context-management, performance]
sources: [tools/tool_result_storage.py, tools/budget_config.py, run_agent.py]
---

# 大型工具结果处理与上下文保护

## 设计原理

工具可能返回大型结果（如 `search_files` 搜索整个代码库、`terminal` 执行长输出命令）。如果直接放入对话历史，会快速消耗上下文窗口。Hermes 实现了**智能文件化机制**，将大型结果保存到磁盘，只保留预览。

## 三层溢出防护

大型工具结果通过三层机制递进防护（`tools/tool_result_storage.py` + `tools/budget_config.py`）：

```text
Layer 1: 工具内截断        — 各工具自己预截断输出（search_files 等）
Layer 2: 单结果持久化      — 超 100K 字符 → 写入 sandbox 磁盘，context 只保留 1.5K 预览
Layer 3: 轮次聚合预算      — 单轮所有结果合计超 200K → 最大的溢出到磁盘
```

### 阈值配置（`tools/budget_config.py`）

```python
DEFAULT_RESULT_SIZE_CHARS  = 100_000   # Layer 2: 单结果持久化阈值
DEFAULT_TURN_BUDGET_CHARS  = 200_000   # Layer 3: 轮次聚合上限
DEFAULT_PREVIEW_SIZE_CHARS = 1_500     # 持久化后的内联预览大小

# read_file 被 pin 为 ∞，防止"持久化→读取→再持久化"死循环
PINNED_THRESHOLDS = {"read_file": float("inf")}
```

阈值解析优先级：`PINNED_THRESHOLDS > tool_overrides > registry per-tool > default`

### Layer 2: 单结果持久化（`maybe_persist_tool_result()`）

工具返回后，如果输出超过阈值：
1. 通过 `env.execute()` 将完整结果写入 sandbox 的 `/tmp/hermes-results/{tool_use_id}.txt`
2. context 内容替换为 `<persisted-output>` 标签，包含 1,500 字符预览 + 文件路径
3. agent 可通过 `read_file` 访问完整输出
4. sandbox 写入失败时回退为内联截断

### Layer 3: 轮次聚合预算（`enforce_turn_budget()`）

单轮内如果多个中等大小结果合计超过 200K 字符：
- 按大小降序排列未持久化的结果
- 逐个溢出到磁盘，直到总量低于预算

这层捕获的是"单个不超限但合计超限"的场景。

## 上下文窗口保护

### 预飞行压缩

```python
# 在进入主循环之前，检查加载的对话历史是否已超过上下文阈值
if (
    self.compression_enabled
    and len(messages) > self.context_compressor.protect_first_n
                    + self.context_compressor.protect_last_n + 1
):
    # 包含工具 schema tokens — 多工具时可能增加 20-30K+ tokens
    _preflight_tokens = estimate_request_tokens_rough(
        messages,
        system_prompt=active_system_prompt or "",
        tools=self.tools or None,
    )
    
    if _preflight_tokens >= self.context_compressor.threshold_tokens:
        # 主动压缩，而不是等待 API 错误
        for _pass in range(3):  # 最多 3 轮
            _orig_len = len(messages)
            messages, active_system_prompt = self._compress_context(...)
            if len(messages) >= _orig_len:
                break  # 无法进一步压缩
            if _preflight_tokens < self.context_compressor.threshold_tokens:
                break  # 已低于阈值
```

### 413 错误处理

```python
is_payload_too_large = (
    status_code == 413
    or 'request entity too large' in error_msg
    or 'payload too large' in error_msg
)

if is_payload_too_large:
    compression_attempts += 1
    if compression_attempts > max_compression_attempts:
        return {"error": "Request payload too large: max compression attempts reached."}
    
    # 尝试压缩后重试
    messages, active_system_prompt = self._compress_context(...)
    if len(messages) < original_len:
        time.sleep(2)  # 压缩后短暂暂停
        restart_with_compressed_messages = True
        break
```

### 上下文长度错误检测

```python
is_context_length_error = any(phrase in error_msg for phrase in [
    'context length', 'context size', 'maximum context',
    'token limit', 'too many tokens', 'reduce the length',
    'exceeds the limit', 'context window',
    'request entity too large',  # OpenRouter/Nous 413 安全网
    'prompt is too long',  # Anthropic
    'prompt exceeds max length',  # Z.AI / GLM
])

# 启发式：Anthropic 有时返回通用 400 错误
if not is_context_length_error and status_code == 400:
    ctx_len = getattr(self.context_compressor, 'context_length', 200000)
    is_large_session = approx_tokens > ctx_len * 0.4 or len(api_messages) > 80
    is_generic_error = len(error_msg.strip()) < 30
    if is_large_session and is_generic_error:
        is_context_length_error = True  # 视为上下文溢出

# 服务器断开也可能是上下文过大
if not is_context_length_error and not status_code:
    _is_server_disconnect = (
        'server disconnected' in error_msg
        or 'peer closed connection' in error_msg
    )
    if _is_server_disconnect and approx_tokens > ctx_len * 0.6:
        is_context_length_error = True  # 视为上下文溢出
```

### 429 长上下文层级错误

```python
# Anthropic 返回 429 "Extra usage is required for long context requests"
# 当 Claude Max 订阅不包含 1M 上下文层级时
_is_long_context_tier_error = (
    status_code == 429
    and "extra usage" in error_msg
    and "long context" in error_msg
    and "sonnet" in self.model.lower()
)

if _is_long_context_tier_error:
    _reduced_ctx = 200000  # 降级到标准层级 200K
    compressor.context_length = _reduced_ctx
    compressor.threshold_tokens = int(_reduced_ctx * compressor.threshold_percent)
    # 不持久化 — 这是订阅层级限制，不是模型能力
    compressor._context_probe_persistable = False
```

## 代理安全写入

```python
class _SafeWriter:
    """透明 stdio 包装器，捕获 broken pipe 的 OSError/ValueError"""
    
    def write(self, data):
        try:
            return self._inner.write(data)
        except (OSError, ValueError):
            return len(data) if isinstance(data, str) else 0
    
    def flush(self):
        try:
            self._inner.flush()
        except (OSError, ValueError):
            pass

def _install_safe_stdio() -> None:
    """包装 stdout/stderr，使尽力而为的控制台输出不会崩溃 Agent"""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and not isinstance(stream, _SafeWriter):
            setattr(sys, stream_name, _SafeWriter(stream))
```

**为什么需要？**
- systemd 服务/Docker 容器中，stdout/stderr 管道可能不可用
- 子代理线程退出后，共享 stdout 句柄可能已关闭
- 防止 `OSError: [Errno 5] Input/output error` 崩溃 Agent

## Surrogate 字符清理

```python
_SURROGATE_RE = re.compile(r'[\ud800-\udfff]')

def _sanitize_surrogates(text: str) -> str:
    """将孤立代理码点替换为 U+FFFD（替换字符）"""
    if _SURROGATE_RE.search(text):
        return _SURROGATE_RE.sub('\ufffd', text)
    return text

# 代理在 UTF-8 中无效，会使 OpenAI SDK 中的 json.dumps() 崩溃
def _sanitize_messages_surrogates(messages: list) -> bool:
    """清理消息列表中所有字符串内容的代理字符"""
    found = False
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, str) and _SURROGATE_RE.search(content):
            msg["content"] = _SURROGATE_RE.sub('\ufffd', content)
            found = True
    return found
```

**为什么需要？**
- 剪贴板粘贴富文本（Google Docs, Word）可能注入孤立代理
- 会导致 JSON 序列化崩溃

## 预算警告清理

```python
_BUDGET_WARNING_RE = re.compile(
    r"\[BUDGET(?:\s+WARNING)?:\s+Iteration\s+\d+/\d+\..*?\]",
    re.DOTALL,
)

def _strip_budget_warnings_from_history(messages: list) -> None:
    """从工具结果消息中移除预算压力警告"""
    for msg in messages:
        if not isinstance(msg, dict) or msg.get("role") != "tool":
            continue
        content = msg.get("content")
        if not isinstance(content, str) or "_budget_warning" not in content and "[BUDGET" not in content:
            continue
        
        # 尝试 JSON 解析（常见情况）
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict) and "_budget_warning" in parsed:
                del parsed["_budget_warning"]
                msg["content"] = json.dumps(parsed, ensure_ascii=False)
                continue
        except (json.JSONDecodeError, TypeError):
            pass
        
        # 回退：从纯文本工具结果中移除模式
        cleaned = _BUDGET_WARNING_RE.sub("", content).strip()
        if cleaned != content:
            msg["content"] = cleaned
```

**为什么需要？**
- 预算警告是**轮次作用域**信号，不应泄漏到重放历史
- GPT 系列模型会将其解释为仍然活跃的指令，避免在后续所有轮次中调用工具

## 优越性分析

### 上下文节省

| 场景 | 无保护 | 有保护 | 节省 |
|------|--------|--------|------|
| 大型搜索输出 | 100K chars | 1.5K + 文件引用 | ~98.5% |
| 长终端输出 | 50K chars | 1.5K + 文件引用 | ~97% |
| 预飞行压缩 | 等待 API 错误 | 主动压缩 | 避免失败 |

### 与其他 Agent 框架对比

| 特性 | Hermes | Cursor | OpenCode |
|------|--------|--------|----------|
| 大型结果文件化 | ✅ 自动 | ✅ 自动 | ❌ 截断 |
| 可配置阈值 | ✅ BudgetConfig | ❌ 固定 | N/A |
| 预飞行压缩 | ✅ | ✅ | ❌ |
| Surrogate 清理 | ✅ | ❌ | ❌ |
| 预算警告清理 | ✅ | N/A | N/A |
| 安全 stdio | ✅ | N/A | N/A |

## 相关页面

- [[context-compressor-architecture]] — 上下文压缩与预飞行压缩机制
- [[parallel-tool-execution]] — 并行工具执行产生大型结果的场景
- [[model-tools-dispatch]] — 工具结果经过统一格式处理

## 相关文件

- `tools/tool_result_storage.py` — 三层溢出防护（Layer 2 + Layer 3）
- `tools/budget_config.py` — 阈值配置与优先级解析
- `run_agent.py` — Surrogate 清理、预算警告清理
- `agent/context_compressor.py` — 上下文压缩
