---
title: 代码执行沙箱（execute_code）
created: 2026-04-10
updated: 2026-05-17
type: concept
tags: [sandbox, code-execution, tools, architecture]
sources: [tools/code_execution_tool.py]
---

# 代码执行沙箱

## 概述

`execute_code` 工具让 LLM 编写一段 Python 脚本，在隔离子进程中执行。脚本可以通过 RPC 回调有限的 Hermes 工具集，将多步工具链压缩为一次推理，减少 token 消耗和延迟。

## 核心价值

```text
传统方式：10 轮工具调用 = 10 次 LLM 推理 + 10 次 context 膨胀
execute_code：1 次 LLM 写脚本 + 1 次执行，中间结果不进 context
```

## 沙箱限制

### 允许的工具（只有 7 个）

```python
SANDBOX_ALLOWED_TOOLS = [
    "web_search",      # 搜索
    "web_extract",     # 网页提取
    "read_file",       # 读文件
    "write_file",      # 写文件
    "search_files",    # 搜索文件
    "patch",           # 修改文件
    "terminal",        # 终端命令
]
```

### 资源限制

```python
DEFAULT_TIMEOUT = 300         # 5 分钟超时
DEFAULT_MAX_TOOL_CALLS = 50   # 最多 50 次工具调用
MAX_STDOUT_BYTES = 50_000     # 输出上限 50KB
MAX_STDERR_BYTES = 10_000     # 错误输出上限 10KB
```

可通过 config.yaml 的 `code_execution.*` 覆盖。

## 两种通信模式

| 模式 | 适用后端 | 通信方式 |
|------|---------|---------|
| **UDS（Unix Domain Socket）** | local | 父进程开 RPC listener，子进程通过 socket 调用工具 |
| **File-based RPC** | Docker / SSH / Modal / Daytona | 子进程写请求文件 → 父进程轮询 → 写响应文件 |

### 流程

```text
1. 父进程生成 hermes_tools.py stub（包含 RPC 函数）
2. 父进程开启 RPC 监听（UDS socket 或文件轮询线程）
3. 子进程执行 LLM 写的脚本
4. 脚本中调用 hermes_tools.web_search(...) 等
   → 通过 RPC 发回父进程 → 父进程调真正的工具 → 返回结果
5. 只有最终 stdout 返回给 LLM，中间结果不进 context
```

## 与 Terminal Backend 的关系

execute_code 的脚本**在当前 terminal backend 中执行**。如果 backend 是 Docker，脚本就跑在 Docker 里，通过 file-based RPC 回调本机的工具。

## Post-Write 校验链 —— Delta Lint → LSP 诊断 → File-Mutation Footer

Hermes 在 v0.13.0 → v0.14.0 三步加固了"agent 写完文件就立即知道有没有翻车"：

### 1. Delta Lint（v0.13.0+）

`tools/file_tools.py:1045,1061,1171`：`write_file` + `patch` 写完后自动跑 Python / JSON / YAML / TOML 语法检查，**只回报新增的错误**给 agent（旧错误不打扰）。

### 2. LSP 语义诊断（v0.14.0+）

`agent/lsp/`（11 modules，~4400 行：`cli.py / protocol.py / client.py:930 / manager.py:644 / eventlog.py / install.py / servers.py:1040 / range_shift.py / workspace.py / reporter.py`）：

写完后跑**真正的 language server**做**语义分析**——类型错误、未定义符号、缺 import、不可达代码——立即 surface 给 agent。LSP server 由 `agent/lsp/install.py` 按需安装，`agent/lsp/servers.py` 维护 Python/TypeScript/Go/Rust 等 server 清单。

比单纯 syntax check 升级一大截。

### 3. File-Mutation Verifier Footer（v0.14.0+）

`tools/file_state.py` + `agent/file_safety.py`：每轮如果写/改了文件，**给 agent 一段 footer**总结磁盘上具体变了什么（路径、行数、delta）。Agent 立刻发现"我以为写进去了但实际没保存"的失败，不再自信地报 success。

## 相关页面

- [[terminal-backends]] — 脚本在哪个后端执行
- [[large-tool-result-handling]] — 工具结果的溢出防护

## 关键源码

- `tools/code_execution_tool.py`（1347 行）— 沙箱完整实现
- `tools/file_tools.py:1045,1061,1171` — Delta lint（v0.13.0+）
- `agent/lsp/` — LSP 语义诊断（v0.14.0+，11 modules）
- `tools/file_state.py` + `agent/file_safety.py` — File-mutation footer（v0.14.0+）
