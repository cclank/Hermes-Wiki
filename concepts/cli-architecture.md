---
title: CLI 架构与终端交互设计
created: 2026-04-07
updated: 2026-04-07
type: concept
tags: [architecture, cli, terminal, ux]
sources: [raw/articles/code-analysis-2026-04-07.md]
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
    completer=SlashCommandCompleter(),
)

user_input = session.prompt("🐍 > ")
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
    
    FACES = ["◕‿◕", "◕_◕", "◔‿◔", "⊙‿⊙", "◕︵◕"]
    VERBS = ["thinking", "processing", "calculating", "pondering", "wondering"]
    WINGS = ["♪", "♫", "♬", "✧", "✦"]
    
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
class SkinEngine:
    """CLI 主题引擎"""
    
    def __init__(self, skin_config: dict):
        self.banner_colors = skin_config.get("banner_colors", {})
        self.spinner_faces = skin_config.get("spinner_faces", KawaiiSpinner.FACES)
        self.spinner_verbs = skin_config.get("spinner_verbs", KawaiiSpinner.VERBS)
        self.tool_prefix = skin_config.get("tool_prefix", "┊")
        self.response_box = skin_config.get("response_box", "rounded")

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

## 相关文件

- `cli.py` — CLI 主类
- `hermes_cli/main.py` — 入口点和子命令
- `hermes_cli/commands.py` — 斜杠命令定义
- `agent/display.py` — 显示系统
- `hermes_cli/skin_engine.py` — 皮肤引擎
