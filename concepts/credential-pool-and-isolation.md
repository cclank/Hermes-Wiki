---
title: 凭证池与环境隔离系统
created: 2026-04-07
updated: 2026-04-11
type: concept
tags: [architecture, credentials, security, isolation]
sources: [agent/credential_pool.py, hermes_cli/auth.py]
---

# 凭证池与环境隔离系统

## 设计原理

企业场景需要多个 API 密钥实现：
1. **负载均衡** — 多个密钥分担请求
2. **故障转移** — 一个密钥限速时自动切换
3. **成本控制** — 不同密钥有不同预算

Hermes 实现了**凭证池系统**，支持多密钥自动轮换。

## 凭证池架构

核心数据结构位于 `agent/credential_pool.py`（不是 `tools/`）：

- **`PooledCredential`** — 单个凭证条目（dataclass），包含 `runtime_api_key`、`runtime_base_url`、耗尽状态和计数
- **`CredentialPool`** — 凭证池，管理多个凭证的选择、轮换和恢复

### 4 种选池策略

```yaml
# config.yaml
credential_pool:
  strategy: round_robin  # 默认
```

| 策略 | 行为 |
|------|------|
| `fill_first` | 一直用第一个，直到耗尽才切下一个 |
| `round_robin` | 依次轮换，均匀分担 |
| `random` | 随机选一个可用的 |
| `least_used` | 选使用次数最少的 |

### 关键方法

- `select()` — 按策略选择下一个可用凭证
- `mark_exhausted(entry)` — 标记耗尽 + 自动轮换（耗尽 TTL 为 1 小时，过期自动恢复）
- `try_refresh(entry)` — OAuth token 刷新
- `has_available()` — 是否还有可用凭证

## 凭证轮换逻辑

```python
# 402 (账单耗尽) — 立即轮换
if status_code == 402:
    next_entry = pool.mark_exhausted_and_rotate(status_code=402, ...)
    if next_entry:
        self._swap_credential(next_entry)
        return True, False

# 429 (速率限制) — 第一次重试，第二次轮换
if status_code == 429:
    if not has_retried_429:
        return False, True  # 重试相同凭证
    next_entry = pool.mark_exhausted_and_rotate(status_code=429, ...)
    if next_entry:
        self._swap_credential(next_entry)
        return True, False

# 401 (未授权) — 先刷新，失败则轮换
if status_code == 401:
    refreshed = pool.try_refresh_current()
    if refreshed:
        self._swap_credential(refreshed)
        return True, has_retried_429
    # 刷新失败 — 轮换
    next_entry = pool.mark_exhausted_and_rotate(status_code=401, ...)
    if next_entry:
        self._swap_credential(next_entry)
        return True, False
```

## 凭证交换

```python
def _swap_credential(self, entry) -> None:
    """交换凭证"""
    runtime_key = getattr(entry, "runtime_api_key", None)
    runtime_base = getattr(entry, "runtime_base_url", None) or self.base_url
    
    if self.api_mode == "anthropic_messages":
        self._anthropic_client.close()
        self._anthropic_api_key = runtime_key
        self._anthropic_base_url = runtime_base
        self._anthropic_client = build_anthropic_client(runtime_key, runtime_base)
        self._is_anthropic_oauth = _is_oauth_token(runtime_key)
        self.api_key = runtime_key
        self.base_url = runtime_base
        return
    
    # OpenAI 兼容模式
    self.api_key = runtime_key
    self.base_url = runtime_base.rstrip("/")
    self._client_kwargs["api_key"] = self.api_key
    self._client_kwargs["base_url"] = self.base_url
    self._replace_primary_openai_client(reason="credential_rotation")
```

## 环境隔离

```python
# HERMES_HOME 隔离
def get_hermes_home() -> Path:
    """获取 Hermes 主目录（支持 Profile 覆盖）"""
    env_override = os.getenv("HERMES_HOME")
    if env_override:
        return Path(env_override)
    return Path.home() / ".hermes"

# Profile 支持
# ~/.hermes/ 是默认 Profile
# HERMES_HOME=/path/to/custom 使用自定义 Profile
```

### Profile 隔离的内容

| 内容 | 隔离 | 共享 |
|------|------|------|
| 配置 (config.yaml) | ✅ | ❌ |
| 密钥 (.env) | ✅ | ❌ |
| 技能 (~/.hermes/skills/) | ✅ | ❌ |
| 记忆 (~/.hermes/memories/) | ✅ | ❌ |
| 会话数据库 | ✅ | ❌ |
| 代码仓库 | ❌ | ✅ |

## 终端后端环境隔离

```python
# tools/environments/
# 每个终端后端提供隔离的执行环境

local.py      # 本地执行（共享文件系统）
docker.py     # Docker 容器隔离
ssh.py        # SSH 远程执行
modal.py      # Modal 无服务器隔离
daytona.py    # Daytona 沙箱隔离
singularity.py # Singularity 容器隔离
```

## 优越性分析

### 与其他 Agent 框架对比

| 特性 | Hermes | Cursor | OpenCode |
|------|--------|--------|----------|
| 凭证池 | ✅ 多密钥轮换 | ❌ | ❌ |
| 自动故障转移 | ✅ 402/429/401 | ❌ | ❌ |
| OAuth 刷新 | ✅ 自动 | ❌ | ❌ |
| Profile 隔离 | ✅ HERMES_HOME | ❌ | ❌ |
| 终端后端隔离 | ✅ 6 种后端 | ❌ | ✅ Docker |

## 相关页面

- [[interrupt-and-fault-tolerance]] — 中断传播与容错机制（凭证轮换逻辑）
- [[auxiliary-client-architecture]] — 辅助客户端使用凭证池获取认证
- [[configuration-and-profiles]] — Profile 隔离与凭证管理

## 相关文件

- `agent/credential_pool.py` — 凭证池（4 种策略 + 耗尽恢复）
- `hermes_cli/auth.py` — 凭证解析
- `tools/environments/` — 终端后端环境
