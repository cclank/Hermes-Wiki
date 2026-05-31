---
title: CLI 架构与终端交互设计
created: 2026-04-07
updated: 2026-05-31
type: concept
tags: [architecture, cli, terminal, ux, tui, ink, setup, prompt-size, partial-compress]
sources: [cli.py, hermes_cli/, ui-tui/, tui_gateway/, hermes_cli/partial_compress.py, hermes_cli/prompt_size.py, hermes_cli/mcp_startup.py]
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

Hermes 实际上有 **两个完全独立的 CLI 前端**（共用同一后端 agent）：

1. **经典 CLI**（`cli.py` + `hermes_cli/`） —— Python `prompt_toolkit` + `rich`，进 `hermes` 默认入口。
2. **Ink TUI**（`ui-tui/` + `tui_gateway/`） —— v0.11.0 起的 React/Ink 重写，进 `hermes --tui`。Python 这边跑一个 JSON-RPC server（`tui_gateway/`），Ink Node 进程通过 RPC 调 agent。

> Ink TUI 是 v0.11.0 ~310 commits 的重写（@OutThisLife + Teknium）。v0.12.0 完成 ~57% 冷启动加速，v0.14.0 进一步 −19 秒。

## 经典 CLI

基于 `prompt_toolkit` 和 `rich` 构建。

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

### 工具失败具体错误（2026-05-23，`094d732`）

`agent/display.py:+44` —— 工具完成行的失败 suffix 现在显示**具体** error message（解析 JSON `error`/`message` 字段），不再统一打 `[error]`：

| 之前 | 之后 |
|------|------|
| `┊ 📖 read foo.py 0.1s [error]` | `┊ 📖 read foo.py 0.1s [File not found: foo.py]` |

`agent/tool_executor.py:+2` 把原始 JSON result 透传到 display，display 层做窄宽截断。

### Todo 进度分数（2026-05-23，`ffde8b7`）

`agent/display.py:+18` 解析 `todo_tool` 结果的 summary，预览行显示 `done/total fraction`：

```
读: ┊ 📋 plan 3/4 task(s) 0.5s
写: ┊ 📋 plan update 3/4 ✓ 0.5s
```

无完成任务时回退到 plain count。+243 行测试覆盖渲染。

### `display.tool_progress: verbose` 与 root logger DEBUG 解耦（2026-05-24，`c9b3eea`，#31379）

`cli.py:2860-2865`：之前 PR `6a1aa42` 把 `display.tool_progress="verbose"`（per-tool 显示完整 args/results/think blocks）耦合到 `self.verbose`（root logger DEBUG level），结果**只是想看完整工具调用**的用户**整个进程 DEBUG 日志泛滥**。

修复后：

- `self.verbose` 仅控制 root logger DEBUG。
- `self.tool_progress_mode = "off" | "new" | "all" | "verbose"` 独立控制 tool-call 渲染。

`tui_gateway/server.py:+6` 同步取消耦合。

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

## v0.12 - v0.14 新增子命令与斜杠命令

### 新 hermes 子命令

