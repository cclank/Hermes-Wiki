---
title: 中断传播与容错机制
created: 2026-04-07
updated: 2026-04-15
type: concept
tags: [architecture, reliability, fault-tolerance, interrupt]
sources: [run_agent.py, gateway/run.py, agent/error_classifier.py, tools/credential_pool.py]
---

# 中断传播与容错机制

## 设计原理

Agent 可能执行长时间运行的任务（多次工具调用、子代理委派）。用户需要能够：
1. **中断当前操作** — 发送新消息或按 Ctrl+C
2. **优雅处理失败** — API 错误、网络断开、凭证过期
3. **自动恢复** — 重试、回退、凭证轮换

Hermes 实现了**多层中断和容错机制**。

## 中断机制

### 中断标志

```python
class AIAgent:
    def __init__(self):
        self._interrupt_requested = False
        self._interrupt_message = None
    
    @property
    def is_interrupted(self) -> bool:
        """检查是否请求了中断"""
        return self._interrupt_requested
    
    def clear_interrupt(self):
        """清除中断状态"""
        self._interrupt_requested = False
        self._interrupt_message = None
```

### 中断传播到子代理

```python
# 父代理可以中断所有子代理
def _propagate_interrupt(self):
    with self._active_children_lock:
        for child in self._active_children:
            child._interrupt_requested = True
```

### API 调用中断

```python
def _interruptible_api_call(self, api_kwargs: dict):
    """在后台线程中运行 API 调用，使主循环可以检测中断"""
    
    result = {"response": None, "error": None}
    request_client_holder = {"client": None}
    
    def _call():
        try:
            if self.api_mode == "codex_responses":
                request_client_holder["client"] = self._create_request_openai_client(...)
                result["response"] = self._run_codex_stream(...)
            elif self.api_mode == "anthropic_messages":
                result["response"] = self._anthropic_messages_create(api_kwargs)
            else:
                request_client_holder["client"] = self._create_request_openai_client(...)
                result["response"] = request_client_holder["client"].chat.completions.create(**api_kwargs)
        except Exception as e:
            result["error"] = e
        finally:
            # 清理请求客户端
            request_client = request_client_holder.get("client")
            if request_client is not None:
                self._close_request_openai_client(request_client, reason="request_complete")
    
    t = threading.Thread(target=_call, daemon=True)
    t.start()
    
    while t.is_alive():
        t.join(timeout=0.3)  # 每 300ms 检查一次中断
        if self._interrupt_requested:
            # 强制关闭进行中的 HTTP 连接
            try:
                if self.api_mode == "anthropic_messages":
                    self._anthropic_client.close()
                    self._anthropic_client = build_anthropic_client(...)
                else:
                    request_client = request_client_holder.get("client")
                    if request_client is not None:
                        self._close_request_openai_client(request_client, reason="interrupt_abort")
            except Exception:
                pass
            raise InterruptedError("Agent interrupted during API call")
    
    if result["error"] is not None:
        raise result["error"]
    return result["response"]
```

### 主循环中断检查

```python
while api_call_count < self.max_iterations and self.iteration_budget.remaining > 0:
    # 检查中断请求
    if self._interrupt_requested:
        interrupted = True
        if not self.quiet_mode:
            self._safe_print("⚠️ Interrupted by user")
        break
    
    # ... 正常处理
```

### 流式 API 调用中断

```python
def _interruptible_streaming_api_call(self, api_kwargs: dict, ...):
    """流式变体，支持实时 token 投递"""
    
    for chunk in stream:
        if self._interrupt_requested:
            break  # 停止接收流
        
        # ... 处理 chunk
    
    # 清理
    if self._interrupt_requested:
        raise InterruptedError("Agent interrupted during streaming")
```

## 容错机制

### 凭证池轮换

```python
def _recover_with_credential_pool(self, *, status_code, has_retried_429, ...):
    """通过凭证池轮换尝试恢复"""
    
    pool = self._credential_pool
    if pool is None or status_code is None:
        return False, has_retried_429
    
    if status_code == 402:
        # 账单耗尽 — 立即轮换
        next_entry = pool.mark_exhausted_and_rotate(status_code=402, ...)
        if next_entry is not None:
            self._swap_credential(next_entry)
            return True, False
    
    if status_code == 429:
        if not has_retried_429:
            return False, True  # 第一次 429，重试相同凭证
        # 第二次 429，轮换到下一个凭证
        next_entry = pool.mark_exhausted_and_rotate(status_code=429, ...)
        if next_entry is not None:
            self._swap_credential(next_entry)
            return True, False
    
    if status_code == 401:
        # 尝试刷新当前凭证
        refreshed = pool.try_refresh_current()
        if refreshed is not None:
            self._swap_credential(refreshed)
            return True, has_retried_429
        # 刷新失败 — 轮换到下一个凭证
        next_entry = pool.mark_exhausted_and_rotate(status_code=401, ...)
        if next_entry is not None:
            self._swap_credential(next_entry)
            return True, False
    
    return False, has_retried_429
```

