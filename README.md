# Hermes Agent Architecture Wiki

<p align="center">
  <img src="https://img.shields.io/badge/Wiki-Hermes_Agent-blue?style=for-the-badge&logo=markdown" alt="Wiki" height="28">
  <img src="https://img.shields.io/badge/Source-hermes--agent-green?style=for-the-badge&logo=github" alt="Source" height="28">
  <img src="https://img.shields.io/badge/Knowledge_Base-36_pages-orange?style=for-the-badge" alt="Knowledge Base" height="28">
  <img src="https://img.shields.io/badge/Verified-Source_Code-brightgreen?style=for-the-badge" alt="Verified" height="28">
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge" alt="License" height="28">
</p>

> 基于 Nous Research [Hermes Agent](https://github.com/NousResearch/hermes-agent) 源码的深度架构文档。
> 所有页面均经过**逐行源码验证**，确保准确性与时效性。


---

## 目录结构
### 核心架构

- [agent-loop-and-prompt-assembly](concepts/agent-loop-and-prompt-assembly.md): Agent 循环、系统提示构建、平台提示、执行指导
- [tool-registry-architecture](concepts/tool-registry-architecture.md): 中央工具注册系统，声明式注册+集中调度
- [model-tools-dispatch](concepts/model-tools-dispatch.md): 工具编排与调度，异步桥接+动态 schema 调整+参数类型强制
- [toolsets-system](concepts/toolsets-system.md): 工具分组系统、递归解析、14+ 平台工具集
- [prompt-builder-architecture](concepts/prompt-builder-architecture.md): 系统提示模块化组装，注入防护+技能缓存+模型特定指导
- [auxiliary-client-architecture](concepts/auxiliary-client-architecture.md): 辅助 LLM 客户端路由器，多 provider 解析链+自动降级

### 记忆与会话

- [memory-system-architecture](concepts/memory-system-architecture.md): 三层架构（MemoryStore/MemoryManager/MemoryProvider），冻结快照模式
- [session-search-and-sessiondb](concepts/session-search-and-sessiondb.md): FTS5 搜索 + LLM 摘要的跨会话回忆，orphan 删除策略
- [context-compressor-architecture](concepts/context-compressor-architecture.md): 自动上下文压缩，token-budget 尾部保护（min_tail=3），Session 分裂
- [skills-and-memory-interaction](concepts/skills-and-memory-interaction.md): Skills 与 Memory 的互补关系和决策树
- [skills-system-architecture](concepts/skills-system-architecture.md): 渐进式披露架构，技能发现、条件激活、密钥管理

### 工具与能力

- [browser-tool-architecture](concepts/browser-tool-architecture.md): 多后端浏览器自动化，accessibility tree+三层安全防护
- [web-tools-architecture](concepts/web-tools-architecture.md): 多后端搜索/提取/爬取，LLM 智能内容压缩
- [code-execution-sandbox](concepts/code-execution-sandbox.md): execute_code 沙箱，7 工具限制+UDS/File RPC 两种通信模式
- [voice-mode-architecture](concepts/voice-mode-architecture.md): Push-to-talk 语音交互，STT（3 Provider）+ TTS（5 Provider）
- [context-references](concepts/context-references.md): @file/@folder/@diff/@url/@git 引用系统，安全沙箱+注入量限制
- [fuzzy-matching-engine](concepts/fuzzy-matching-engine.md): 8 策略链模糊匹配，从精确到相似度匹配
- [large-tool-result-handling](concepts/large-tool-result-handling.md): 三层溢出防护（工具内截断/单结果持久化/轮次聚合预算）

### 性能与优化

- [parallel-tool-execution](concepts/parallel-tool-execution.md): 智能并发安全检测，三层分类+路径冲突检测
- [prompt-caching-optimization](concepts/prompt-caching-optimization.md): 冻结快照保护 prefix cache，75% 成本节省
- [smart-model-routing](concepts/smart-model-routing.md): 智能模型路由，短消息走便宜模型

### 安全与可靠性

- [security-defense-system](concepts/security-defense-system.md): 多层防御体系 + 危险命令审批系统（manual/smart/off 三模式）
- [interrupt-and-fault-tolerance](concepts/interrupt-and-fault-tolerance.md): 中断传播、结构化错误分类（error_classifier）、Fallback 模型链
- [credential-pool-and-isolation](concepts/credential-pool-and-isolation.md): 多密钥自动轮换、4 种选池策略、Profile 隔离

### 多 Agent

- [multi-agent-architecture](concepts/multi-agent-architecture.md): 4 种运行时机制（delegate_task/MoA/Background Review/send_message）
- [configuration-and-profiles](concepts/configuration-and-profiles.md): 多 Profile 架构，完全隔离的 agent 实例（第二种多 Agent 方案）

### 平台与扩展

- [cli-architecture](concepts/cli-architecture.md): CLI 架构、斜杠命令、hermes dump
- [terminal-backends](concepts/terminal-backends.md): 6 种终端后端、统一 spawn-per-call 执行模型
- [messaging-gateway-architecture](concepts/messaging-gateway-architecture.md): 15 平台统一网关（含 BlueBubbles/iMessage）
- [gateway-session-management](concepts/gateway-session-management.md): 网关会话管理，多平台会话隔离+PII 脱敏+重置策略
- [hook-system-architecture](concepts/hook-system-architecture.md): 双 Hook 系统（Gateway Hooks + Plugin System）
- [mcp-and-plugins](concepts/mcp-and-plugins.md): MCP 集成、插件钩子系统、OAuth 支持
- [skin-engine](concepts/skin-engine.md): YAML 驱动的皮肤/主题系统
- [worktree-isolation](concepts/worktree-isolation.md): Git Worktree 并行隔离模式
- [cron-scheduling](concepts/cron-scheduling.md): 内置调度器、自然语言调度、多平台投递
- [trajectory-and-data-generation](concepts/trajectory-and-data-generation.md): 轨迹保存、批量运行器、RL 训练环境

### 更新日志

- [2026-04-09-update](changelog/2026-04-09-update.md): 59 commits，结构化错误分类、统一执行层、三层溢出防护、BlueBubbles 等

---

## 统计信息

- **概念页面**: 36 个
- **更新日志**: 1 个
- **源码覆盖**: 关键模块逐行验证
- **最后更新**: 2026-04-10


## 使用方式

- **GitHub 在线浏览**: 直接点击上方目录链接
- **Obsidian 本地知识库**: 
  ```bash
  git clone https://github.com/cclank/Hermes-Wiki.git ~/Hermes-Wiki
  ```
- **配合 Hermes Agent**: 在 config.yaml 中设置 `skills.config.wiki.path: ~/Hermes-Wiki`


---

*本文档基于 Hermes Agent 源码分析生成。*