| 命令 | 引入版本 | 说明 |
|------|---------|------|
| `hermes -z <prompt>` | v0.12.0 | One-shot 非交互模式，配 `--model` / `--provider` / `HERMES_INFERENCE_MODEL` |
| `hermes update --check` | v0.12.0 | preflight 升级检查 + opt-in HERMES_HOME backup |
| `hermes curator {archive, prune, list-archived, backup, rollback}` | v0.12/v0.13 | Curator 扩展子命令（详见 [[skills-system-architecture]]） |
| `hermes kanban {add, dispatch, claim, complete, reclaim, ...}` | v0.13.0 | 持久化 Kanban CLI（详见 [[multi-agent-architecture]]） |
| `hermes proxy {start, status, list-providers}` | v0.14.0 | OpenAI-compatible 本地代理：`hermes_cli/proxy/cli.py:30,78,102` |
| `hermes acp --setup-browser` | v0.14.0 | Zed ACP registry 引导浏览器工具安装 |
| `pip install hermes-agent && hermes` | v0.14.0 | PyPI 正式上架（`pyproject.toml:6` `name = "hermes-agent"`） |
| `hermes setup --portal` | v0.14.0 (2026-05-23) | 一键 Nous Portal 起步：OAuth + provider=nous + Tool Gateway opt-in；幂等可重复跑（`hermes_cli/setup.py:3063-3173 _run_portal_one_shot`） |
| `hermes portal {status, open, tools}` | v0.14.0 (2026-05-23) | 状态/订阅页/Tool Gateway 路由薄表面，缺省派发 `status`（`hermes_cli/portal_cli.py:175-220`，注册 `hermes_cli/main.py:11877-11880`） |
| `hermes kanban promote <id> [reason ...] [--ids id...] [--force] [--dry-run] [--json]` | 2026-05-23 | 手动 todo→ready 恢复（auto-promote daemon 漏父任务 done 时使用），`--ids` 批量；`task_events kind="promoted_manual"`（区分 daemon 自动 promoted）。源码 `hermes_cli/kanban.py:553-584` |
| `hermes skills audit [name] --deep` | 2026-05-23 | AST 深度诊断（`tools/skills_ast_audit.py:84 ast_scan_path`）—— 在 regex Skills Guard 之上覆盖动态 `importlib.import_module(computed)` / `getattr(obj, computed)` 等绕过模式。输出为 diagnostic hints，不影响 install gate（详见 [[skills-system-architecture]]） |

### 新斜杠命令（v0.13.0+）

`hermes_cli/commands.py`：

| 斜杠 | 位置 | 说明 |
|------|------|------|
| `/goal <目标>` | `commands.py:105` | 锁定跨轮持久目标（Ralph loop），judge 评分推进直到 DONE（`hermes_cli/goals.py`） |
| `/subgoal {show, append, remove, clear}` | `commands.py:107` | 给运行中的 `/goal` mid-loop 追加成功标准 |
| `/handoff <profile>` | `commands.py:82` | 实时迁移整个 session（v0.14.0 升级带 message + tool call + context 一起迁） |
| `/steer <text>` | `commands.py:103` | 对正在运行的 agent 注入纠偏指令 |
| `/queue <text>` | `commands.py:101` | 后续指令排队进 inflight agent |
| `/reload-skills` | v0.12.0 | rescan `~/.hermes/skills/`（不打破 prompt cache） |
| `/reload` | v0.12.0 | `.env` 热重载（TUI 也支持） |
| `/mouse` | v0.12.0 | toggle ConPTY phantom mouse 注入 |

## Nous Portal 一键起步（v0.14.0, 2026-05-23+）

PR #30860（commit `b4cf5b6`）把 Portal 订阅做成 CLI 一等公民，三个面向不同用户的 surface：

### `hermes setup --portal`

`hermes_cli/setup.py:3063-3173 _run_portal_one_shot`：单一命令把新用户从零带到可工作的 Hermes：

1. 调 `auth_add_command` 等价路径跑 OAuth device flow（已登录则跳过 — `setup.py:3103-3110`）
2. `config.model.provider = "nous"`，让运行时挑 Nous 默认模型（`setup.py:3155`）
3. `prompt_enable_tool_gateway(config)` 一句 Y/n 把 Web/Image/TTS/Browser 全部路由进 Portal（`setup.py:3164`）

OAuth 失败 / 用户取消 / 其他异常各自独立提示，永不静默回退。

### `hermes portal {status, open, tools}`

`hermes_cli/portal_cli.py`：

| 子命令 | 行为 | 源码 |
|------|------|------|
| `status`（默认） | Portal 登录 + 当前 inference provider + Tool Gateway 5 类目路由摘要 | `portal_cli.py:39-108` |
| `open` | `webbrowser.open("https://portal.nousresearch.com/manage-subscription")` | `portal_cli.py:111-123` |
| `tools` | 列 Web/Image/TTS/Browser/Modal 五类 + 每类 partner + 当前 provider | `portal_cli.py:126-172` |

默认派发 `status` —— gh / kubectl 同惯例（`portal_cli.py:177-181`）。注册在 `main.py:11877-11880`，并加进 `_BUILTIN_SUBCOMMANDS`（`main.py:10657`）防被插件发现快路径覆盖。

### Tool Picker "Nous-included" 标记

`hermes_cli/tools_config.py`（+44 行）：

