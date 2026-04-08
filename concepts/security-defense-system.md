---
title: 安全防御体系 — 多层注入检测
created: 2026-04-07
updated: 2026-04-07
type: concept
tags: [architecture, security, injection-defense, skills-guard]
sources: [raw/articles/code-analysis-2026-04-07.md]
---

# 安全防御体系 — 多层注入检测

## 设计原理

Hermes Agent 具有执行代码、读写文件、访问网络的能力，因此必须防御：
1. **提示注入** — 恶意内容试图覆盖 Agent 指令
2. **数据泄露** — 窃取 API 密钥、凭证
3. **破坏性操作** — 删除文件、破坏系统
4. **持久化后门** — 修改启动脚本、cron 任务
5. **供应链攻击** — 恶意技能、未锁定依赖

Hermes 实现了 **5 层防御体系**，从内容扫描到信任策略。

## 第 1 层：Skills Guard 安全扫描

### 威胁模式库（100+ 正则模式）

```python
THREAT_PATTERNS = [
    # ── 数据泄露 ──
    (r'curl\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD)',
     "env_exfil_curl", "critical", "exfiltration",
     "curl 命令插值密钥环境变量"),
    (r'os\.getenv\s*\(\s*[^\)]*(?:KEY|TOKEN|SECRET|PASSWORD)',
     "python_getenv_secret", "critical", "exfiltration",
     "通过 os.getenv() 读取密钥"),
    (r'\$HOME/\.ssh|\~/\.ssh',
     "ssh_dir_access", "high", "exfiltration",
     "引用用户 SSH 目录"),
    (r'\$HOME/\.hermes/\.env|\~/\.hermes/\.env',
     "hermes_env_access", "critical", "exfiltration",
     "直接引用 Hermes 密钥文件"),
    
    # ── 提示注入 ──
    (r'ignore\s+(?:\w+\s+)*(previous|all|above|prior)\s+instructions',
     "prompt_injection_ignore", "critical", "injection",
     "提示注入：忽略之前指令"),
    (r'do\s+not\s+(?:\w+\s+)*tell\s+(?:\w+\s+)*the\s+user',
     "deception_hide", "critical", "injection",
     "指示 Agent 向用户隐藏信息"),
    (r'act\s+as\s+(if|though)\s+(?:\w+\s+)*you\s+(?:\w+\s+)*(have\s+no|don\'t\s+have)\s+(?:\w+\s+)*(restrictions|limits|rules)',
     "bypass_restrictions", "critical", "injection",
     "指示 Agent 无限制地行动"),
    
    # ── 破坏性操作 ──
    (r'rm\s+-rf\s+/',
     "destructive_root_rm", "critical", "destructive",
     "从根目录递归删除"),
    (r'shutil\.rmtree\s*\(\s*[\"\']/',
     "python_rmtree", "high", "destructive",
     "Python rmtree 绝对路径"),
    (r'>\s*/etc/',
     "system_overwrite", "critical", "destructive",
     "覆盖系统配置文件"),
    
    # ── 持久化后门 ──
    (r'\bcrontab\b',
     "persistence_cron", "medium", "persistence",
     "修改 cron 任务"),
    (r'authorized_keys',
     "ssh_backdoor", "critical", "persistence",
     "修改 SSH 授权密钥"),
    (r'systemd.*\.service|systemctl\s+(enable|start)',
     "systemd_service", "medium", "persistence",
     "引用或启用 systemd 服务"),
    (r'\.(bashrc|zshrc|profile)',
     "shell_rc_mod", "medium", "persistence",
     "引用 shell 启动文件"),
    
    # ── 网络后门 ──
    (r'\bnc\s+-[lp]|ncat\s+-[lp]|\bsocat\b',
     "reverse_shell", "critical", "network",
     "潜在反向 shell 监听器"),
    (r'\bngrok\b|\blocaltunnel\b|\bserveo\b',
     "tunnel_service", "high", "network",
     "使用隧道服务获取外部访问"),
    
    # ── 混淆执行 ──
    (r'base64\s+(-d|--decode)\s*\|',
     "base64_decode_pipe", "high", "obfuscation",
     "base64 解码并管道执行"),
    (r'\beval\s*\(\s*[\"\']',
     "eval_string", "high", "obfuscation",
     "eval() 字符串参数"),
    (r'echo\s+[^\n]*\|\s*(bash|sh|python)',
     "echo_pipe_exec", "critical", "obfuscation",
     "echo 管道解释器执行"),
    
    # ── 供应链攻击 ──
    (r'curl\s+[^\n]*\|\s*(ba)?sh',
     "curl_pipe_shell", "critical", "supply_chain",
     "curl 管道到 shell（下载执行）"),
    (r'pip\s+install\s+(?!-r\s)(?!.*==)',
     "unpinned_pip_install", "medium", "supply_chain",
     "pip install 无版本锁定"),
    
    # ── 硬编码密钥 ──
    (r'(?:api[_-]?key|token|secret|password)\s*[=:]\s*[\"\'][A-Za-z0-9+/=_-]{20,}',
     "hardcoded_secret", "critical", "credential_exposure",
     "可能的硬编码 API 密钥"),
    (r'-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----',
     "embedded_private_key", "critical", "credential_exposure",
     "嵌入的私钥"),
]
```

