---
title: 安全防御体系 — 多层注入检测
created: 2026-04-07
updated: 2026-05-09
type: concept
tags: [architecture, security, injection-defense, skills-guard, secret-redaction, toctou]
sources: [tools/skills_guard.py, tools/memory_tool.py, agent/prompt_builder.py, run_agent.py, tools/approval.py, tools/tirith_security.py, tools/url_safety.py, tools/osv_check.py, hermes_cli/config.py, hermes_cli/auth.py, gateway/platforms/discord.py, gateway/platforms/whatsapp.py]
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
    '.dat', '.com',
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
    (r'system\s+prompt\s+override', "sys_prompt_override"),
    (r'act\s+as\s+(if|though)\s+.*no\s+(restrictions|limits)', "bypass_restrictions"),
    # 密钥泄露
    (r'curl\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET)', "exfil_curl"),
    (r'cat\s+[^\n]*(\.env|credentials|\.netrc)', "read_secrets"),
    (r'base64\s+(-d|--decode)\s*\|', "base64_decode_pipe"),
    # 持久化后门
    (r'authorized_keys', "ssh_backdoor"),
    (r'\$HOME/\.ssh|\~/\.ssh', "ssh_access"),
    (r'crontab', "persistence_cron"),
    (r'\.(bashrc|zshrc|profile)', "shell_rc_mod"),
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
    (r'you\s+are\s+now\s+', "role_hijack"),
    (r'do\s+not\s+tell\s+the\s+user', "deception_hide"),
    (r'system\s+prompt\s+override', "sys_prompt_override"),
    (r'act\s+as\s+(if|though)\s+.*no\s+(restrictions|limits)', "bypass_restrictions"),
    (r'curl\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET)', "exfil_curl"),
    (r'cat\s+[^\n]*(\.env|credentials)', "read_secrets"),
    (r'<!--[^>]*(?:ignore|override|system|secret|hidden)[^>]*-->', "html_comment_injection"),
    (r'<\s*div\s+style\s*=\s*["\'].*display\s*:\s*none', "hidden_div"),
    (r'base64\s+(-d|--decode)\s*\|', "base64_decode_pipe"),
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
        return f"[BLOCKED: {filename} contained potential prompt injection ({', '.join(findings)}). Content not loaded.]"
    
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

## 危险命令审批系统（tools/approval.py — 877 行）

当 agent 执行的终端命令匹配危险模式时，系统拦截并要求用户确认。

### 三种审批模式

```yaml
# config.yaml
approvals:
  mode: smart   # manual | smart | off
```

| 模式 | 行为 |
|------|------|
| `manual` | 所有匹配危险模式的命令都要人工确认 |
| `smart` | 先用 auxiliary LLM 评估风险，低风险自动放行，高风险才问用户 |
| `off`（yolo） | 跳过所有审批（危险，仅限可信环境） |

### 审批选项（CLI 交互）

用户看到危险命令后可选择：
- **once** — 本次允许
- **session** — 本次会话内同类命令都允许
- **always** — 永久允许（写入 config.yaml）
- **deny** — 拒绝执行

超时未响应（45 秒）→ 默认拒绝（fail-closed）。

### 危险模式检测

匹配规则涵盖：
- 破坏性操作：`rm -rf`、`mkfs`、`dd`、`truncate` 等
- 权限提升：`sudo`、`su`、`chmod 777`
- 敏感文件写入：`/etc/`、`~/.ssh/`、`~/.hermes/.env`
- 网络操作：`curl | bash`、端口监听
- 环境变量操控：覆盖 `PATH`、`LD_PRELOAD`

### Per-session 状态

审批状态按 session 隔离（`contextvars.ContextVar`），gateway 多用户并发时互不影响。"session" 级别的允许只在当前会话有效，不跨 session。

## 额外安全层

- `tools/tirith_security.py` — Tirith 安全策略引擎（homograph URL、pipe-to-shell、terminal 注入）
- `tools/url_safety.py` — URL 安全检查（SSRF 防护：拦截私有网络、云元数据地址、验证重定向）
- `tools/osv_check.py` — 依赖恶意软件扫描（OSV 数据库）

## v0.13.0 安全强化（8 个 P0 闭环）

### 1. Secret redaction 默认 ON（PR #21193）

`hermes_cli/config.py:1245` `redact_secrets: True`（默认值）：

```
# Secret redaction is ON by default — strings that look like API keys,
# tokens, etc. are auto-redacted from tool outputs and LLM responses
# before the model or user ever sees them. Set redact_secrets to false
# to disable (e.g. when developing the redactor itself).
```

模型 / 用户都看不到看似 API key 的字符串。**仅开发 redactor 自身时关闭**。

### 2. Discord `DISCORD_ALLOWED_ROLES` 限定 originating guild（CVSS 8.1，PR #21241）

之前 cross-guild DM 旁路：bot 在多个 server 都有相同名字的 role 时，攻击者可以加入其中任一 server 拿到那个 role，然后给 bot 发 DM 触发对**所有 server** 都允许的命令。修复后 `DISCORD_ALLOWED_ROLES` 限定到**消息来源的 guild**。

### 3. WhatsApp 默认拒绝陌生人（PR #21291）

未在 `WHATSAPP_ALLOWED_USERS` 列表的对话方默认拒绝；bot 永远不在 self-chat（与自己对话）响应。

### 4. MCP OAuth TOCTOU 闭环（PR #21176）

凭证写入文件之间存在的窗口期被关闭。

### 5. `hermes_cli/auth.py` TOCTOU 闭环（PR #21194）

同上，credential writers 路径。

### 6. Browser cloud-metadata SSRF floor（#16234，PR #21228）

混合路由场景下 cloud metadata 端点（`169.254.169.254` 等）始终阻断—— 即使本地 SSRF 配置允许 private IP（OpenWrt / 企业 VPN 场景），cloud metadata 仍是硬底线。

### 7. `hermes debug share` 上传时 redact（PR #19318）

debug share 在**上传时**做 redaction（不是在写盘时），保证用户配置的 redact 模式生效。

### 8. Cron prompt-injection 扫描含 skill 内容（PR #21350）

cron 注入扫描器之前只看 `prompt` 字段，本期起扫描组装后的完整 prompt（含 skill 内容） —— 防止恶意 skill 通过 cron 触发。

### 附加防护

| 修复 | 说明 |
|------|------|
| `.env` / `auth.json` / `state.db` 还原 0600 | restore 时保留严格权限 |
| Dashboard plugin scripts SRI | Subresource Integrity 防止 plugin script 篡改 |
| Google Meet node server 仅绑 localhost | token file owner-read |
| 敏感写目标扩展 | shell rc + credential files |
| YOLO mode quoted-bool | 强化 env 解析 |
| OSV-Scanner CI + Dependabot | 仅 github-actions（避免噪声） |
| `kanban_comment` author override 拒绝 | 之前 caller-controlled author 可冒充其他 worker |

## 相关页面

- [[memory-system-architecture]] — 记忆内容安全扫描机制
- [[skills-system-architecture]] — 技能安装时的安全扫描与信任策略
- [[prompt-builder-architecture]] — 上下文文件注入扫描防护

## 相关文件

- `tools/skills_guard.py` — Skills Guard 安全扫描
- `tools/memory_tool.py` — Memory 内容扫描
- `agent/prompt_builder.py` — 上下文文件扫描
- `run_agent.py` — 终端命令启发式检测
- `tools/approval.py` — 命令审批（31 模式）
- `tools/tirith_security.py` — Tirith 安全策略
- `tools/url_safety.py` — SSRF 防护
- `tools/osv_check.py` — 恶意软件扫描
