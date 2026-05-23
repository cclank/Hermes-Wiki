---
title: CLI 架构与终端交互设计
created: 2026-04-07
updated: 2026-05-18
type: concept
tags: [architecture, cli, terminal, ux]
sources: [hermes_cli/commands.py, hermes_cli/goals.py, hermes_cli/kanban.py, hermes_cli/curator.py, cli.py]
---

> **v2026.4.30 ~ v2026.5.7 增量**：
>
> - **`hermes -z <prompt>` 一次性模式**（v2026.4.30+）—— 非交互式 one-shot，支持 `--model` / `--provider` / `HERMES_INFERENCE_MODEL`。
> - **`hermes update --check`**（v2026.4.30+）preflight，opt-in pre-update HERMES_HOME 备份。
> - **`hermes update --yes/-y`** 跳过交互（#18261）。
> - **`/goal`**（v2026.5.7+）—— Ralph loop，跨轮目标锁定。源码 `hermes_cli/goals.py`（535 行）。`/goal <text>` 设定，`/goal resume` 继续，`/goal clear` 清除。
> - **`/new <session_name>`**（v2026.5.7+）接受可选 session 名（#19637）。
> - **`/curator archive | prune | list-archived`**（v2026.5.7+）curator 子命令。`hermes_cli/curator.py:258` 起。
> - **i18n —— 7 个 locale**：源码 `locales/` 下 `en/zh/ja/de/es/fr/uk/tr.yaml`。`display.language` 配置启用。
> - **100 条新 CLI 启动 tip**（#20168）覆盖 cron / kanban / curator / plugins 等。

# CLI 架构与终端交互设计

## 设计原理

Hermes CLI 提供完整的终端用户体验：自动补全、多行编辑、流式输出、工具调用可视化。基于 `prompt_toolkit` 和 `rich` 构建。

## 核心组件

```python
# cli.py
class HermesCLI:
    """Hermes CLI 主类"""
    
    def __init__(self):
        self.agent = None
        self.config = load_cli_config()
        self.session_db = SessionDB(...)
        self.todo_store = TodoStore()
    
    def run(self):
        """主循环"""
        while True:
            user_input = self._get_input()  # prompt_toolkit 输入
            if user_input.startswith("/"):
                self._handle_command(user_input)
            else:
                self._handle_message(user_input)
```

## 斜杠命令清单（v0.13.0）

`hermes_cli/commands.py` 列举所有斜杠命令；CLI / 网关共享同一表面。重点新增：

| 命令 | 类别 | 说明 |
|------|------|------|
| `/goal <text\|pause\|resume\|clear\|status>` | Session | 持久目标 + Ralph 循环；详见 [[goal-loop-architecture]] |
| `/subgoal <text\|remove N\|clear>` | Session | 给活动 `/goal` 追加验收标准 |
| `/queue <prompt>` / `/q` | Session | 把 prompt 排到当前 turn 之后跑，不抢占 |
| `/steer <prompt>` | Session | 注入 guidance 到正在跑的 turn，下一个 tool call 之后呈现 |
| `/kanban <subcommand>` | Tools & Skills | 看板操作（15+ verb，详见 [[kanban-architecture]]） |
| `/curator archive\|prune\|list-archived` | Tools & Skills | v0.13.0 子命令扩张 |
| `/reload-skills` | Tools & Skills | rescan `~/.hermes/skills/`，不失效 prompt cache（v2026.4.23+） |
| `/reload-mcp` | Tools & Skills | rescan MCP server；会失效 cache，所以加确认 |
| `/reload` | Tools & Skills | 把 `.env` 热加载进当前 session |
| `/mouse` | Configuration | 关掉 ConPTY 的 phantom mouse 注入（@kevin-ho） |
| `/indicator <kaomoji\|emoji\|unicode\|ascii>` | Configuration | busy-indicator 风格 |

`/queue` 与 `/steer` 在 ACP transport (`acp_adapter/server.py:1618` `_cmd_steer` / `1637` `_cmd_queue`) 同名生效，让 Zed / VS Code / JetBrains 接入后直接可用。

## `hermes -z` 一次性模式（v0.12.0）

非交互式 CLI：

