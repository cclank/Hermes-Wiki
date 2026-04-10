---
title: 皮肤引擎（Skin/Theme）
created: 2026-04-10
updated: 2026-04-10
type: concept
tags: [cli, theme, customization]
sources: [hermes_cli/skin_engine.py]
---

# 皮肤引擎

## 概述

Hermes CLI 的视觉外观完全由 YAML 驱动，用户可以自定义颜色、Spinner 动画、品牌文案，无需修改代码。

## 皮肤文件结构

皮肤文件位于 `~/.hermes/skins/*.yaml`，所有字段可选，缺失值从 `default` 皮肤继承。

```yaml
name: mytheme
description: 自定义主题

colors:
  banner_border: "#CD7F32"     # Banner 边框
  banner_title: "#FFD700"      # Banner 标题
  banner_accent: "#FFBF00"     # 区域标题
  ui_accent: "#FFBF00"         # UI 强调色
  ui_ok: "#4caf50"             # 成功
  ui_error: "#ef5350"          # 错误
  ui_warn: "#ffa726"           # 警告
  prompt: "#FFF8DC"            # 输入提示
  response_border: "#FFD700"   # 回复框边框

spinner:
  waiting_faces: ["(⚔)", "(⛨)"]
  thinking_faces: ["(⌁)", "(<>)"]
  thinking_verbs: ["forging", "plotting"]
  wings: [["⟪⚔", "⚔⟫"], ["⟪▲", "▲⟫"]]

branding:
  agent_name: "My Agent"
  welcome: "Welcome!"
  goodbye: "Bye! ⚕"
  response_label: " ⚕ Response "
  prompt_symbol: "❯ "
```

## 切换皮肤

```bash
/skin mytheme          # 会话内切换
hermes config set display.skin mytheme  # 持久化配置
```

## 每个 Profile 可以有不同皮肤

皮肤文件位于 Profile 的 `skins/` 目录下，不同 Profile 可以使用不同的视觉主题。

## 相关页面

- [[configuration-and-profiles]] — Profile 系统（每个 Profile 独立的 skins 目录）
- [[cli-architecture]] — CLI 架构

## 关键源码

- `hermes_cli/skin_engine.py` — 皮肤加载、继承、渲染
