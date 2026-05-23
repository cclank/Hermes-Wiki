---
title: i18n — 静态消息本地化
created: 2026-05-14
updated: 2026-05-14
type: concept
tags: [i18n, localization, locales, gateway, ui, module]
sources: [agent/i18n.py, locales/]
version: v0.13.0
---

# i18n — 静态消息本地化

## 概述

v0.13.0 引入 `agent/i18n.py`（258 行）+ `locales/<lang>.yaml`，把 Hermes 自身发出的*静态用户面*消息翻译成多种语言。**by design 不翻译 agent 生成的输出 / log / tool result / slash 描述**——后者一旦本地化就会破坏 prompt cache、增加翻译漂移、并把英文为主的运维信号变成多语言乱炖。

## 范围（thin slice）

只覆盖以下三类（`agent/i18n.py` 顶部 docstring 明列）：

1. **Approval prompts**（"Allow this command?" 等）
2. **若干 gateway slash 命令回复**
3. **Restart-drain notice**（重启时给用户的优雅提示）

其余一律保留英文。

## 支持语言

v0.13.0 正式 ship **8 个 catalog**（en + 7 个新语言：zh / ja / de / es / fr / tr / uk）。

v0.13.0 之后（`c39168453`, 2026-05-10, #22914）一次性把 catalog 扩到 **16 个**，并把 gateway 命令 + Web Dashboard 也接入。

**当前 main 上的 16 个 catalog**（`locales/<lang>.yaml`，验证自 `ls locales/`）：

```
en (baseline), zh, zh-hant, ja, de, es, fr, tr, uk,
af, ko, it, ga, pt, ru, hu
```

`SUPPORTED_LANGUAGES`（`agent/i18n.py:42`）：

```python
SUPPORTED_LANGUAGES: tuple[str, ...] = (
    "en", "zh", "zh-hant", "ja", "de", "es", "fr", "tr", "uk",
    "af", "ko", "it", "ga", "pt", "ru", "hu",
)
DEFAULT_LANGUAGE = "en"
```

## 语言别名

`_LANGUAGE_ALIASES`（`agent/i18n.py:51-83`）覆盖常见自然写法和 BCP-47 标签：

| 类型 | 例子 |
|------|------|
| 英文母语名 | `chinese → zh`、`japanese → ja`、`german → de` |
| 区域细分 | `zh-cn / zh-hans / zh-sg → zh`、`zh-tw / zh-hk / zh-mo → zh-hant`、`fr-fr / fr-ca → fr` |
| 自指 | `日本語 → ja`、`中文 → zh`、`español → es`、`한국어 → ko`、`русский → ru` |
| 兼容写法 | `traditional-chinese / traditional_chinese → zh-hant`、`brazilian → pt`、`gaeilge → ga` |

未知 lang 一律 fall back 到 `"en"`。

## 解析顺序

`agent/i18n.py:t()` 解析当前 lang（docstring 第一节）：

1. 显式 `lang=` 参数（测试 / 临时覆盖）
2. `HERMES_LANGUAGE` 环境变量
3. `display.language` 配置（`config.yaml`）
4. baseline `"en"`

## 查找链

```python
t("approval.choose")          # 当前 lang
t("gateway.draining", count=3)# {count} 格式化
t("approval.choose_long", lang="zh")  # 显式覆盖
```

key path 是 dotted（`approval.choose`、`gateway.approval_expired`）。catalog 文件是**扁平 dict**（不是 nested YAML 树），便于一眼扫一行。

**Missing-key 三层回落**（保证永远不崩）：

1. `<current_lang>` catalog 命中 → 返回
2. 未命中 → `en` catalog
3. 仍未命中 → 字面 key path（`"approval.choose"`）

## 缓存

`@lru_cache` + `_catalog_cache` + `_catalog_lock`（line 84-86）—— catalog YAML 解析一次缓存，多线程安全。

## 集成点

| 调用方 | 用途 |
|--------|------|
| `tools/approval.py` | dangerous-command approval prompt（"once / session / always / deny"） |
| `gateway/run.py` | restart drain notice、若干静态 slash 回复 |
| `gateway/restart.py` | 同上 |
| Web Dashboard | `c39168453` 引入 dashboard 静态文案翻译（gateway commands + dashboard，16 个 locale 同步） |

## 文档站

`docs/` 站点 ship 简体中文（zh-Hans）locale（v0.13.0 release notes 提及）。docs i18n 是独立工具链（Docusaurus），与 `agent/i18n.py` 静态消息系统不共用 catalog。

## 为什么这么窄？

设计文档（`agent/i18n.py` 顶部）明示：

> Scope (thin slice, by design): only the highest-impact static strings shown to the user by Hermes itself ... Agent-generated output, log lines, error tracebacks, tool outputs, and slash-command descriptions all stay in English.

理由：

1. **Prompt cache**：agent 的 system / tool 描述本地化后跨 lang 切换会失效 cache
2. **运维信号一致**：log / traceback 多语言混杂使 grep 失效
3. **翻译漂移成本**：tool 输出是 agent 推理依据，翻译错一句就可能改变 agent 行为

## 相关页面

- [[messaging-gateway-architecture]] — restart drain notice 在 gateway 启动 / `/update` 时使用
- [[security-defense-system]] — approval prompt 是 i18n 的最大消费者
- [[cli-architecture]] — `display.language` 配置

## 相关文件

- `agent/i18n.py` — `t()` 函数与解析链
- `locales/` — 16 个 YAML catalog
- `tools/approval.py` — approval prompt 使用方