```bash
hermes -z "find largest file in /var/log"
hermes -z --model claude-sonnet-4.6 "summarise PR #123"
HERMES_INFERENCE_MODEL=gpt-5.5 hermes -z "..."
```

`#15702-#15704`、`#15841`、`#16539`、`#16566`。`hermes update --check` 是 preflight；opt-in pre-update HERMES_HOME 备份。

## 输入系统

```python
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory

session = PromptSession(
    history=FileHistory("~/.hermes/input_history"),
    auto_suggest=AutoSuggestFromHistory(),
    completer=SlashCommandCompleter(),  # 定义在 hermes_cli/commands.py
)

user_input = session.prompt(get_active_prompt_symbol())  # 提示符号通过 skin engine 配置
```

### 斜杠命令补全

```python
class SlashCommandCompleter(Completer):
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if text.startswith("/"):
            for cmd_name, cmd_def in COMMANDS.items():
                if cmd_name.startswith(text[1:]):
                    yield Completion(cmd_name, start_position=-len(text[1:]))
```

### 命令注册表（`hermes_cli/commands.py:64+`）

`COMMAND_REGISTRY: list[CommandDef]` 是 **CLI / Gateway / TUI 共享**的单一 source of truth。`CommandDef` 字段：

```python
@dataclass
class CommandDef:
    name: str                              # 命令名（不带 /）
    description: str                       # 人类可读描述
    category: str                          # "Session" / "Configuration" / "Info" 等
    aliases: tuple[str, ...] = ()          # 别名（"reset" → "new"）
    args_hint: str = ""                    # 参数占位符 "<prompt>" / "[name]"
    subcommands: tuple[str, ...] = ()      # 可 tab-补全的子命令
    cli_only: bool = False                 # 仅 CLI
    gateway_only: bool = False             # 仅 gateway/messaging
    gateway_config_gate: str | None = None # config dotpath，truthy 时 cli_only 在 gateway 也开
```

### 关键斜杠命令（v0.13.0+ 新增标 ★）

| 命令 | 功能 | 范围 |
|------|------|------|
| `/new`（别名 `/reset`）`[name]` | 新会话 | 双 |
| `/topic [off\|help\|session-id]` ★ | Telegram DM topic 模式 | gateway only |
| `/clear` / `/redraw` ★ | 清屏 / 强制 UI 重绘（恢复 terminal drift） | cli only |
| `/history` / `/save` | 查看 / 保存历史 | cli only |
| `/retry` / `/undo` | 重试 / 撤销 | 双 |
| `/title [name]` ★ | 设置会话标题 | 双 |
| `/branch`（别名 `/fork`）`[name]` ★ | 分叉会话 | 双 |
| `/compress [focus]` | 手动压缩 | 双 |
| `/rollback [number]` | 列 / 还原 checkpoint | 双 |
| `/snapshot [create\|restore <id>\|prune]` ★（别名 `/snap`） | Hermes config/state 快照 | cli only |
| `/stop` ★ | 杀所有后台进程 | 双 |
| `/approve [session\|always]` / `/deny` ★ | 处理 pending dangerous command | gateway only |
| `/background <prompt>` ★（别名 `/bg`、`/btw`） | 后台 prompt | 双 |
| `/agents`（别名 `/tasks`）★ | 显示活动 agent + 运行任务 | 双 |
| `/queue <prompt>` ★（别名 `/q`） | 队列下一轮 prompt（不打断） | 双 |
| `/steer <prompt>` ★ | 工具调用之间注入消息（不打断） | 双 |
| `/goal [text\|pause\|resume\|clear\|status]` ★ | 跨轮持续目标（Ralph 循环） | 双 |
| `/status` | 会话信息 | 双 |
| `/profile` ★ | 当前 profile 名 + home 目录 | 双 |
| `/sethome` ★（别名 `/set-home`） | 当前 chat 设为 home channel | gateway only |
| `/resume [name]` | 恢复命名 session | 双 |
| `/sessions` ★ | 浏览 + resume 历史会话 | 双 |
| `/config` | 显示当前配置 | cli only |
| `/model`（别名 `/provider`）`[model] [--provider name] [--global]` | 切换模型 | 双 |
| `/personality [name]` | 设置预定义 personality | 双 |
| `/statusbar`（别名 `/sb`） | 切换 context/model 状态栏 | cli only |
| `/verbose` ★ | 循环 tool progress：off → new → all → verbose | cli only（`gateway_config_gate: display.tool_progress_command`） |

