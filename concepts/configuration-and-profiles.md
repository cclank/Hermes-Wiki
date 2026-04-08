---
title: 配置管理与 Profile 系统
created: 2026-04-07
updated: 2026-04-07
type: concept
tags: [architecture, configuration, profile, ux]
sources: [hermes-agent 源码分析 2026-04-07]
---

# 配置管理与 Profile 系统

## 设计原理

Hermes 需要管理大量配置项：模型、工具、技能、平台、凭证等。使用**分层配置 + Profile 隔离**实现灵活管理。

## 配置层次

```
1. 硬编码默认值 (hermes_cli/config.py)
2. 环境变量 (.env, shell)
3. 用户配置 (~/.hermes/config.yaml)
4. Profile 覆盖 (HERMES_HOME 环境变量)
```

## 配置文件

```yaml
# ~/.hermes/config.yaml
model: "anthropic/claude-opus-4.6"
provider: "anthropic"
max_turns: 90
compression_enabled: true

agent:
  tool_use_enforcement: "auto"  # true/false/auto/list
  prompt_caching: true
  cache_ttl: "5m"

delegation:
  max_iterations: 50
  model: ""
  base_url: ""

display:
  skin: "default"

tools:
  disabled:
    telegram: ["image_generate"]

skills:
  config:
    wiki:
      path: ~/wiki
```

## 环境变量

```bash
# ~/.hermes/.env
OPENROUTER_API_KEY=sk-or-...
ANTHROPIC_API_KEY=sk-ant-...
TELEGRAM_BOT_TOKEN=123456:ABC-...
HERMES_HOME=~/.hermes
```

## Profile 系统

```python
# hermes_cli/profiles.py

def list_profiles() -> list[Profile]:
    """列出所有 Profile"""
    profiles = []
    for dir in get_hermes_home().parent.iterdir():
        if (dir / "config.yaml").exists():
            profiles.append(Profile(name=dir.name, path=dir))
    return profiles

def get_active_profile_name() -> str:
    """获取当前 Profile 名称"""
    return get_hermes_home().name

def seed_profile_skills(profile_path: Path, quiet: bool = False) -> dict:
    """为 Profile 播种技能"""
    skills_dir = profile_path / "skills"
    return sync_skills_to_dir(skills_dir, quiet=quiet)
```

### 切换 Profile

```bash
# 通过环境变量
HERMES_HOME=~/.hermes-work hermes

# 或通过 CLI 命令
hermes profile switch work
```

## 配置迁移

```python
# hermes_cli/config.py

def migrate_config(interactive: bool = True, quiet: bool = False) -> dict:
    """迁移配置到最新版本"""
    results = {
        "env_added": [],
        "config_added": [],
        "env_removed": [],
        "config_removed": [],
    }
    
    # 检查缺失的环境变量
    missing_env = get_missing_env_vars(required_only=True)
    for var in missing_env:
        if interactive:
            value = input(f"Enter value for {var}: ")
            save_env_var(var, value)
        results["env_added"].append(var)
    
    # 检查缺失的配置字段
    missing_config = get_missing_config_fields()
    for field in missing_config:
        default = get_field_default(field)
        save_config_value(field, default)
        results["config_added"].append(field)
    
    return results
```

## 优越性分析

### 与其他 Agent 框架对比

| 特性 | Hermes | Claude Code | Cursor |
|------|--------|-------------|--------|
| 分层配置 | ✅ 4 层 | ✅ 2 层 | ✅ 2 层 |
| Profile 隔离 | ✅ HERMES_HOME | ❌ | ❌ |
| 配置迁移 | ✅ 自动检测 | ❌ | ❌ |
| 环境变量加载 | ✅ .env 文件 | ❌ | ❌ |
| 技能配置 | ✅ 每技能独立 | N/A | N/A |

## 相关页面

- [[cli-architecture]] — CLI 架构与终端交互设计
- [[credential-pool-and-isolation]] — 凭证池与环境隔离系统
- [[skills-system-architecture]] — 技能系统架构（受 Profile 隔离影响）

## 相关文件

- `hermes_cli/config.py` — 配置管理
- `hermes_cli/profiles.py` — Profile 系统
- `hermes_cli/env_loader.py` — 环境变量加载
