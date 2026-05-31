---
title: 模糊匹配引擎 — 8 策略链
created: 2026-04-07
updated: 2026-05-31
type: concept
tags: [architecture, tool, reliability, fuzzy-matching, patch, indentation, crlf, escalation, atomic-write, utf8-bom, gutter]
sources: [tools/fuzzy_match.py, tools/file_operations.py, tools/file_tools.py]
---

# 模糊匹配引擎 — 8 策略链

## 设计原理

当 Agent 修改文件时，需要找到要替换的文本。LLM 生成的文本可能与原文有细微差异（空格、缩进、转义序列等）。Hermes 实现了 **8 策略链**，从精确匹配逐步降级到模糊匹配，最大化匹配成功率。

灵感来自 OpenCode 的模糊匹配实现。

## 8 策略链

```python
strategies = [
    ("exact", _strategy_exact),                    # 1. 精确匹配
    ("line_trimmed", _strategy_line_trimmed),      # 2. 逐行修剪
    ("whitespace_normalized", _strategy_whitespace_normalized),  # 3. 空白规范化
    ("indentation_flexible", _strategy_indentation_flexible),    # 4. 缩进灵活
    ("escape_normalized", _strategy_escape_normalized),          # 5. 转义规范化
    ("trimmed_boundary", _strategy_trimmed_boundary),            # 6. 边界修剪
    ("block_anchor", _strategy_block_anchor),      # 7. 块锚定
    ("context_aware", _strategy_context_aware),    # 8. 上下文感知
]

for strategy_name, strategy_fn in strategies:
    matches = strategy_fn(content, old_string)
    if matches:
        # 找到匹配 → 执行替换
        if len(matches) > 1 and not replace_all:
            return content, 0, f"找到 {len(matches)} 个匹配，请提供更多上下文"
        new_content = _apply_replacements(content, matches, new_string)
        return new_content, len(matches), None

# 所有策略都失败
return content, 0, "未找到匹配"
```

## 策略详解

### 策略 1：精确匹配

```python
def _strategy_exact(content, pattern):
    """直接字符串匹配"""
    matches = []
    start = 0
    while True:
        pos = content.find(pattern, start)
        if pos == -1:
            break
        matches.append((pos, pos + len(pattern)))
        start = pos + 1
    return matches
```

**适用场景：** LLM 生成的文本与原文完全一致

### 策略 2：逐行修剪

```python
def _strategy_line_trimmed(content, pattern):
    """逐行去除首尾空白后匹配"""
    pattern_lines = [line.strip() for line in pattern.split('\n')]
    pattern_normalized = '\n'.join(pattern_lines)
    
    content_lines = content.split('\n')
    content_normalized_lines = [line.strip() for line in content_lines]
    
    # 在规范化内容中查找，映射回原始位置
    return _find_normalized_matches(...)
```

**适用场景：** LLM 生成的文本每行首尾有多余空格

### 策略 3：空白规范化

```python
def _strategy_whitespace_normalized(content, pattern):
    """将多个空格/制表符折叠为单个空格"""
    def normalize(s):
        return re.sub(r'[ \t]+', ' ', s)
    
    pattern_normalized = normalize(pattern)
    content_normalized = normalize(content)
    
    # 在规范化内容中查找，映射回原始位置
    return _map_normalized_positions(content, content_normalized, matches)
```

**适用场景：** LLM 生成的文本空格数量不一致

### 策略 4：缩进灵活

```python
def _strategy_indentation_flexible(content, pattern):
    """完全忽略缩进差异"""
    content_stripped_lines = [line.lstrip() for line in content.split('\n')]
    pattern_lines = [line.lstrip() for line in pattern.split('\n')]
    
    # 去除所有前导空白后匹配
    return _find_normalized_matches(...)
```

**适用场景：** LLM 生成的文本缩进级别不同

### 策略 5：转义规范化

```python
def _strategy_escape_normalized(content, pattern):
    """将转义序列转换为实际字符"""
    def unescape(s):
        return s.replace('\\n', '\n').replace('\\t', '\t').replace('\\r', '\r')
    
    pattern_unescaped = unescape(pattern)
    if pattern_unescaped == pattern:
        return []  # 无转义序列，跳过
    
    return _strategy_exact(content, pattern_unescaped)
```

