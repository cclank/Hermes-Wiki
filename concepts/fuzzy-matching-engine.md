---
title: 模糊匹配引擎 — 8 策略链
created: 2026-04-07
updated: 2026-04-07
type: concept
tags: [architecture, tool, reliability, fuzzy-matching]
sources: [raw/articles/code-analysis-2026-04-07.md]
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

## 相关文件

- `tools/fuzzy_match.py` — 模糊匹配引擎实现
- `tools/skill_manager_tool.py` — 技能管理中调用模糊匹配
- `tools/file_tools.py` — 文件工具中调用模糊匹配
