# Wiki Index

> 内容目录。每个 wiki 页面按类型列出，附一行摘要。
> 查询前先读此文件找到相关页面。
> Last updated: 2026-05-02 | Total pages: 40 | Tracking: v0.12.0 (v2026.4.30)

## Entities

- [[aiagent-class]] — 核心对话循环类，管理 LLM 交互和工具调用
- [[memorystore-class]] — 记忆系统核心类，管理 MEMORY.md 和 USER.md

## Concepts

### 核心架构
- [[tool-registry-architecture]] — 中央工具注册系统，声明式注册+集中调度，循环导入安全
- [[auxiliary-client-architecture]] — 辅助 LLM 客户端路由器，多 provider 解析链+适配器模式+自动降级
- [[browser-tool-architecture]] — 多后端浏览器自动化，accessibility tree 文本表示+三层安全防护+并发隔离
- [[web-tools-architecture]] — 多后端搜索/提取/爬取，LLM 智能内容压缩（分块+合成），四层安全防护
- [[skills-system-architecture]] — 渐进式披露架构，技能发现、条件激活、密钥管理
- [[memory-system-architecture]] — 冻结快照模式、原子写入、安全扫描
- [[agent-loop-and-prompt-assembly]] — Agent 循环、系统提示构建、平台提示、执行指导
- [[skills-and-memory-interaction]] — Skills 与 Memory 的互补关系和决策树
- [[toolsets-system]] — 工具分组系统、递归解析、14+ 平台工具集
- [[session-search-and-sessiondb]] — FTS5 搜索 + LLM 摘要的跨会话回忆

### 性能与优化
- [[parallel-tool-execution]] — 智能并发安全检测，三层分类 + 路径冲突检测
- [[prompt-caching-optimization]] — Anthropic system_and_3 缓存策略，75% 成本节省
- [[fuzzy-matching-engine]] — 8 策略链模糊匹配，从精确到相似度匹配
- [[smart-model-routing]] — 智能模型路由，10级上下文长度解析链+本地服务器自动探测
- [[large-tool-result-handling]] — 大型结果文件化、预飞行压缩、Surrogate 清理

### 安全与可靠性
- [[security-defense-system]] — 5 层防御体系，100+ 威胁模式检测
- [[interrupt-and-fault-tolerance]] — 中断传播、凭证池轮换、Fallback 模型链
- [[tool-loop-guardrails]] — 工具调用循环守护（v0.12.0），exact/same-tool/idempotent 三维检测，warn/block/halt 决策
- [[credential-pool-and-isolation]] — 多密钥自动轮换、Profile 隔离
- [[multi-agent-architecture]] — 多 Agent 体系，子代理委派+批量处理+跨平台通信
- [[kanban-multi-profile-board]] — Kanban 跨 profile 协作板（v0.12.0），SQLite WAL+CAS、worker tools、dashboard 插件
- [[persistent-goals-ralph-loop]] — `/goal` Ralph 循环（v0.12.0），辅助模型 judge + SessionDB 持久化 + 不动系统提示

### 平台与扩展
- [[cli-architecture]] — CLI 架构、斜杠命令补全、Skin 引擎
- [[configuration-and-profiles]] — 分层配置、Profile 隔离、自动迁移
- [[hook-system-architecture]] — Hook 系统（Gateway Hooks + Plugin System），事件驱动+工具注册+上下文注入
- [[mcp-and-plugins]] — MCP 集成、插件钩子系统、OAuth 支持
- [[terminal-backends]] — 6 种终端后端、环境抽象、持久化 Shell
- [[cron-scheduling]] — 内置调度器、自然语言调度、多平台投递
- [[trajectory-and-data-generation]] — 轨迹保存、批量运行器、RL 训练环境
- [[prompt-builder-architecture]] — 系统提示模块化组装，注入防护+技能缓存+模型特定指导
- [[context-compressor-architecture]] — 自动上下文压缩，结构化摘要+迭代更新+工具对完整性保障
- [[model-tools-dispatch]] — 工具编排与调度，异步桥接+动态 schema 调整+参数类型强制
- [[gateway-session-management]] — 网关会话管理，多平台会话隔离+PII 脱敏+重置策略
- [[messaging-gateway-architecture]] — 消息网关架构、平台适配器、DM 配对