- 已登录 Nous → provider rows 显星 ★ + 副标 "Included with your Nous subscription"（`tools_config.py:1999-2015 managed_by_nous` 检查）
- 未登录但被提示输入付费 API key（Firecrawl/FAL/ElevenLabs/Browserbase 等）→ 单行淡灰 "Available through Nous Portal subscription."（`tools_config.py:2430-2447 _show_portal_hint`），且仅当该类目有 Nous-managed sibling

非订阅用户体验完全不变。

### Portal request tags（`agent/portal_tags.py`）

所有发往 Nous Portal 的请求统一打 `product=hermes-agent` + `client=hermes-client-v<__version__>` —— 4 处独立 call site 历史会漂移（见 PR #24194），由此模块集中（`portal_tags.py:37-65`）。版本来自 live `hermes_cli.__version__`，避免被预计算成常量。

## Native Windows 支持（v0.14.0+）

`scripts/check-windows-footguns.py` + `pyproject.toml:60,66`（tzdata、psutil）：原生 `cmd.exe` + PowerShell 跑通，**无需 WSL**。完整 PowerShell installer 含 MinGit 自动安装、Microsoft Store python stub 检测、前台 Ctrl+C dance。本版后续跟 40+ Windows-only fix（taskkill、native PTY、信号差异、路径规范化、file-locking）。

## OSC8 可点击 URL（v0.14.0+）

任何支持 OSC8 的终端中 agent 输出的 URL 都是真 hyperlink，hover 高亮、点击在浏览器打开。iTerm2 / Kitty / Ghostty / 现代 Windows Terminal 都支持。

## 安全/UX 微调（2026-05-24）

| 改动 | 源码 | 说明 |
|------|------|------|
| `display.tool_progress: verbose` 不再开 root DEBUG | `cli.py:2860-2865` + `tui_gateway/server.py:+6` | 见上文「`display.tool_progress: verbose` 与 root logger DEBUG 解耦」 |
| TUI slash dropdown 不再砍 `/goal` 末字符 | `tui_gateway/server.py:+7` + `ui-tui/src/components/appOverlays.tsx:+13` | prompt_toolkit `Completion.display` 是 `FormattedText`（list 子类），原 JSON-RPC payload 写成 `[["", "/goal"]]`，下游错位（#31311） |
| TUI 状态栏新增 TTS 指示器 | `ui-tui/src/app/interfaces.ts:+3` + `useMainApp.ts:+12` | `/voice off` 清 `HERMES_VOICE_TTS`，前端跟踪 `voiceTts` state |
| ZIP 升级失败 tempdir 不再泄露 | `hermes_cli/main.py:+7` | `shutil.rmtree` 进 `finally`（`2c34a7d`） |
| `.env` 加载前 strip null bytes | `hermes_cli/env_loader.py:+10` | API key copy-paste 末尾 null bytes 不再让 `os.environ[k]=v` 抛 `ValueError: embedded null byte`（`75643a6`） |
| Qwen auth status 检查 refresh capability | `hermes_cli/main.py` | 仅 access token 在期不足以判 healthy（`e8fa415`） |
| `HERMES_SESSION_ID` 在 env 与 contextvar 间同步 | `gateway/session_context.py:+15` | session switch 不再两端漂（`86871ee`） |
| `display.tool_progress` 工具失败行显示具体错误 | `agent/display.py:+44` | `094d732`，详见上文 |
| `todo` 显示 `done/total fraction` | `agent/display.py:+18` | `ffde8b7`，详见上文 |

## 国际化（v0.13.0+）

`locales/` 共 **16 个语言 YAML**（af、de、en、es、fr、ga、hu、it、ja、ko、pt、ru、tr、uk、zh、zh-hant），gateway + CLI 静态消息可翻译。Docs 站点拿 zh-Hans。

## v0.14 增量 — 2026-05-27（migrate xai / dashboard OAuth config / update --branch）

### `hermes migrate xai` — May 15 2026 退役模型自动迁移

`hermes_cli/migrate.py:cmd_migrate_xai` + `hermes_cli/xai_retirement.py`（253 行，纯逻辑无 IO）：

```bash
hermes migrate xai              # 干跑展示替换计划
hermes migrate xai --apply      # 用 ruamel round-trip 重写 config.yaml in-place（保留注释/顺序）
hermes migrate xai --no-backup  # 跳过 .bak 写出
```

