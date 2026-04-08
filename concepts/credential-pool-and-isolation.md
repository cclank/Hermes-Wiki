---
title: 凭证池与环境隔离系统
created: 2026-04-07
updated: 2026-04-07
type: concept
tags: [architecture, credentials, security, isolation]
sources: [raw/articles/code-analysis-2026-04-07.md]
---

# 凭证池与环境隔离系统

## 设计原理

企业场景需要多个 API 密钥实现：
1. **负载均衡** — 多个密钥分担请求
2. **故障转移** — 一个密钥限速时自动切换
3. **成本控制** — 不同密钥有不同预算

Hermes 实现了**凭证池系统**，支持多密钥自动轮换。

## 凭证池架构

```python
# tools/credential_pool.py

class CredentialEntry:
    """单个凭证条目"""
    id: str
    runtime_api_key: str
    runtime_base_url: str
    is_exhausted: bool = False  # 是否已耗尽
    exhaustion_count: int = 0   # 耗尽次数
    last_exhausted_at: float = 0

class CredentialPool:
    """凭证池"""
    
    def __init__(self, entries: list[CredentialEntry]):
        self.entries = entries
        self.current_index = 0
    
    def get_current(self) -> CredentialEntry:
        """获取当前凭证"""
        return self.entries[self.current_index]
    
    def mark_exhausted_and_rotate(self, status_code: int, ...) -> Optional[CredentialEntry]:
        """标记当前凭证为耗尽并轮换到下一个"""
        current = self.entries[self.current_index]
        current.is_exhausted = True
        current.exhaustion_count += 1
        current.last_exhausted_at = time.time()
        
        # 轮换到下一个可用凭证
        next_entry = self._find_next_available()
        if next_entry:
            self.current_index = self.entries.index(next_entry)
            return next_entry
        return None
    
    def try_refresh_current(self) -> Optional[CredentialEntry]:
        """尝试刷新当前凭证（OAuth token 轮换）"""
        current = self.get_current()
        try:
            new_token = resolve_token(current.id)
            if new_token and new_token != current.runtime_api_key:
                current.runtime_api_key = new_token
                current.is_exhausted = False
                return current
        except Exception:
            pass
        return None
    
    def has_available(self) -> bool:
        """是否还有可用凭证"""
        return any(not e.is_exhausted for e in self.entries)
```

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

## 相关文件

- `tools/credential_pool.py` — 凭证池
- `hermes_cli/auth.py` — 凭证解析
- `tools/environments/` — 终端后端环境