### `/goal` —— Ralph 循环（v0.13.0+）

`hermes_cli/goals.py` 实现 `GoalManager`，把 Ralph 循环作为一等 primitive：

- 每轮结束后辅助模型 judge —— "目标是否被最后一条 assistant 响应满足？"
- 不满足 → 注入 continuation prompt 到同一 session，继续干
- 终止条件：goal 完成 / turn budget 耗尽 / 用户 `pause` / `clear` / 用户发新消息（preempt）
- **零 system prompt 突变、零 toolset swap** —— prompt cache 完整保留
- Judge 失败 fail-OPEN（continue），turn budget 是后盾
- 状态写 SessionDB 的 `state_meta` 表，键 `goal:<session_id>`，`/resume` 自动捡起来

CLI 和 gateway 共享同一个 `GoalManager`。

### 销毁性命令二次确认（v0.13.0+，PR #4069 / #22687）

`/clear`、`/new` 等会丢失上下文的命令现在弹**确认对话框**，避免误操作丢工作。

## 显示系统

### KawaiiSpinner

```python
# agent/display.py
class KawaiiSpinner:
    """动画加载指示器"""
    
    SPINNERS: dict          # 9 种命名动画集 ('dots', 'bounce', 'grow', ...)
    KAWAII_WAITING: list     # 10 个多字符颜文字
    KAWAII_THINKING: list    # 15 个多字符颜文字
    THINKING_VERBS: list    # 15 个动词 ("pondering", "contemplating", "musing", "cogitating", "ruminating", ...)
    
    def show(self, message: str):
        """显示加载动画"""
        # 使用 Rich 面板和动画
```

### 工具调用预览

```python
def build_tool_preview(tool_name: str, args: dict) -> str:
    """构建工具调用预览"""
    preview = f"🔧 {tool_name}("
    for key, value in list(args.items())[:3]:
        preview += f"\n  {key}={preview_value(value)},"
    preview += "\n)"
    return preview

def get_cute_tool_message(tool_name: str) -> str:
    """获取可爱的工具执行消息"""
    emoji = _get_tool_emoji(tool_name)
    return f"{emoji} Calling {tool_name}..."
```

## Skin 引擎

```python
# hermes_cli/skin_engine.py
@dataclass
class SkinConfig:
    """皮肤配置数据类"""
    ...

# 模块级函数（非类）
def init_skin_from_config(): ...
def get_active_skin() -> SkinConfig: ...
def list_skins() -> list: ...
def set_active_skin(name: str): ...

# 配置示例
# ~/.hermes/config.yaml
display:
  skin: "default"  # 或自定义皮肤名称
```

## hermes send 子命令

`hermes send` 把脚本输出 / stdin 管道转发到任意已配置的消息平台。命令在 `hermes_cli/main.py` 注册（`register_send_subparser`），实现于 `hermes_cli/send_cmd.py`，是 `tools.send_message_tool.send_message_tool` 的一层薄封装。

```bash
# 把脚本输出管道发送给某个目标
./build.sh 2>&1 | hermes send --to telegram

# 发送文件、带主题
hermes send --to email --file report.pdf --subject "每日报告"

# 列出可用目标
hermes send --list
```

支持 `--to`、`--file`、`--subject`、`--list`、管道 stdin、线程化目标、以及 `#channel` 频道名解析。

## 优越性分析

### 与其他 Agent 框架对比

| 特性 | Hermes | Claude Code | Codex CLI |
|------|--------|-------------|-----------|
| 斜杠命令补全 | ✅ 自动 | ✅ | ❌ |
| 多行编辑 | ✅ | ✅ | ✅ |
| 输入历史 | ✅ 文件持久化 | ✅ | ✅ |
| 动画加载 | ✅ KawaiiSpinner | ✅ 简单 | ✅ 简单 |
| 主题系统 | ✅ Skin Engine | ❌ | ❌ |
| 工具调用预览 | ✅ 格式化 | ✅ | ❌ |

## v0.12.0 / v0.13.0 新增斜杠命令