- 退役名单来源 `https://docs.x.ai/developers/migration/may-15-retirement`
- 同 `hermes doctor` 复用 `find_retired_xai_refs(config)`（`b4ba425`）
- chat 启动时 warn 退役模型（`a8a05c8`）

子命令注册：`hermes_cli/main.py:11265-11297`。

### `hermes update --branch <name>` + post-pull syntax-validate auto-rollback

- `feat(cli): add --branch flag to hermes update`（`51689a4`）—— 让 fork 用户固定到自定义 branch
- `feat(update): syntax-validate critical files post-pull, auto-rollback on failure (#28669, aedb8ac)` —— 拉新代码后跑 `python -m py_compile`、`yaml.safe_load`、`json.loads` 等校验，失败则 git reset 回原 HEAD
- `fix: check upstream even when origin/main has no new commits`（`6f2a2f1`）
- `fix(update): bypass systemd RestartSec after graceful drain (#22101, d971b26)`
- `fix(update): quarantine hermes.exe vs concurrent Windows instance (#26670, 2a7308b)`
- `fix(entry-points): guard hermes_bootstrap import so partial updates don't brick hermes (#22091, 26bac67)`

### Dashboard OAuth 配置 surface

详见 [[dashboard-auth-oauth-gate]]。CLI 暴露的 config keys：

```yaml
dashboard:
  oauth:
    client_id: agent:{agent_instance_id}   # 必填（Nous Portal 风格）
    portal_url: https://portal.example     # 可选
  public_url: https://...                   # OAuth redirect_uri 基址覆盖（Fly.io 等公网部署）
```

环境变量覆盖（空值视作未设）：`HERMES_DASHBOARD_OAUTH_CLIENT_ID` / `HERMES_DASHBOARD_PORTAL_URL` / `HERMES_DASHBOARD_PUBLIC_URL`。

### TUI Session Orchestrator（新 in-TUI multi-session 视图）

