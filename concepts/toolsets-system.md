---
title: Toolsets System
created: 2026-04-07
updated: 2026-04-07
type: concept
tags: [toolset, tool, tool-registry, architecture]
sources: [hermes-agent 源码分析 2026-04-07]
---

# 工具集系统

## 概述

Toolsets 是 Hermes Agent 的**工具分组系统**，允许将工具组合成有意义的集合，并为不同场景/平台启用不同的工具集。

## 核心设计

```python
# toolsets.py
_HERMES_CORE_TOOLS = [
    # Web
    "web_search", "web_extract",
    # Terminal + process management
    "terminal", "process",
    # File manipulation
    "read_file", "write_file", "patch", "search_files",
    # Vision + image generation
    "vision_analyze", "image_generate",
    # Skills
    "skills_list", "skill_view", "skill_manage",
    # Browser automation
    "browser_navigate", "browser_snapshot", "browser_click",
    "browser_type", "browser_scroll", "browser_back",
    "browser_press", "browser_get_images",
    "browser_vision", "browser_console",
    # Text-to-speech
    "text_to_speech",
    # Planning & memory
    "todo", "memory",
    # Session history search
    "session_search",
    # Clarifying questions
    "clarify",
    # Code execution + delegation
    "execute_code", "delegate_task",
    # Cronjob management
    "cronjob",
    # Cross-platform messaging
    "send_message",
    # Home Assistant
    "ha_list_entities", "ha_get_state", "ha_list_services", "ha_call_service",
]
```

## 工具集定义

```python
TOOLSETS = {
    # 基础工具集
    "web": {
        "description": "Web research and content extraction tools",
        "tools": ["web_search", "web_extract"],
        "includes": []  # 不包含其他工具集
    },
    
    # 组合工具集
    "debugging": {
        "description": "Debugging and troubleshooting toolkit",
        "tools": ["terminal", "process"],
        "includes": ["web", "file"]  # 组合其他工具集
    },
    
    # 平台特定工具集
    "hermes-telegram": {
        "description": "Telegram bot toolset",
        "tools": _HERMES_CORE_TOOLS,  # 使用核心工具列表
        "includes": []
    },
    
    "hermes-acp": {
        "description": "Editor integration (VS Code, Zed, JetBrains)",
        "tools": [...],  # 编码专用，无消息/音频/clarify
        "includes": []
    },
    
    "hermes-api-server": {
        "description": "OpenAI-compatible API server",
        "tools": [...],  # 完整工具集，无交互 UI 工具
        "includes": []
    },
    
    # 注意："all" 不是 TOOLSETS 的一个条目
    # 它在 resolve_toolset() 中作为特殊情况处理
    # if name in {"all", "*"}: ...
}
```

## 递归解析

```python
def resolve_toolset(name: str, visited: Set[str] = None) -> List[str]:
    """递归解析工具集，处理组合依赖"""
    
    # 特殊别名：all 或 *
    if name in {"all", "*"}:
        all_tools = set()
        for toolset_name in get_toolset_names():
            resolved = resolve_toolset(toolset_name, visited.copy())
            all_tools.update(resolved)
        return list(all_tools)
    
    # 循环检测
    if name in visited:
        return []  # 静默返回
    
    visited.add(name)
    toolset = TOOLSETS.get(name)
    
    # 收集直接工具
    tools = set(toolset.get("tools", []))
    
    # 递归解析包含的工具集
    for included_name in toolset.get("includes", []):
        included_tools = resolve_toolset(included_name, visited)
        tools.update(included_tools)
    
    return list(tools)
```

## 平台工具集

| 工具集 | 平台 | 特点 |
|--------|------|------|
| `hermes-cli` | 终端 CLI | 完整工具集 |
| `hermes-telegram` | Telegram | 完整工具集 |
| `hermes-discord` | Discord | 完整工具集 |
| `hermes-whatsapp` | WhatsApp | 完整工具集 |
| `hermes-slack` | Slack | 完整工具集 |
| `hermes-signal` | Signal | 完整工具集 |
| `hermes-homeassistant` | Home Assistant | 智能家居控制 |
| `hermes-email` | Email (IMAP/SMTP) | 邮件交互 |
| `hermes-sms` | SMS (Twilio) | 短信，字符限制 |
| `hermes-mattermost` | Mattermost | 自托管团队消息 |
| `hermes-matrix` | Matrix | 去中心化加密消息 |
| `hermes-dingtalk` | 钉钉 | 企业消息 |
| `hermes-feishu` | 飞书/Lark | 企业消息 |
| `hermes-wecom` | 企业微信 | 企业微信消息 |
| `hermes-webhook` | Webhook | 接收外部事件 |
| `hermes-acp` | 编辑器集成 | 编码专用 |
| `hermes-api-server` | HTTP API | 通过 HTTP 访问 |

## 插件扩展

工具集支持插件动态注册：

```python
def _get_plugin_toolset_names() -> Set[str]:
    """返回插件注册的工具集名称"""
    from tools.registry import registry
    return {
        entry.toolset
        for entry in registry._tools.values()
        if entry.toolset not in TOOLSETS
    }
```

## 工具注册表

```python
# tools/registry.py
class ToolRegistry:
    def register(self, name, toolset, schema, handler, ...):
        """注册工具到中央注册表（需要 toolset 参数）"""
    
    def get_schema(self, name):
        """获取工具的 schema 定义"""
    
    def get_all_tool_names(self):
        """获取所有已注册工具名称"""
```

每个工具文件在导入时自动注册：

```python
# tools/terminal_tool.py
from tools.registry import registry

registry.register(
    name="terminal",
    toolset="terminal",
    schema=TERMINAL_SCHEMA,
    handler=terminal_handler,
    ...
)
```

## 工具启用/禁用

通过 `hermes tools` 命令或配置管理：

```yaml
# ~/.hermes/config.yaml
tools:
  disabled:
    telegram: ["image_generate"]
    discord: ["text_to_speech"]
```

## 文件依赖链

```
tools/registry.py  (无依赖 — 被所有工具文件导入)
       ↑
tools/*.py  (每个在导入时调用 registry.register())
       ↑
model_tools.py  (导入 tools/registry + 触发工具发现)
       ↑
run_agent.py, cli.py, batch_runner.py, environments/
```

## 相关页面

- [[tool-registry-architecture]] — 中央工具注册表（Registry 按 toolset 组织工具）
- [[model-tools-dispatch]] — 工具编排层通过 toolset 过滤工具定义
- [[mcp-and-plugins]] — 插件动态注册扩展工具集

## 相关文件

- `toolsets.py` — Toolset 定义和解析
- `tools/registry.py` — 中央工具注册表
- `model_tools.py` — 工具编排，`_discover_tools()`, `handle_function_call()`
- `hermes_cli/tools_config.py` — 工具启用/禁用配置
