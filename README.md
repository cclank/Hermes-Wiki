# 📘 Hermes Agent Architecture Wiki

<p align="center">
  <img src="https://img.shields.io/badge/Wiki-Hermes_Agent-blue?style=for-the-badge&logo=markdown" alt="Wiki" height="28">
  <img src="https://img.shields.io/badge/Source-hermes--agent-green?style=for-the-badge&logo=github" alt="Source" height="28">
  <img src="https://img.shields.io/badge/Knowledge_Base-37_pages-orange?style=for-the-badge" alt="Knowledge Base" height="28">
  <img src="https://img.shields.io/badge/Verified-Source_Code-brightgreen?style=for-the-badge" alt="Verified" height="28">
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge" alt="License" height="28">
</p>

> 基于 Nous Research [Hermes Agent](https://github.com/NousResearch/hermes-agent) 源码的深度架构文档。
> 所有页面均经过**逐行源码验证**，确保准确性与时效性。


---

## 🗂️ 目录结构
### 核心架构

- [tool-registry-architecture](concepts/tool-registry-architecture.md): 中央工具注册系统，声明式注册+集中调度，循环导入安全
- [auxiliary-client-architecture](concepts/auxiliary-client-architecture.md): 辅助 LLM 客户端路由器，多 provider 解析链+适配器模式+自动降级
- [browser-tool-architecture](concepts/browser-tool-architecture.md): 多后端浏览器自动化，accessibility tree 文本表示+三层安全防护+并发隔离
- [web-tools-architecture](concepts/web-tools-architecture.md): 多后端搜索/提取/爬取，LLM 智能内容压缩（分块+合成），四层安全防护
- [skills-system-architecture](concepts/skills-system-architecture.md): 渐进式披露架构，技能发现、条件激活、密钥管理
- [memory-system-architecture](concepts/memory-system-architecture.md): 冻结快照模式、原子写入、安全扫描
- [agent-loop-and-prompt-assembly](concepts/agent-loop-and-prompt-assembly.md): Agent 循环、系统提示构建、平台提示、执行指导
- [skills-and-memory-interaction](concepts/skills-and-memory-interaction.md): Skills 与 Memory 的互补关系和决策树
- [toolsets-system](concepts/toolsets-system.md): 工具分组系统、递归解析、14+ 平台工具集
- [session-search-and-sessiondb](concepts/session-search-and-sessiondb.md): FTS5 搜索 + LLM 摘要的跨会话回忆

### 性能与优化

- [parallel-tool-execution](concepts/parallel-tool-execution.md): 智能并发安全检测，三层分类 + 路径冲突检测
- [prompt-caching-optimization](concepts/prompt-caching-optimization.md): Anthropic system_and_3 缓存策略，75% 成本节省
- [fuzzy-matching-engine](concepts/fuzzy-matching-engine.md): 8 策略链模糊匹配，从精确到相似度匹配
- [smart-model-routing](concepts/smart-model-routing.md): 智能模型路由，10级上下文长度解析链+本地服务器自动探测
- [model-metadata-and-routing](concepts/model-metadata-and-routing.md): 模型元数据缓存、提供商路由、定价估算
- [large-tool-result-handling](concepts/large-tool-result-handling.md): 大型结果文件化、预飞行压缩、Surrogate 清理

### 安全与可靠性

- [security-defense-system](concepts/security-defense-system.md): 5 层防御体系，100+ 威胁模式检测
- [interrupt-and-fault-tolerance](concepts/interrupt-and-fault-tolerance.md): 中断传播、凭证池轮换、Fallback 模型链
- [credential-pool-and-isolation](concepts/credential-pool-and-isolation.md): 多密钥自动轮换、Profile 隔离
- [multi-agent-architecture](concepts/multi-agent-architecture.md): 多 Agent 体系，子代理委派+批量处理+跨平台通信
- [iteration-budget-and-delegation](concepts/iteration-budget-and-delegation.md): 迭代预算、子代理委派、并行任务

### 平台与扩展

- [cli-architecture](concepts/cli-architecture.md): CLI 架构、斜杠命令补全、Skin 引擎
- [gateway-multi-platform](concepts/gateway-multi-platform.md): 14+ 平台统一网关、会话共享、服务管理
- [configuration-and-profiles](concepts/configuration-and-profiles.md): 分层配置、Profile 隔离、自动迁移
- [hook-system-architecture](concepts/hook-system-architecture.md): Hook 系统（Gateway Hooks + Plugin System），事件驱动+工具注册+上下文注入
- [mcp-and-plugins](concepts/mcp-and-plugins.md): MCP 集成、插件钩子系统、OAuth 支持
- [terminal-backends](concepts/terminal-backends.md): 6 种终端后端、环境抽象、持久化 Shell
- [cron-scheduling](concepts/cron-scheduling.md): 内置调度器、自然语言调度、多平台投递
- [trajectory-and-data-generation](concepts/trajectory-and-data-generation.md): 轨迹保存、批量运行器、RL 训练环境
- [prompt-builder-architecture](concepts/prompt-builder-architecture.md): 系统提示模块化组装，注入防护+技能缓存+模型特定指导
- [context-compressor-architecture](concepts/context-compressor-architecture.md): 自动上下文压缩，结构化摘要+迭代更新+工具对完整性保障
- [context-compression](concepts/context-compression.md): 自动上下文压缩、摘要生成、阈值控制
- [model-tools-dispatch](concepts/model-tools-dispatch.md): 工具编排与调度，异步桥接+动态 schema 调整+参数类型强制
- [gateway-session-management](concepts/gateway-session-management.md): 网关会话管理，多平台会话隔离+PII 脱敏+重置策略
- [messaging-gateway-architecture](concepts/messaging-gateway-architecture.md): 消息网关架构、平台适配器、DM 配对


---

## 📊 统计信息

- **总页面数**: 37
- **核心模块**: 9 个
- **源码覆盖**: 4753+ 行关键代码分析
- **最后更新**: 2026-04-08


## 🛠️ 使用方式

- **GitHub 在线浏览**: 直接点击上方目录链接
- **Obsidian 本地知识库**: 
  ```bash
  git clone https://github.com/cclank/Hermes-Wiki.git ~/Hermes-Wiki
  ```
- **配合 Hermes Agent**: 在 config.yaml 中设置 `skills.config.wiki.path: ~/Hermes-Wiki`


---

*本文档由 Hermes Agent 自动生成并维护。*