详见 [[2026-05-27-update#5-tui-session-orchestrator]]。`ui-tui/src/components/activeSessionSwitcher.tsx`（635 行）+ `tui_gateway/server.py +221` 行新 RPC。能：
- list / activate / close / launch 进程内多个 TUI session
- 切换时 hydrate committed 与 in-flight output
- 浮窗 orchestrator overlay 支持 mouse hit-testing
- chrome 区暴露可点击 live-session 计数

### Bitwarden EU + 自托管 Server URL

`bc3f1f4`（#31378）：`secrets.bitwarden.server_url` 配置 — EU = `https://vault.bitwarden.eu`、自托管 = 任意私有 URL。配合先前的 `feat(secrets): Bitwarden Secrets Manager integration with lazy bws install (#30035)` 与 `feat(secrets): label detected credentials with their source (Bitwarden) (#30364)` 完成 Bitwarden integration matrix。

### Nix 包变体

`9769794`「feat(nix): add #messaging and #full package variants (#33108)」：
- `nix run github:NousResearch/hermes-agent#messaging` —— 所有 gateway 平台依赖
- `nix run github:NousResearch/hermes-agent#full` —— 全功能 (含 vision/voice/skills/...)

### API Server 三连

`gateway/platforms/api_server.py`：

- **Session controls**（`f7527b0`，+476 行）—— 外部客户端 CRUD session
- **`GET /v1/skills`**（#33016）—— 列已安装 skill（name/description/category），受 `API_SERVER_KEY` 保护
- **`GET /v1/toolsets`**（#33016）—— 列 `api_server` 平台 resolved toolset + 展开的 tool name
- `/v1/capabilities` 广告 `skills_api` + `toolsets_api`（`9622326`）
- session chat API 支持媒体输入（`464b51d`）

### 性能微调（v0.14 hot path）

- `load_config_readonly()`（`hermes_cli/config.py:4579`）—— 跳过 defensive deepcopy 让 `hermes_cli/timeouts.py:22,51` 的每 API call 路径减半成本，agent loop per-conversation 函数调用 −47%（#28866）
- `perf(cli): skip eager plugin discovery on known built-in subcommands (#22120, 5089596)`
- `perf(cli): defer openai._base_client import via sys.meta_path finder (#28864, 784febe)`
- termux 系列 fast-path（`a3beee4` / `6c3fd97` / `6dbbf20` / `c29b4f5`）

## 相关页面

- [[configuration-and-profiles]] — 配置管理与 Profile 系统
- [[hook-system-architecture]] — Hook 与插件扩展系统
- [[session-search-and-sessiondb]] — 会话搜索与 SessionDB
- [[voice-mode-architecture]] — 语音模式（Push-to-talk → STT → TTS）
- [[skin-engine]] — 皮肤/主题自定义
- [[context-references]] — @file/@diff/@url 引用系统
- [[worktree-isolation]] — Git Worktree 并行隔离
- [[code-execution-sandbox]] — 代码执行沙箱
- [[multi-agent-architecture]] — `/goal`、`/handoff`、`/steer`、`/queue`、Kanban CLI
- [[smart-model-routing]] — `hermes proxy` OpenAI-compatible 本地代理

## v0.15.1 维护窗口增量（2026-05-31，hermes `eb3cf9750`）

### Setup 重构 — Quick Setup 直通 Nous Portal（#35723，`de4f40ed0`）

`hermes setup` 首次运行不再展示完整 provider 选择器，直接进 Nous Portal：

- `hermes_cli/setup.py:3010` 菜单文本 `"Quick Setup (Nous Portal) — OAuth login, model & messaging (recommended)"`
- `hermes_cli/setup.py:3064 _run_first_time_quick_setup` 调用 `hermes_cli.main._model_flow_nous(config)`（line 3086-3087），同时覆盖**未登录**（device-code OAuth → 精选 Nous model）与**已登录**（直接精选 picker）两条路径。
- 完成后**从磁盘 re-sync config dict**（line 3096+），避免 #4172 的 stale-overwrite。
- Terminal / defaults / messaging 步骤不变。

### Full Setup happy-defaults

- 删除：同 provider rotation pool / vision-backend picker / TTS sub-flow。Vision 从主 provider 自动检测；TTS 默认 Edge；rotation 移到 `hermes auth add`。
- Terminal 章节保留 backend picker（默认 Local）+ 必要凭据（Modal token、SSH host/user/key、Daytona key）。

### Picker 迁 curses（#35776，`087be0073` + `3463c97a3` + `8f4c8e7c8`）

setup 的 provider→model 子菜单及 3 个同类 picker 从 `simple_term_menu.TerminalMenu` 迁到 curses；`3463c97a3` 在 `curses_radiolist` 包装层解码原始方向键序列（`\x1b[A/B/C/D`）；`8f4c8e7c8` 提取 `_curses_menu_event_loop_driver` 共享驱动器复用。

### `hermes prompt-size` 诊断命令（#35276，`61268ff7a`，关闭 #34667）

- `hermes_cli/prompt_size.py:141 cmd_prompt_size(args)` —— 153 行新模块。
- `hermes_cli/main.py:14467-14486` subparser 注册：`prompt-size [--platform NAME] [--json]`。
- 报告新会话**固定 prompt budget** 拆分：system prompt total / skills index / memory / user profile / prompt tiers / tool-schema JSON bytes。
- **零模型工具足迹**：顶层 CLI subcommand，非 agent 工具。
- **离线运行**：假凭据强制走 direct-construction，不发网络。

观察：skills index 通常是最大单块（issue #34667 的典型症状）。

### `/compress here [N]`（#35048，`bcc830100`）

用户选择压缩边界。详见 [[context-compressor-architecture]] 的 §2026-05-31 增量。`hermes_cli/partial_compress.py` 新模块 235 行。

### Tool Gateway 始终展示 + 选中即登录（#35792，`1fc7bdc5e`）

`hermes tools` 列表中的 Nous-managed Tool Gateway 行（Firecrawl / OpenAI TTS / Browser Use / FAL image / FAL video）原本仅在已登录时显示；改成**始终可见**，选中时触发 OAuth 登录流。让 onboarding 期就看到这些托管后端的存在。

### Model picker 多 endpoint 合并 + catalog TTL 24h→1h

- `93e6a05ef` (#35227) —— 同 provider 跨多 endpoint 合并到一行，让用户先选 provider 再选 endpoint。
- `e1293bde4` (#35756) —— `model_catalog` 磁盘缓存 TTL 24h → 1h，新发布的 `model-catalog.json` 一小时内进 picker。

### CLI 状态簇

- **`/status` token 标签精化**（`9d4c81130` + `2259c15e4`）—— "Cumulative API tokens (re-sent each call)" 替换误导性 "Session usage (cumulative)"。
- **CLI 状态栏 token sentinel 钳制**（`f2d4cf4f7`，#35858）—— `max(0, last_prompt_tokens or 0)`。
- **CLI context display 与 preflight token estimate 同步**（`897f9533e`，#35079）。
- **`/steer` 与 `/model` 内联提交后 input 区重绘**（`04de307d6`，#34839）。
- **OSC 11 bg-color 探测在 SSH 下不再 trap 用户进 stray editor**（`5921d6678`，#35441）。
- **oneshot 失败 stderr + rc=1**（`433bffff5`）+ **空响应 fail closed**（`9fbde54b5`）。
- **uninstall 清 Hermes-managed node/npm/npx symlinks**（`54aa4db1d`）。

### Update / install 簇

- **`uv tool upgrade` 走 uv tool install path**（`1bdb29d93`，#29700）
- **pipx + `--system` fallback**（`2334228ec`）
- **launcher virtualenv 透传到 uv**（`14517ac1f`）
- **Windows launcher-shim 排出 concurrent check**（`2475244ca`，#35257）
- **migration prompt 列新增 config key + 纯版本号 bump 跳过**（`9ed9af2f7`，#35658）
- **pyproject vs `hermes_cli/__init__.py` 版本漂移在 `hermes doctor` 报告**（`bb79bcde6`，#35142）
- **container 但非 Docker image 不当作 image update**（`c1b2d0917`，#35139）

### 进程标题 'hermes'（`84ee80eb5`）

- `hermes_cli/main.py:68 _set_process_title()` —— `:11505 main()` 入口最早处调用。
- 策略链：`setproctitle`（opt-in）→ `ctypes prctl(PR_SET_NAME)` on Linux → `pthread_setname_np` on macOS → Windows no-op。
- 任何失败静默，不增加新 dependency。

### MCP discovery 不阻塞 agent-capable startup（`0c6e133c0`）

新文件 `hermes_cli/mcp_startup.py`（59 行）+ tests 166 行：MCP server discovery 改 background task，避免冷启动阻塞。详见 [[mcp-and-plugins]]。

### TUI 簇

- **delegation 启动时 nudge `/agents` dashboard**（`5a72e82fd` + `9d2571c86` + `e481b1533`）
- **WSL `131072x1` 终端维度钳制**（`b1d34cf6e`，#35657）
- **鼠标 burst 噪声不再卡 composer**（`cd067ab91`，#35512）
- **PowerShell clipboard 改 base64 stdin flag**（`64998fa93` + `16882cfde`）

---

## 相关文件

- `cli.py` — 经典 CLI 主类（660KB；大单体文件）
- `hermes_cli/main.py` — 入口点和子命令
- `hermes_cli/commands.py` — 斜杠命令定义（lines 82, 101, 103, 105, 107 为新增）
- `hermes_cli/goals.py` — `/goal` Ralph loop 实现
- `hermes_cli/kanban.py` — Kanban CLI（2677 行）
- `hermes_cli/proxy/` — OpenAI-compatible 本地代理（v0.14.0+）
- `hermes_cli/portal_cli.py` — `hermes portal {status,open,tools}` 薄表面（2026-05-23+）
- `hermes_cli/setup.py:3010,3064` — Quick Setup (Nous Portal) 入口（2026-05-31+）
- `hermes_cli/partial_compress.py` — `/compress here [N]` 模块（235 行，2026-05-29+）
- `hermes_cli/prompt_size.py` — `hermes prompt-size` 诊断（153 行，2026-05-30+）
- `hermes_cli/mcp_startup.py` — MCP discovery 非阻塞 background task（59 行，2026-05-30+）
- `agent/portal_tags.py` — Portal 请求标签集中点（`product=hermes-agent` + `client=hermes-client-v<ver>`）
- `hermes_cli/dump.py` — `hermes dump` 环境摘要（纯文本，用于调试/提 issue）
- `agent/display.py` — 显示系统
- `hermes_cli/skin_engine.py` — 皮肤引擎
- `locales/` — 16 个语言 YAML