| 命令 | 来源 | 行为 |
|---|---|---|
| **`/goal <text>`** | `hermes_cli/goals.py`（v0.13.0） | 锁定目标，每轮 judge done/continue；详见 [[goal-and-ralph-loop]] |
| **`/goal status/pause/resume/clear`** | 同上 | 状态管理 |
| **`/steer <prompt>`** | v0.11.0 | 中段提示，agent 下一个 tool call 后看到，不破 prompt cache |
| **`/queue <prompt>`** | v0.13.0 ACP | 排队下一指令 |
| **`/kanban …`** | `hermes_cli/kanban.py:2181`（v0.13.0） | 共享 15-verb argparse 树；详见 [[kanban-multi-agent]] |
| **`/curator …`** | `hermes_cli/curator.py`（v0.11~0.13） | status/run/pause/resume/pin/unpin/restore/archive/prune/list-archived |
| **`/reload-skills`** | v0.11.0 | rescan `~/.hermes/skills/`，不破 prompt cache |
| **`/reload`** | v0.11.0 TUI 移植 | `.env` 热重载 |
| **`/reload-mcp`** | v0.11.0 | 带"未来不再询问"确认对话框（清缓存代价大） |
| **`/clear`** | v0.11.0 | 带 confirm |
| **`/model`** (TUI) | v0.13.0 | 和 `hermes model` 等价，含 inline auth |
| **`/mouse`** | v0.12.0 TUI | toggle ConPTY 假鼠标注入 |

## `hermes -z` 一次性模式（v0.12.0）

```
hermes -z "fix the failing test in tests/test_x.py"
hermes -z "summarize this PR" --model claude-opus-4.5
HERMES_INFERENCE_MODEL=gpt-5.5 hermes -z "..."
```

非交互式 prompt，跑完就退——给脚本 / CI / cron 之外的一次性自动化任务用。配合 `--model` / `--provider` / 环境变量。

## `hermes update --check` 预检（v0.12.0）

跑升级前先看是否真的有新版本可用，opt-in pre-update HERMES_HOME 备份避免升级出错丢配置。

## TUI vs Classic CLI

`ui-tui/` 是 React/Ink 重写的 TUI（v0.11.0 起），与 `cli.py` 经典 CLI 共存：

- TUI 是默认（`hermes` / `hermes --tui`），React/Ink 前端 + Python JSON-RPC 后端（`tui_gateway`）
- Classic CLI（`hermes --classic` 或 fall back）

经典 CLI 的功能逐步往 TUI 迁，比如 LaTeX 渲染、`d` 删 session、`/reload`、`/mouse` 都在 v0.12 ~ v0.13 落地。

## 相关页面

- [[configuration-and-profiles]] — 配置管理与 Profile 系统
- [[hook-system-architecture]] — Hook 与插件扩展系统
- [[session-search-and-sessiondb]] — 会话搜索与 SessionDB
- [[voice-mode-architecture]] — 语音模式（Push-to-talk → STT → TTS）
- [[skin-engine]] — 皮肤/主题自定义
- [[context-references]] — @file/@diff/@url 引用系统
- [[worktree-isolation]] — Git Worktree 并行隔离
- [[code-execution-sandbox]] — 代码执行沙箱
- [[goal-and-ralph-loop]] — `/goal` 命令实现
- [[kanban-multi-agent]] — `/kanban` 子命令
- [[skills-system-architecture]] — `/curator` 子命令

## 相关文件

- `cli.py` — CLI 主类（`_handle_sessions_command()` 处理经典 CLI 的 `/sessions` 斜杠命令）
- `hermes_cli/main.py` — 入口点和子命令（注册 `hermes send`）
- `hermes_cli/send_cmd.py` — `hermes send` 实现（`send_message_tool` 薄封装）
- `hermes_cli/commands.py` — 斜杠命令定义
- `hermes_cli/goals.py` — `/goal` Ralph 循环
- `hermes_cli/kanban.py` — `/kanban` argparse 树
- `hermes_cli/curator.py` — `/curator` 子命令
- `hermes_cli/dump.py` — `hermes dump` 环境摘要（纯文本，用于调试/提 issue）
- `agent/display.py` — 显示系统
- `hermes_cli/skin_engine.py` — 皮肤引擎
- `ui-tui/` — Ink TUI 前端
- `tui_gateway/` — TUI 后端 JSON-RPC
