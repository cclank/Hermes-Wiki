---
title: LSP 语义诊断集成
created: 2026-05-20
updated: 2026-05-31
type: concept
tags: [lsp, lint, diagnostics, file-operations, windows-cmd-shim]
source_files:
  - agent/lsp/
  - tools/file_operations.py
verified_against: hermes-agent HEAD (2026-05-31, eb3cf9750)
---

# LSP 语义诊断集成（v0.14.0）

v0.13.0 给 `write_file` / `patch` 加了 **基础 post-write lint**：纯语法检查 Python / JSON / YAML / TOML。v0.14.0 用 `agent/lsp/` 把它**升级为真正的语义级诊断** —— 跑真正的 language server 子进程（pyright / gopls / rust-analyzer / typescript-language-server 等），把 `textDocument/publishDiagnostics` 接进 lint delta。

```
┌─────────────────────────────────────────┐
│ FileOperations._check_lint_delta(path)  │
└──────┬──────────────────────────────────┘
       │
       ├─ git 工作区？                       否 → 回退原 in-process 语法检查
       │       是
       ▼
   agent.lsp.get_service()
       │
       ▼
   service.touch_file(path)              ── 通知 LSP daemon "我刚改了这个文件"
   service.diagnostics_for(path)         ── 拿最新诊断（pyright 已批 N ms）
       │
       ▼
   diff vs 改前 diagnostics
       │
       ▼
   "新增的"错误 → 注入 footer 给 agent 看
```

---

## 1. 关键设计：git-workspace 门控

源码：`agent/lsp/__init__.py:1`。

> LSP is **gated on git workspace detection** — if the agent's cwd is inside a git repository, LSP runs against that workspace; otherwise the file_operations layer falls back to its existing in-process syntax checks. This keeps users on user-home cwd's (e.g. Telegram gateway chats) from spawning daemons they don't need.

**为什么 git？**

- LSP daemon 重，启动慢、内存大、需要 indexer。在 `$HOME` 跑等于浪费资源。
- 编辑代码通常在 git repo 内。
- 用 git root 作为 workspace 边界天然合理（pyright / gopls 默认都以 git root 索引）。

如果 cwd 不在 git repo 内，`agent.lsp.get_service()` 返回的 service 的 `enabled_for(path)` 永远 False，FileOperations 退回老路径（纯 `ast.parse` / `json.loads` / `yaml.safe_load` / `tomli.loads`）。

---

## 2. 模块结构

```
agent/lsp/
├── __init__.py        # 公共 API：get_service(), enabled_for(), touch_file(), diagnostics_for()
├── cli.py             # hermes lsp 子命令（手动 toggle / list）
├── client.py          # 单个 LSP 客户端（per-language）
├── eventlog.py        # 调试用事件日志
├── install.py         # 自动装 LSP server（pip / npm / cargo）
├── manager.py         # 管理 client 池（lazy spawn / per-workspace）
├── protocol.py        # LSP JSON-RPC 协议帧
├── range_shift.py     # patch 改文件后，shift diagnostic 行号
├── reporter.py        # 渲染为 agent footer 文本
├── servers.py         # 每种语言的 server 配置（pyright / gopls / ...）
└── workspace.py       # git root 检测 + workspace tracking
```

---

## 3. 公共 API

```python
from agent.lsp import get_service

svc = get_service()
if svc and svc.enabled_for(path):
    await svc.touch_file(path)
    diags = svc.diagnostics_for(path)
```

调用点在 `tools/file_operations.py:FileOperations._check_lint_delta` —— 每次 `write_file` 或 `patch` 完成后调一次。

---

## 4. Delta 而不是全量

LSP 的诊断是**整个文件的**列表 —— 文件本来就有 10 个 type 错也照报。要避免噪声，必须算 **delta**：

```
before_write = diagnostics_for(path)        # 写之前
... write_file 或 patch 执行 ...
after_write  = diagnostics_for(path)        # 写之后
new_errors   = after_write - before_write   # 仅新增
```

加上 `range_shift.py` 处理"patch 移动了行号" 的情形 —— 把"改前的错误"按 patch 增删的行数 shift，再做集合差。

只有真正**因为这次修改新增**的错误才会进 agent footer。

---

## 5. Agent 看到的 Footer