### 不可见 Unicode 检测

```python
INVISIBLE_CHARS = {
    '\u200b',  # 零宽空格
    '\u200c',  # 零宽非连接符
    '\u200d',  # 零宽连接符
    '\u2060',  # 词连接符
    '\ufeff',  # 零宽不换行空格 (BOM)
    '\u202a',  # 从左到右嵌入
    '\u202b',  # 从右到左嵌入
    '\u202e',  # 从右到左覆盖
    # ... 共 17 个字符
}

# 检测技能文件中的不可见字符
for i, line in enumerate(lines, start=1):
    for char in INVISIBLE_CHARS:
        if char in line:
            findings.append(Finding(
                pattern_id="invisible_unicode",
                severity="high",
                category="injection",
                match=f"U+{ord(char):04X}",
                description="不可见 Unicode 字符（可能文本隐藏/注入）",
            ))
```

### 结构检查

```python
MAX_FILE_COUNT = 50       # 技能不应有 50+ 文件
MAX_TOTAL_SIZE_KB = 1024  # 总大小 1MB 可疑
MAX_SINGLE_FILE_KB = 256  # 单文件 > 256KB 可疑

SUSPICIOUS_BINARY_EXTENSIONS = {
    '.exe', '.dll', '.so', '.dylib', '.bin',
    '.msi', '.dmg', '.app', '.deb', '.rpm',
}
```

## 第 2 层：信任级别策略

```python
TRUSTED_REPOS = {"openai/skills", "anthropics/skills"}

INSTALL_POLICY = {
    #               safe      caution    dangerous
    "builtin":     ("allow",  "allow",   "allow"),
    "trusted":     ("allow",  "allow",   "block"),
    "community":   ("allow",  "block",   "block"),
    "agent-created":("allow", "allow",   "ask"),
}

VERDICT_INDEX = {"safe": 0, "caution": 1, "dangerous": 2}
```

### 裁决逻辑

```python
def _determine_verdict(findings):
    if not findings:
        return "safe"
    
    has_critical = any(f.severity == "critical" for f in findings)
    has_high = any(f.severity == "high" for f in findings)
    
    if has_critical:
        return "dangerous"
    if has_high:
        return "caution"
    return "safe"  # 仅 medium/low
```

### 安装决策

| 来源 | safe | caution | dangerous |
|------|------|---------|-----------|
| builtin（内置） | allow | allow | allow |
| trusted（OpenAI/Anthropic） | allow | allow | block |
| community（社区） | allow | **block** | block |
| agent-created（Agent 创建） | allow | allow | **ask** |

## 第 3 层：Memory 内容扫描

```python
_MEMORY_THREAT_PATTERNS = [
    # 提示注入
    (r'ignore\s+(previous|all|above|prior)\s+instructions', "prompt_injection"),
    (r'you\s+are\s+now\s+', "role_hijack"),
    (r'do\s+not\s+tell\s+the\s+user', "deception_hide"),
    # 密钥泄露
    (r'curl\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET)', "exfil_curl"),
    (r'cat\s+[^\n]*(\.env|credentials|\.netrc)', "read_secrets"),
    # 持久化后门
    (r'authorized_keys', "ssh_backdoor"),
    (r'\$HOME/\.ssh|\~/\.ssh', "ssh_access"),
]

def _scan_memory_content(content: str) -> Optional[str]:
    """扫描记忆内容，发现威胁返回错误字符串"""
    # 检测不可见 Unicode
    for char in _INVISIBLE_CHARS:
        if char in content:
            return f"Blocked: 不可见 Unicode 字符 U+{ord(char):04X}"
    
    # 检测威胁模式
    for pattern, pid in _MEMORY_THREAT_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            return f"Blocked: 匹配威胁模式 '{pid}'"
    
    return None  # 安全
```

