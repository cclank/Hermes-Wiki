---
title: Checkpoint Manager v2 — 透明文件系统快照
created: 2026-05-14
updated: 2026-05-14
type: concept
tags: [checkpoint, git, shadow-store, snapshot, prune, architecture, module]
sources: [tools/checkpoint_manager.py]
version: v0.13.0
---

# Checkpoint Manager v2 — 透明文件系统快照

## 概述

`tools/checkpoint_manager.py` (1638 行) 在 `write_file` / `patch` / `terminal --dangerous` 之前**每轮**自动创建 shadow-git 快照，让用户可以回滚到任何 turn 之前的状态。v0.13.0 是大版本重写（**v2**），把 *per-project* shadow repo 改成 *单 shared bare-ish store*，对象去重 + 真 prune。

> 关键定位：**这不是工具** —— LLM 永远看不到 checkpoint manager 在 schema 里。它是透明基础设施，受 `checkpoints` 配置 flag 或 `--checkpoints` CLI flag 控制。

## v1 → v2 变更

### v1 的问题（`tools/checkpoint_manager.py:24-30` 注释）

- 每个 working directory 一个完整 shadow git repo
- objects 不跨项目去重
- 多项目用户磁盘暴涨
- prune 形同虚设

### v2 设计：单 shared store

```
~/.hermes/checkpoints/
    store/                           ← 单 bare-ish git repo
        HEAD, config, objects/       ← git 内部（跨项目共享）
        refs/hermes/<hash16>         ← 每项目分支 tip
        indexes/<hash16>             ← 每项目 git index
        projects/<hash16>.json       ← {workdir, created_at, last_touch}
        info/exclude                 ← 共享默认排除规则
    .last_prune                      ← auto-prune 幂等标记
    legacy-<timestamp>/              ← 自动迁移走的 pre-v2 per-project shadow repos
```

`hash16` 是 working directory 的 SHA hash 前 16 个字符，作为 namespace。

## 自动迁移

`migrate_legacy_shadows()`（`tools/checkpoint_manager.py:340`）：

- 第一次 v2 init 扫描 `CHECKPOINT_BASE`
- 把 *任何 pre-v2 shadow repo*（顶级目录里有 `HEAD` 文件的）+ 散乱目录搬到 `legacy-<timestamp>/` 子目录
- v2 reserved 顶级条目（`store/`、`.last_prune`、`legacy-*`）跳过
- v2 从干净状态启动，旧数据可手动恢复或随 legacy 一起按 retention 清理

## 实现要点

### git 状态完全隔离

`GIT_DIR` + `GIT_WORK_TREE` + `GIT_INDEX_FILE` 三个环境变量都指向 shared store —— **不**污染用户项目目录的 `.git/`：

```python
env = {
    "GIT_DIR":        store_dir,
    "GIT_WORK_TREE":  workdir,
    "GIT_INDEX_FILE": store_dir / "indexes" / hash16,
}
```

每次 commit 用 namespaced 分支 `refs/hermes/<hash16>`，objects 去重。

### `DEFAULT_EXCLUDES`（line 78-117）

预定义全局忽略，覆盖：

- 依赖 / build 输出：`node_modules/`、`dist/`、`build/`、`target/`、`.next/`、`.nuxt/`
- 缓存：`__pycache__`、`*.pyc`、`.pytest_cache`、`.mypy_cache`、`.ruff_cache`、`coverage/`
- 虚拟环境：`.venv/`、`venv/`、`env/`
- VCS：`.git/`、`.hg/`、`.svn/`
- Hermes 约定：`.worktrees/`（避免递归 snapshot 兄弟 worktree）
- 编译/二进制：`*.so`、`*.dylib`、`*.dll`、`*.o`、`*.a`、`*.jar`、`*.class`

### prune（`prune_checkpoints` line 1223）

```python
def prune_checkpoints(
    retention_days: int = 7,
    *,
    max_total_size_mb: int = 0,
) -> dict:
```

三步：

1. **Orphan**：`workdir` 字段不存在的 ref（项目已删除）→ 删
2. **Stale**：`last_touch` 早于 `now - retention_days * 86400` → 删
3. **Size cap**：`max_total_size_mb > 0` 时，逐项目按最旧 checkpoint 删，直到总大小低于阈值

最后 `git gc --prune=now` 回收 unreferenced objects。`legacy-*` 目录也按 retention 自动清。

`.last_prune` 文件提供幂等保护，避免多次 hermes 启动连续跑 prune。

## 触发条件

`maybe_checkpoint_before_tool()`（构造函数 line 601）—— *每轮 turn 最多一次*：

- tool 名属于 `write_file` / `patch` / `terminal` 且带 destructive flag → 在 tool execute **之前**抓快照
- 同一 turn 多次写入只在第一次 snapshot —— 完整保留到下一个 turn 的所有未提交修改

## 用户接口

```
hermes checkpoints list                    # 当前项目的快照
hermes checkpoints show <id>               # 看 diff
hermes checkpoints rollback <id>           # 回滚到某快照
hermes checkpoints prune                   # 立即执行 prune
hermes checkpoints config                  # 看 retention/cap 配置
```

`hermes_cli/checkpoints.py` 暴露 CLI；slash 命令 `/checkpoints` 共享同一 argparse surface。

## 配置（`config.yaml`）

```yaml
checkpoints:
  enabled: true
  retention_days: 7         # 7 天后过期
  max_total_size_mb: 500    # 总盘符上限；0 = 不限
```

## 验证总结

| 声明 | 验证 |
|------|------|
| 单 shared store | `tools/checkpoint_manager.py:71` `_STORE_DIRNAME = "store"` |
| Objects 跨项目去重 | 仅一个 `objects/` 目录 + namespace refs `refs/hermes/<hash16>` |
| Per-project namespace | 通过 `hash16` SHA 前缀 |
| 自动迁移 pre-v2 | `migrate_legacy_shadows()` line 340 |
| 真 prune | `prune_checkpoints` line 1223，含 `git gc --prune=now` |
| Size cap | `max_total_size_mb` line 589 + `_enforce_size_cap()` line 1087 |
| 不污染用户 `.git/` | `GIT_DIR` + `GIT_WORK_TREE` + `GIT_INDEX_FILE` 全部指向 shared store |
| LLM 看不到 | `tools/checkpoint_manager.py:12` —— "This is NOT a tool" |

## 相关页面

- [[worktree-isolation]] — `.worktrees/` 兄弟目录被 checkpoint 主动排除
- [[security-defense-system]] — `terminal` 的危险命令模式 + checkpoint 是回滚保险
- [[cli-architecture]] — `/checkpoints` 斜杠命令

## 相关文件

- `tools/checkpoint_manager.py` — 主实现（1638 行）
- `hermes_cli/checkpoints.py` — `hermes checkpoints` CLI