每回合写完文件后，agent 收到的 tool message 末尾附加形如：

```
─── lint diagnostics (lsp/pyright) ───
hermes_state.py:142:12  error  "self.foo" is unknown attribute on type "AIAgent"
hermes_state.py:198:5   error  Type "int | None" is not assignable to parameter "size" of type "int"
2 new diagnostics introduced by this write.
```

agent 下一回合的 system note 里也有"上回合写了什么文件、新增几个 lint error"的 verifier footer（v0.14.0 独立 feature，参见 changelog 第 11 节）。两者组合让 agent**第一时间发现自己写错了**。

---

## 6. Server 配置

源码：`agent/lsp/servers.py`。每种语言：

```python
ServerSpec(
    name="pyright",
    cmd=["pyright-langserver", "--stdio"],
    languages={"python"},
    install_hint="pip install pyright",
    autoinstall=False,    # 不自动装；提示用户
    settings={...},       # initializationOptions
)
```

默认覆盖：

| 语言 | Server |
|------|--------|
| Python | pyright |
| TypeScript / JavaScript | typescript-language-server |
| Go | gopls |
| Rust | rust-analyzer |
| Ruby | solargraph |
| ...（陆续扩展） | |

**没装就跳过** —— Hermes 不强行安装。`hermes lsp install <server>` 走 `install.py` 的辅助路径。

---

## 7. 不变量

- LSP daemon 永远在 **git workspace** 内启动，非 git 路径回退老 lint。
- 诊断永远以 **delta**（仅本次写入新增的错误）呈现给 agent。
- LSP server 失败 / 缺失 → 退回 in-process 语法检查，**不阻塞** write_file / patch。
- daemon **per-workspace**：同一个仓库内的多 file 写共享一个进程；切到另一个 repo 启第二个。
- `touch_file` → `diagnostics_for` 之间有合理 await（让 LSP indexer 给出最新 diagnostics）。

---

## 8. 与现有 lint 的关系

| 写入路径 | v0.13.0 之前 | v0.13.0 | v0.14.0 |
|---------|-------------|---------|---------|
| `write_file` | 无 lint | basic syntax（Python/JSON/YAML/TOML 纯语法） | 上述 + LSP 语义 |
| `patch` | 无 lint | basic syntax delta | 上述 + LSP 语义 delta + range_shift |
| `terminal` 写文件 | 无 lint | 无 | 无（terminal 写文件不走 FileOperations）|

---

## 9. 验证

```
agent/lsp/__init__.py:1-30             docstring（git-gate 设计理由）
agent/lsp/manager.py                   client pool / per-workspace
agent/lsp/workspace.py                 git root 检测
agent/lsp/range_shift.py               patch 后行号 shift
agent/lsp/servers.py                   每语言 ServerSpec
tools/file_operations.py               _check_lint_delta 调用点
website/docs/user-guide/features/lsp.md  用户文档
```

## 10. 2026-05-31 增量 — Windows .cmd shim 双修复

### `fix(lsp): handle Windows .cmd shims in LSP process spawn`（`296fcdfa5`）

- `asyncio.create_subprocess_exec` 在 Windows 上**无法直接执行** `.cmd / .bat` —— `CreateProcess` 期待 PE 可执行文件，遇到批处理 shim 报 `WinError 193 (%1 is not a valid Win32 application)`。
- 受影响的 LSP server：npm-installed 系列，如 `intelephense` / `typescript-language-server`，在 Windows 上 npm 自动生成 `.cmd` shim 入口。
- **修**：spawn 前探测 path 后缀；`.cmd / .bat` 走 `subprocess.create_subprocess_shell(...)`（经 `cmd.exe`）而非 exec。

### `fix(lsp): detect Windows wrapper binaries in installer probes`（`460771bf0`）

- `agent/lsp/install.py` 的 binary-existence probe 原仅查无后缀文件；Windows 下二进制实际叫 `<name>.exe` 或 `<name>.cmd`。
- **修**：probe sweep `[name, name+".exe", name+".cmd", name+".bat", name+".ps1"]`。
- 配套 `agent/lsp/cli.py` 把 `which`-equivalent 输出 path 也带上 wrapper 后缀，让用户看到完整路径。

测试 `tests/agent/lsp/test_install_and_lint_fixes.py:+41` 行覆盖。