**适用场景：** LLM 生成的文本包含字面转义序列

### 策略 6：边界修剪

```python
def _strategy_trimmed_boundary(content, pattern):
    """仅修剪首行和尾行的空白"""
    pattern_lines = pattern.split('\n')
    pattern_lines[0] = pattern_lines[0].strip()
    if len(pattern_lines) > 1:
        pattern_lines[-1] = pattern_lines[-1].strip()
    
    # 在内容中滑动窗口匹配
    for i in range(len(content_lines) - pattern_line_count + 1):
        block_lines = content_lines[i:i + pattern_line_count]
        check_lines = block_lines.copy()
        check_lines[0] = check_lines[0].strip()
        if len(check_lines) > 1:
            check_lines[-1] = check_lines[-1].strip()
        
        if '\n'.join(check_lines) == modified_pattern:
            matches.append(...)
```

**适用场景：** 仅首尾行有空白差异

### 策略 7：块锚定

```python
def _strategy_block_anchor(content, pattern):
    """基于首尾行锚定，中间部分使用相似度匹配"""
    # Unicode 规范化
    norm_pattern = _unicode_normalize(pattern)
    norm_content = _unicode_normalize(content)
    
    pattern_lines = norm_pattern.split('\n')
    first_line = pattern_lines[0].strip()
    last_line = pattern_lines[-1].strip()
    
    # 查找首尾行匹配的位置
    for i in range(len(norm_content_lines) - pattern_line_count + 1):
        if (norm_content_lines[i].strip() == first_line and 
            norm_content_lines[i + pattern_line_count - 1].strip() == last_line):
            
            # 计算中间部分的相似度
            content_middle = '\n'.join(norm_content_lines[i+1:i+pattern_line_count-1])
            pattern_middle = '\n'.join(pattern_lines[1:-1])
            similarity = SequenceMatcher(None, content_middle, pattern_middle).ratio()
            
            # 阈值：唯一匹配 0.10，多候选 0.30
            threshold = 0.10 if candidate_count == 1 else 0.30
            if similarity >= threshold:
                matches.append(...)
```

**适用场景：** 首尾行匹配，中间内容有细微差异

### 策略 8：上下文感知

```python
def _strategy_context_aware(content, pattern):
    """逐行相似度匹配，50% 阈值"""
    pattern_lines = pattern.split('\n')
    content_lines = content.split('\n')
    
    for i in range(len(content_lines) - pattern_line_count + 1):
        block_lines = content_lines[i:i + pattern_line_count]
        
        # 计算逐行相似度
        high_similarity_count = 0
        for p_line, c_line in zip(pattern_lines, block_lines):
            sim = SequenceMatcher(None, p_line.strip(), c_line.strip()).ratio()
            if sim >= 0.80:  # 单行 80% 相似度
                high_similarity_count += 1
        
        # 需要至少 50% 的行具有高相似度
        if high_similarity_count >= len(pattern_lines) * 0.5:
            matches.append(...)
```

**适用场景：** 整体内容有 50% 以上行相似

## Unicode 规范化

```python
UNICODE_MAP = {
    "\u201c": '"', "\u201d": '"',  # 智能双引号
    "\u2018": "'", "\u2019": "'",  # 智能单引号
    "\u2014": "--", "\u2013": "-", # 破折号
    "\u2026": "...", "\u00a0": " ", # 省略号和不间断空格
}

def _unicode_normalize(text: str) -> str:
    """将 Unicode 字符规范化为标准 ASCII 等价物"""
    for char, repl in UNICODE_MAP.items():
        text = text.replace(char, repl)
    return text
```

## 优越性分析

### 匹配成功率

| 场景 | 精确匹配 | 8 策略链 |
|------|----------|----------|
| 完全一致 | ✅ | ✅ |
| 首尾空格差异 | ❌ | ✅ 策略 2/6 |
| 缩进差异 | ❌ | ✅ 策略 4 |
| 转义序列差异 | ❌ | ✅ 策略 5 |
| 智能引号 | ❌ | ✅ 策略 7 |
| 中间内容微调 | ❌ | ✅ 策略 7/8 |

### 与其他工具对比

