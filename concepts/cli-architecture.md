---
title: CLI 架构与终端交互设计
created: 2026-04-07
updated: 2026-05-10
type: concept
tags: [architecture, cli, terminal, ux, slash-commands, oneshot]
sources: [cli.py, hermes_cli/main.py, hermes_cli/commands.py, hermes_cli/goals.py, hermes_cli/kanban.py, hermes_cli/curator.py, ui-tui/]
---

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

- `cli.py` — Classic CLI 主类
- `hermes_cli/main.py` — 入口点和子命令（含 `-z` 短路）
- `hermes_cli/commands.py` — 斜杠命令定义
- `hermes_cli/goals.py` — `/goal` Ralph 循环
- `hermes_cli/kanban.py` — `/kanban` argparse 树
- `hermes_cli/curator.py` — `/curator` 子命令
- `hermes_cli/dump.py` — `hermes dump` 环境摘要（纯文本，用于调试/提 issue）
- `agent/display.py` — 显示系统
- `hermes_cli/skin_engine.py` — 皮肤引擎
- `ui-tui/` — Ink TUI 前端
- `tui_gateway/` — TUI 后端 JSON-RPC
