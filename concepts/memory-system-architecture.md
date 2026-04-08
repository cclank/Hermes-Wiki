---
title: Memory System Architecture
created: 2026-04-07
updated: 2026-04-07
type: concept
tags: [memory, architecture, module, session-store]
sources: [raw/articles/code-analysis-2026-04-07.md]
---

# Memory System Architecture

## Overview

Memory 系统提供**跨会话的持久化记忆**，使用两个独立的 Markdown 文件存储不同类型的信息：

- **`MEMORY.md`** — Agent 的个人笔记（环境事实、项目约定、工具特性、经验教训）
- **`USER.md`** — 用户画像（偏好、沟通风格、期望、工作习惯）

## 核心设计原则

### 1. 冻结快照模式 (Frozen Snapshot Pattern)

这是最关键的设计决策：

```
会话启动时:
  load_from_disk() → 读取文件 → 捕获快照到 _system_prompt_snapshot
  ↓
  快照注入系统提示 → 整个会话期间保持不变
  ↓
  会话中的写入 → 更新磁盘文件 + 内存状态，但不修改系统提示
  ↓
  下次会话启动 → 重新加载，新内容生效
```

**为什么这样设计？**
- 保持系统提示稳定，充分利用 Anthropic 的 prefix cache
- 避免中途修改系统提示导致缓存失效
- 写入仍然持久化（磁盘 + 内存），只是当前会话看不到自己的写入

### 2. 字符限制（不是 token 限制）

- `MEMORY.md`: 2200 字符
- `USER.md`: 1375 字符

使用字符数而不是 token 数，因为字符计数与模型无关。

### 3. 条目分隔符

使用 `§` (section sign) 作为条目分隔符，支持多行条目。

## MemoryStore 类

```python
class MemoryStore:
    # 并行状态
    memory_entries: List[str]        # 内存中的实时状态
    user_entries: List[str]
    _system_prompt_snapshot: Dict    # 冻结快照（用于系统提示）
    
    # 核心方法
    load_from_disk()                 # 加载并捕获快照
    add(target, content)             # 添加条目
    replace(target, old_text, new)   # 替换条目
    remove(target, old_text)         # 删除条目
    format_for_system_prompt(target) # 返回冻结快照
```

## 原子写入机制

```python
def _write_file(path, entries):
    # 1. 写入临时文件（同目录，同文件系统）
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    # 2. 写入内容 + fsync
    os.fsync(f.fileno())
    # 3. 原子重命名
    os.replace(tmp_path, str(path))
```

**为什么使用原子写入？**
- 避免并发读写看到空文件（旧实现用 `open("w")` 会先截断文件）
- 读者总是看到完整的旧文件或完整的新文件

## 文件锁

```python
@contextmanager
def _file_lock(path):
    lock_path = path.with_suffix(path.suffix + ".lock")
    fd = open(lock_path, "w")
    fcntl.flock(fd, fcntl.LOCK_EX)  # 排他锁
    yield
    fcntl.flock(fd, fcntl.LOCK_UN)
    fd.close()
```

写入时获取锁，读取时不需要锁（因为原子写入保证数据一致性）。

## 安全扫描

所有写入内容都会经过安全扫描，检测：

```python
_MEMORY_THREAT_PATTERNS = [
    # 提示注入
    (r'ignore\s+(previous|all|above|prior)\s+instructions', "prompt_injection"),
    (r'you\s+are\s+now\s+', "role_hijack"),
    (r'do\s+not\s+tell\s+the\s+user', "deception_hide"),
    # 密钥泄露
    (r'curl\s+[^\n]*\$?\w*(KEY|TOKEN|SECRET|PASSWORD)', "exfil_curl"),
    (r'cat\s+[^\n]*(\.env|credentials|\.netrc)', "read_secrets"),
    # 持久化后门
    (r'authorized_keys', "ssh_backdoor"),
]
```

还会检测不可见 Unicode 字符（U+200B, U+200C, U+200D 等）。

## 内存管理策略

### 添加条目
1. 检查内容不为空
2. 安全扫描
3. 获取文件锁 → 重新读取磁盘（获取最新状态）
4. 检查重复
5. 检查字符限制
6. 追加 → 保存 → 释放锁

### 替换条目
1. 使用短唯一子串匹配（不是完整文本或 ID）
2. 如果多个条目匹配，且内容不同 → 要求更具体的匹配
3. 如果多个条目匹配，但内容相同（重复）→ 操作第一个

### 去重
```python
# 保持顺序的去重
entries = list(dict.fromkeys(entries))
```

## 系统提示格式化

```
══════════════════════════════════════════
MEMORY (your personal notes) [65% — 1,430/2,200 chars]
══════════════════════════════════════════
条目 1
§
条目 2
§
条目 3
```

## Profile 支持

记忆文件位于 `~/.hermes/memories/` 目录下，受 `HERMES_HOME` 环境变量影响，支持不同 profile 使用不同的记忆。

## 相关文件

- `tools/memory_tool.py` — Memory 工具实现（560 行）
- `agent/memory_manager.py` — Memory 管理器
- `agent/memory_provider.py` — Memory 提供者接口
- `agent/builtin_memory_provider.py` — 内置 Memory 提供者