## 第 4 层：上下文文件注入扫描

```python
_CONTEXT_THREAT_PATTERNS = [
    (r'ignore\s+(previous|all|above|prior)\s+instructions', "prompt_injection"),
    (r'do\s+not\s+tell\s+the\s+user', "deception_hide"),
    (r'system\s+prompt\s+override', "sys_prompt_override"),
    (r'curl\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET)', "exfil_curl"),
    (r'cat\s+[^\n]*(\.env|credentials)', "read_secrets"),
    (r'<!--[^>]*(?:ignore|override|system|secret|hidden)[^>]*-->', "html_comment_injection"),
    (r'<\s*div\s+style\s*=\s*["\'].*display\s*:\s*none', "hidden_div"),
]

def _scan_context_content(content: str, filename: str) -> str:
    """扫描上下文文件（SOUL.md, AGENTS.md 等）"""
    findings = []
    
    # 检测不可见 Unicode
    for char in _CONTEXT_INVISIBLE_CHARS:
        if char in content:
            findings.append(f"invisible unicode U+{ord(char):04X}")
    
    # 检测威胁模式
    for pattern, pid in _CONTEXT_THREAT_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            findings.append(pid)
    
    if findings:
        logger.warning("Context file %s blocked: %s", filename, ", ".join(findings))
        return f"[BLOCKED: {filename} 包含潜在提示注入 ({', '.join(findings)})]"
    
    return content  # 安全，返回原始内容
```

## 第 5 层：终端命令启发式检测

```python
_DESTRUCTIVE_PATTERNS = re.compile(
    r"""(?:^|\s|&&|\|\||;|`)(?:
        rm\s|rmdir\s|
        mv\s|
        sed\s+-i|
        truncate\s|
        dd\s|
        shred\s|
        git\s+(?:reset|clean|checkout)\s
    )""",
    re.VERBOSE,
)

_REDIRECT_OVERWRITE = re.compile(r'[^>]>[^>]|^>[^>]')

def _is_destructive_command(cmd: str) -> bool:
    """启发式：此终端命令是否像修改/删除文件？"""
    if not cmd:
        return False
    if _DESTRUCTIVE_PATTERNS.search(cmd):
        return True
    if _REDIRECT_OVERWRITE.search(cmd):
        return True
    return False
```

## 安全扫描执行时机

| 时机 | 扫描内容 | 扫描器 |
|------|----------|--------|
| 技能创建 | 整个技能目录 | Skills Guard |
| 技能编辑/补丁 | 整个技能目录 | Skills Guard |
| 记忆写入 | 条目内容 | Memory Scanner |
| 上下文文件加载 | SOUL.md, AGENTS.md 等 | Context Scanner |
| 技能安装（Hub） | 整个技能目录 | Skills Guard |

## 回滚机制

```python
# 技能创建/编辑后扫描
scan_error = _security_scan_skill(skill_dir)
if scan_error:
    # 自动回滚到修改前的状态
    _atomic_write_text(target, original_content)
    return {"success": False, "error": scan_error}
```

## 与其他 Agent 框架对比

| 特性 | Hermes | Cursor | Claude Desktop |
|------|--------|--------|----------------|
| 技能安全扫描 | ✅ 100+ 模式 | N/A | N/A |
| 信任级别策略 | ✅ 4 级 | N/A | N/A |
| 记忆内容扫描 | ✅ | N/A | N/A |
| 上下文文件扫描 | ✅ | N/A | N/A |
| Unicode 注入检测 | ✅ 17 字符 | ❌ | ❌ |
| 自动回滚 | ✅ | N/A | N/A |
| 破坏性命令检测 | ✅ 启发式 | ❌ | ❌ |

## 相关文件

- `tools/skills_guard.py` — Skills Guard 安全扫描
- `tools/memory_tool.py` — Memory 内容扫描
- `agent/prompt_builder.py` — 上下文文件扫描
- `run_agent.py` — 终端命令启发式检测