| 特性 | Hermes | sed/awk | Cursor |
|------|--------|---------|--------|
| 精确匹配 | ✅ | ✅ | ✅ |
| 空白容错 | ✅ 8 策略 | ❌ | ✅ 部分 |
| Unicode 规范化 | ✅ | ❌ | ✅ |
| 相似度匹配 | ✅ | ❌ | ❌ |
| 位置映射 | ✅ 精确 | N/A | ✅ |

## 2026-05-26 Patch 工具三连增强（feat #507 / #32273）

`6bd0be30b feat(patch): indentation preservation, CRLF preservation, per-file failure escalation` 在模糊匹配链外侧加了三个 patch-time 增强（Roo Code 深度对照取出的修复）。

### 缩进保留 — `_reindent_replacement()`（`tools/fuzzy_match.py:185-258`）

**问题场景**：fuzzy 链中 `exact` 之外的策略匹配成功时，LLM 发的 `old_string` / `new_string` 缩进可能与文件实际不同（典型：LLM 发 0 缩进的方法体，但目标方法住在 8-space 缩进 class 内）。原行为：直接 splice 进去，产出格式破但仍 parse 的文件。

**修复算法**（line 199-239）：

1. 取 `old_string` 第一非空 line 的 leading whitespace（LLM base indent）。
2. 取 `file_region` 第一非空 line 的 leading whitespace（file base indent）。
3. 若两 indent 相等 → no-op 直返；否则对 `new_string` 每非空行做 prefix swap：`file_base + (line_indent - llm_base)`，保留 LLM 增加的相对 nesting。

**调用约束**：`tools/fuzzy_match.py:274` 仅在 **non-exact** 策略匹配后调，`exact` 策略 passthrough（exact 即 1 比 1，不需要 reindent）。Approach 与 Roo Code `multi-search-replace.ts:466-500` 一致。

### CRLF 保留 — `_detect_line_ending()`（`tools/file_operations.py:77-103, 741-760, 1047, 1167`）

**问题场景**：模型几乎总用 bare LF 发 tool args（JSON encoded），但文件可能 CRLF（Windows `.bat` / `.cmd` / `.ini`）。原行为：

- `write_file` 静默把 CRLF 压成 LF
- patch 产出**混合**结尾的文件：substituted 段 LF，周围 CRLF

**修复**：

```python
def _detect_line_ending(sample: str) -> Optional[str]:
    # 扫前 4096 字节，比 \r\n vs \n 频次，决定 file 实际 ending
```

`_detect_file_line_ending(path, pre_content)`（line 741-760）：lint/LSP 已读 file 重用 `pre_content`，否则 `head -c 4096` 探测。`write_file` / `patch` 路径（line 1047 / 1167）检测到 `\r\n` 即对整个 write content `_normalize_line_endings(text, "\r\n")`。新文件 verbatim 写。

### Per-File 失败升级 — `_patch_failure_tracker`（`tools/file_tools.py:257-292, 1080-1095`）

**问题场景**：agent 对同一文件失败 3+ 次时，旧的 "old_string not found" hint 不够强；模型继续用变体老 old_string 撞 stale 文件视图。

**实现**：

```python
_patch_failure_tracker: dict[task_id][resolved_path] = count   # line 263
# LRU 64 path/task line 273-276
```

- `_record_patch_failure(task_id, resolved_path)` 每次 fail 自增。
- `_reset_patch_failures(task_id, paths)` 成功 patch 同 path 时清零（line 1060-1062：避免成功一次后再失败时立刻 escalate）。
- `failure_count >= 3` 注入 `_hint`（line 1080-1095）：

```text
This is failure #N patching '<path>'. Stop retrying with variations
of the same old_string. Either: (1) re-read the file fresh to verify
current content, (2) use a longer / more unique old_string with
surrounding context lines, or (3) use write_file to replace the
entire file if the targeted region is hard to anchor.
```

不到 3 次 fail 仍走旧的 "old_string not found. Use read_file..." hint（line 1097-1100）。

测试增量：`tests/tools/test_fuzzy_match.py +5`（缩进保留）/ `test_line_ending_preservation.py +12`（CRLF）/ `test_patch_failure_tracking.py +5`（失败计数 + reset）。所有现有测试 165/165 通过（commit body）。

## 2026-05-31 增量 — 文件 IO 健壮性三连

### 1. write_file / patch 原子化（#35252，`39f6b6e9d`）

`tools/file_operations.py:772 _atomic_write(self, path, content) -> ExecuteResult`：