### Fallback 模型链

```python
# 配置示例
fallback_chain:
  - model: "anthropic/claude-opus-4.6"
    provider: "anthropic"
  - model: "openai/gpt-4o"
    provider: "openrouter"
  - model: "google/gemini-2.5-pro"
    provider: "openrouter"

def _try_activate_fallback(self):
    """激活下一个 fallback 模型"""
    if self._fallback_index >= len(self._fallback_chain):
        return False  # 无更多 fallback
    
    fallback = self._fallback_chain[self._fallback_index]
    self._fallback_index += 1
    
    # 切换模型/凭证
    self.model = fallback["model"]
    self.provider = fallback["provider"]
    # ... 重建客户端
    
    return True
```

### 结构化错误分类（error_classifier.py）

2026-04-09 引入的集中式错误分类器，替代了 `run_agent.py` 中分散的字符串匹配。所有 API 错误被分类为 13 种 `FailoverReason`，每种对应不同的恢复策略：

| 错误类型 | 恢复策略 |
|---------|---------|
| `auth` | 刷新/轮换凭证 |
| `billing` | 立即切换 Provider |
| `rate_limit` | 退避等待后轮换 |
| `context_overflow` | 压缩上下文 |
| `payload_too_large` | 压缩 payload |
| `timeout` | 重建客户端 + 重试 |
| `model_not_found` | fallback 到其他模型 |
| `server_error` / `overloaded` | 重试 / 退避 |
| `thinking_signature` | Anthropic thinking block 签名无效 |
| `long_context_tier` | 降级到 200K 标准层级 |

分类结果是结构化的 `ClassifiedError`，包含恢复提示：

```python
@dataclass
class ClassifiedError:
    reason: FailoverReason
    retryable: bool = True
    should_compress: bool = False
    should_rotate_credential: bool = False
    should_fallback: bool = False
```

重试循环直接读取这些字段决策，不再重复解析错误消息。

### 连接健康检查

```python
def _cleanup_dead_connections(self) -> bool:
    """检测并清理来自提供商故障的死 TCP 连接"""
    
    # 检查共享连接池中的死连接
    cleaned = 0
    for conn in self._connection_pool:
        if not conn.is_healthy():
            conn.close()
            cleaned += 1
    
    return cleaned > 0

# 在每轮对话开始前检查
if self.api_mode != "anthropic_messages":
    try:
        if self._cleanup_dead_connections():
            self._emit_status(
                "🔌 Detected stale connections from a previous provider "
                "issue — cleaned up automatically."
            )
    except Exception:
        pass
```

### 凭证自动刷新

```python
def _try_refresh_nous_client_credentials(self, *, force: bool = True) -> bool:
    """刷新 Nous Portal 凭证"""
    try:
        creds = resolve_nous_runtime_credentials(
            min_key_ttl_seconds=max(60, int(os.getenv("HERMES_NOUS_MIN_KEY_TTL_SECONDS", "1800"))),
            timeout_seconds=float(os.getenv("HERMES_NOUS_TIMEOUT_SECONDS", "15")),
            force_mint=force,
        )
    except Exception:
        return False
    
    api_key = creds.get("api_key")
    base_url = creds.get("base_url")
    if not isinstance(api_key, str) or not api_key.strip():
        return False
    
    self.api_key = api_key.strip()
    self.base_url = base_url.strip().rstrip("/")
    self._client_kwargs["api_key"] = self.api_key
    self._client_kwargs["base_url"] = self.base_url
    
    return self._replace_primary_openai_client(reason="nous_credential_refresh")

def _try_refresh_anthropic_client_credentials(self) -> bool:
    """刷新 Anthropic 凭证（OAuth token 轮换）"""
    if self.api_mode != "anthropic_messages" or self.provider != "anthropic":
        return False
    
    try:
        new_token = resolve_anthropic_token()
    except Exception:
        return False
    
    if not isinstance(new_token, str) or not new_token.strip():
        return False
    if new_token == self._anthropic_api_key:
        return False  # 无变化
    
    self._anthropic_client.close()
    self._anthropic_client = build_anthropic_client(new_token, self._anthropic_base_url)
    self._anthropic_api_key = new_token
    
    # 更新 OAuth 标志 — token 类型可能已更改
    self._is_anthropic_oauth = _is_oauth_token(new_token)
    return True
```

## 活动跟踪

```python
# 用于网关超时处理器和"仍在工作"通知
self._last_activity_ts: float = time.time()
self._last_activity_desc: str = "initializing"
self._current_tool: str | None = None
self._api_call_count: int = 0

def _touch_activity(self, description: str):
    """更新活动时间戳"""
    self._last_activity_ts = time.time()
    self._last_activity_desc = description

def get_status(self) -> dict:
    """获取当前状态（用于超时检测）"""
    elapsed = time.time() - self._last_activity_ts
    return {
        "last_activity_ts": self._last_activity_ts,
        "last_activity_desc": self._last_activity_desc,
        "seconds_since_activity": round(elapsed, 1),
        "current_tool": self._current_tool,
        "api_call_count": self._api_call_count,
        "budget_used": self.iteration_budget.used,
        "budget_max": self.iteration_budget.max_total,
    }
```

