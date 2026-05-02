---
title: CLI 架构与终端交互设计
created: 2026-04-07
updated: 2026-05-02
type: concept
tags: [architecture, cli, terminal, ux, tui, ink, oneshot]
sources: [cli.py, hermes_cli/main.py, hermes_cli/commands.py, hermes_cli/oneshot.py, hermes_cli/fallback_cmd.py, hermes_cli/curator.py, hermes_cli/skin_engine.py, ui-tui/, tui_gateway/]
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

## CLI 子命令（v2026.4.30 新增）

| 命令 | 说明 | 源码 |
|------|------|------|
| **`hermes -z <prompt>`** | 一发即射模式（non-interactive）+ `--model` / `--provider` / `HERMES_INFERENCE_MODEL` 环境变量 + `--toolsets` 选择 | `hermes_cli/oneshot.py` |
| **`hermes update --check`** | 升级前 preflight；opt-in `auto_backup HERMES_HOME` | `hermes_cli/main.py` |
| **`hermes fallback {list,add,remove,clear}`** | 显式 fallback provider chain 管理 | `hermes_cli/fallback_cmd.py`（430+ 行） |
| **`hermes curator {status,run,pause,resume,pin,unpin,restore,backup,rollback}`** | Curator 全套操作（v2026.4.30 扩展） | `hermes_cli/curator.py`（430 行） |
| **`hermes skills install <url>`** | 直接 URL 安装 skill | skill manager |
| **`hermes skills list`** | 显示 enabled / disabled 状态 |  |
| **`hermes hooks {list,test,revoke,doctor}`** | Shell hook 管理 | `hermes_cli/hooks.py` |

## 斜杠命令演化

### 新增（v2026.4.23 ~ v2026.4.30）

| 命令 | 说明 |
|------|------|
| **`/steer <prompt>`** | 跑动中插话，下一次工具调用后看到，**不打断 turn、不破缓存** |
| **`/busy`** | busy 输入模式（用户继续打字时 agent 显示 busy 提示） |
| **`/btw`** | `/background` 别名 |
| **`/reload-skills`** | rescan skills 目录，**不重置 prompt cache** |
| **`/reload-mcp`** | 重新加载 MCP server，弹确认对话框（清缓存代价高，用户 opt-out 永久跳过） |
| **`/queue` / `/bg`** | 排队消息（agent 处理完当前 turn 后看到） |
| **`/curator <subcommand>`** | `hermes curator` 子命令的镜像 |
| **`/mouse`** | TUI ConPTY 鼠标行为切换（修复 WSL2 幻影鼠标注入） |
| **`/reload`** | TUI .env 热重载（从 classic CLI 移植） |

### 删除（v2026.4.30）

- **`/provider`** —— 已被 `/model` 的 picker 完全替代（drop #15047）
- **`/plan` handler** —— 与 `/steer` 重叠，drop #15047
- **`flush_memories` 工具** —— refactor #15696 完全移除（本是迁移工具）
- **BOOT.md 内置 hook** —— #17093；hooks 教程教用户用 shell hook 自实现

## TUI（Ink-based React 重写，`ui-tui/` + `tui_gateway/`）

`hermes --tui` 或 `HERMES_TUI=1` 启动。**v0.11.0 全栈重写**，~310 commits，v0.12.0 进一步追平 + 反超 classic CLI。

### v2026.4.30 新增能力

- **LaTeX 渲染**（@austinpickett #17175）
- **`/reload` .env 热重载**
- **可插拔 busy-indicator 样式**（@OutThisLife #13610）
- **opt-in auto-resume** 上次 session
- **扩展 light-terminal auto-detection**（`HERMES_TUI_THEME` + 背景十六进制）
- **`d` 在 `/resume` picker 删除 session**
- **modified mouse-wheel 行滚动 + `/mouse` 切换**（WSL2 ConPTY 修复）
- **`?` 在输入框弹迷你 help 菜单**
- **TUI Voice Mode** —— VAD 循环 + TTS + crash 取证 parity

### 性能（v2026.4.30 冷启动 -57%）

- **lazy agent init**（@OutThisLife #17190）—— 不启动到第一次输入前不实例化 AIAgent
- **lazy import** OpenAI / Anthropic / Firecrawl / account_usage（#17046）
- **mtime-cache** `load_config()` + `read_raw_config()`（#17041）
- **memoize `get_tool_definitions()`** + TTL-cache `check_fn` 结果（#17098）
- **precompile** `DANGEROUS_PATTERNS` + `HARDLINE_PATTERNS`（#17206）
- **cache Ink text measurements** 跨 yoga flex re-pass（#14818）
- **stabilize long-session scrolling**（#15926）
- **lazily seed virtual history heights**（#16523）

### 结构

- 入口分 `src/entry.tsx`（TTY gate）和 `src/app.tsx`（state machine）
- 持久 `_SlashWorker` 子进程做 slash command dispatch
- `app.tsx` 拆分到 `app/event-handler` / `app/slash-handler` / `app/stores` / `app/hooks`
- Hook 拆分：`useCompletion` / `useInputHistory` / `useQueue` / `useVirtualHistory`
- 组件拆分：`branding.tsx` / `markdown.tsx` / `prompts.tsx` / `sessionPicker.tsx` / `messageLine.tsx` / `thinking.tsx` / `maskedPrompt.tsx`

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

## 相关页面

- [[configuration-and-profiles]] — 配置管理与 Profile 系统
- [[hook-system-architecture]] — Hook 与插件扩展系统
- [[session-search-and-sessiondb]] — 会话搜索与 SessionDB
- [[voice-mode-architecture]] — 语音模式（Push-to-talk → STT → TTS）
- [[skin-engine]] — 皮肤/主题自定义
- [[context-references]] — @file/@diff/@url 引用系统
- [[worktree-isolation]] — Git Worktree 并行隔离
- [[code-execution-sandbox]] — 代码执行沙箱

## 相关文件

- `cli.py` — CLI 主类
- `hermes_cli/main.py` — 入口点和子命令
- `hermes_cli/commands.py` — 斜杠命令定义
- `hermes_cli/dump.py` — `hermes dump` 环境摘要（纯文本，用于调试/提 issue）
- `agent/display.py` — 显示系统
- `hermes_cli/skin_engine.py` — 皮肤引擎