- 流到 target 同**目录** temp file（关键：同 FS 才保证 rename 原子）。
- 经 `mv` 原子换到 target。失败：fallback PID-stamped 名（line 797 注释）。
- 模板（line 813）：
  ```bash
  tmp="$(mktemp ...)"
  [ -n "$tmp" ] || { echo "atomic write: could not create temp file" >&2; exit 1; }
  ...
  mv "$tmp" "$path"
  ```
- `patch` 路径在 `:1192-1207` 流到 temp 再 `mv`（line 1204 备注："保留 mode bits — atomic swap 不静默扩/收权限"）。

**影响**：进程崩溃 / out-of-disk 不会留半成品文件；reader 看到的要么是旧版本要么是完整新版本。

### 2. UTF-8 BOM 处理（#35278，`5f84c9144`）

某些 Windows 编辑器在文本首字符塞 U+FEFF。原行为三处出错：

| 路径 | 出错点 |
|---|---|
| read_file | 把 BOM 当首字符返回，模型看见 phantom U+FEFF |
| patch | 真正首行匹配可能漏（BOM 占了 char 0） |
| write/patch round-trip | 静默剥 BOM，把原文件改成非 BOM |

**修复**（`tools/file_operations.py`）：

- `:127 _UTF8_BOM = "﻿"`
- `:131 _strip_leading_bom(text) -> (text, had_bom)` —— 只剥首 BOM；中段 U+FEFF 保留（合法 unicode whitespace 用途）。
- `:142 _starts_with_utf8_bom(text)` 探测。
- `:848` `_file_has_bom` 属性（基于磁盘探测，新文件返 False —— 新建写不会带 BOM）。
- read（`:947`）："Strip a leading UTF-8 BOM so the model never sees a phantom U+FEFF"。
- write / patch 探测原文件 BOM 状态 → round-trip 后**保留 / 不保留**与磁盘上一致。

### 3. read_file 紧凑 gutter — ~14% token 节省（#35368/#35532，`ea6eaabd8` + `b1a25404b`）

原 gutter：固定宽度 `"     1|content"`（零/空格 padding 到 4-6 字符宽）。
新 gutter：紧凑 `"<n>|content"`（仅 `<n>` 实际位数 + `|`）。

**实测**（cl100k tokenizer on dense Hermes source）：
- padding：比 bare content 多 **~48%** token。
- 紧凑：比 bare content 多 **~16%** token。
- → 切换的净收益 **~14%**。

`b1a25404b` 是后续把它定为**唯一**格式：

- 删 `HERMES_READ_GUTTER=padded` env var 逃生口与其 lookup。
- `grep -r HERMES_READ_GUTTER` 全仓零命中（彻底删除）。
- `tools/file_operations.py:707-713` 文档化新策略 + "padding 是纯 token overhead，dense 源码上"。

### 4. 相对路径 anchor 到绝对 base（#35399，`96643b4a5`）

`fix(file-tools): anchor relative-path resolution to absolute base; report resolved path`：

- 之前：相对路径在 write_file / patch 解析对 **agent process cwd**（可能是 `/`、HERMES_HOME，或终端 init dir）。
- git worktree 会话特别危险：相对路径写到错 worktree。
- 修：相对路径强制 anchor 到**终端 cwd 的绝对 base**；返回**解析后的绝对路径**让用户验证。

---

## 相关页面

- [[model-tools-dispatch]] — 工具编排与调度（调用模糊匹配的上层）
- [[tool-registry-architecture]] — 工具注册系统（文件工具通过 registry 注册）
- [[skills-system-architecture]] — 技能管理工具中使用模糊匹配
- [[tool-loop-guardrails]] — Tool loop guardrails 的"同工具失败"维度与 patch 失败升级互补

## 相关文件

- `tools/fuzzy_match.py` — 模糊匹配引擎实现（含 2026-05-26 `_reindent_replacement` line 185-258）
- `tools/file_operations.py` — **NEW 2026-05-26** `_detect_line_ending` line 77-103 + 写入路径 CRLF 保留
- `tools/file_tools.py` — **NEW 2026-05-26** `_patch_failure_tracker` line 257-292 + 失败 #3+ 升级 hint line 1080-1095
- `tools/skill_manager_tool.py` — 技能管理中调用模糊匹配