## Gateway 重启后自动续跑（2026-04-14）

Gateway 进程在 agent 调用工具**之后、生成最终回复之前**被重启(SIGTERM、崩溃、`drain_timeout`),session transcript 会停在一条 `role: "tool"` 上——之前的做法是用户必须手动 `/retry`(从头回放,丢失所有进度)或说 "continue"。现在当下一条用户消息到达时,Gateway 检测到历史尾部是 tool result,自动注入一条 system note:

```
[System note: Your previous turn was interrupted before you could process the
last tool result(s). The conversation history contains tool outputs you haven't
responded to yet. Please finish processing those results and summarize what was
accomplished, then address the user's new message below.]

<用户的新消息原文>
```

### 实现(`gateway/run.py:8679-8692`)

```python
# Auto-continue: if the loaded history ends with a tool result,
# the previous agent turn was interrupted mid-work
if agent_history and agent_history[-1].get("role") == "tool":
    message = SYSTEM_NOTE + "\n\n" + message
```

注入点在 `_run_agent()` 的 run_sync closure 里,**紧挨** `agent.run_conversation()` 之前。Agent 看到的是完整历史(含未处理的 tool results)加这条 system note,然后继续运行——所以它先总结之前的工作,再处理用户的新消息。

### 设计关键点

| 设计决策 | 说明 |
|---|---|
| **无 schema 变更** | 不新增 session flags 或持久化字段,纯粹检测尾部消息角色 |
| **适用所有重启场景** | Clean shutdown / crash / SIGTERM / drain timeout 都覆盖 |
| **保留用户消息** | 用户原始消息仍然在 system note 之后,不会丢 |
| **suspended session 不触发** | 如果 session 是 suspended 状态(非正常关闭),历史被丢弃,用户从空白开始,避免误 auto-continue 过时内容 |
| **关机通知改文案** | 关机时发出去的通知从 "Use /retry after restart to continue" 改成 "Send any message after restart to resume where it left off"——现在这才是准确的 |

### 对比旧行为

```text
旧流程(手动 /retry):
  用户: "deploy v2.3"
  agent: [calls terminal "kubectl apply"] → [tool result: "deployment started"]
  [Gateway 崩溃/重启]
  用户: "did it work?"
  → 用户必须手动输入 /retry 回放对话 → agent 从头跑 kubectl apply(可能重复部署!)

新流程(auto-continue):
  用户: "deploy v2.3"
  agent: [calls terminal "kubectl apply"] → [tool result: "deployment started"]
  [Gateway 崩溃/重启]
  用户: "did it work?"
  → Gateway 检测到尾部是 tool → 注入 system note → agent 看到 tool result + 用户新消息
  → agent: "部署已启动(kubectl apply 成功).关于你的问题..."
```

**关键安全性**:旧流程的 `/retry` 会重放副作用(再跑一遍 kubectl apply);新流程只是让 agent 解读**已发生的** tool result,不会重复执行。

## 优越性分析

### 与其他 Agent 框架对比

| 特性 | Hermes | Cursor | OpenCode |
|------|--------|--------|----------|
| 用户中断 | ✅ Ctrl+C/新消息 | ✅ | ✅ |
| 子代理中断传播 | ✅ | N/A | N/A |
| 凭证池轮换 | ✅ 多密钥自动轮换 | ❌ | ❌ |
| Fallback 模型链 | ✅ 自动切换 | ❌ | ❌ |
| 连接健康检查 | ✅ 自动清理 | ❌ | ❌ |
| 凭证自动刷新 | ✅ OAuth/token | ❌ | ❌ |
| 活动跟踪 | ✅ 超时检测 | ❌ | ❌ |

## 配置指南

### 环境变量

```bash
# Nous 凭证刷新
HERMES_NOUS_MIN_KEY_TTL_SECONDS=1800  # 最小密钥 TTL
HERMES_NOUS_TIMEOUT_SECONDS=15        # 刷新超时

# 流式读取超时
HERMES_STREAM_READ_TIMEOUT=60.0       # 流式读取超时（秒）
HERMES_API_TIMEOUT=1800.0             # API 总超时（秒）
```

## 相关页面

- [[credential-pool-and-isolation]] — 凭证池与轮换机制
- [[multi-agent-architecture]] — 子代理中断传播与预算隔离
- [[aiagent-class]] — AIAgent 中断标志与主循环

### 相关文件

- `agent/error_classifier.py` — 结构化 API 错误分类（13 种 FailoverReason）
- `run_agent.py` — 中断机制、重试循环
- `tools/credential_pool.py` — 凭证池
- `tools/interrupt.py` — 中断工具
