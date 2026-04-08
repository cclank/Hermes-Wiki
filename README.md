# 📘 Hermes Agent Architecture Wiki

[![Wiki](https://img.shields.io/badge/Wiki-Hermes_Agent-blue?style=for-the-badge&logo=markdown)](https://github.com/cclank/Hermes-Wiki)
[![Source](https://img.shields.io/badge/Source-hermes--agent-green?style=for-the-badge&logo=github)](https://github.com/NousResearch/hermes-agent)
[![Knowledge Base](https://img.shields.io/badge/Knowledge_Base-37_pages-orange?style=for-the-badge)](https://github.com/cclank/Hermes-Wiki)
[![Verified](https://img.shields.io/badge/Verified-Source_Code-brightgreen?style=for-the-badge)](https://github.com/cclank/Hermes-Wiki)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](https://opensource.org/licenses/MIT)

> 基于 Nous Research [Hermes Agent](https://github.com/NousResearch/hermes-agent) 源码的深度架构文档。
> 所有页面均经过**逐行源码验证**，确保准确性与时效性。

---

## 🗂️ 目录结构

### Entities\n\n- **[[aiagent-class]]** — 核心对话循环类，管理 LLM 交互和工具调用\n- **[[memorystore-class]]** — 记忆系统核心类，管理 MEMORY.md 和 USER.md\n\n### Concepts\n\n- **[[tool-registry-architecture]]** — 中央工具注册系统，声明式注册+集中调度，循环导入安全\n- **[[auxiliary-client-architecture]]** — 辅助 LLM 客户端路由器，多 provider 解析链+适配器模式+自动降级\n- **[[browser-tool-architecture]]** — 多后端浏览器自动化，accessibility tree 文本表示+三层安全防护+并发隔离\n- **[[web-tools-architecture]]** — 多后端搜索/提取/爬取，LLM 智能内容压缩（分块+合成），四层安全防护\n- **[[skills-system-architecture]]** — 渐进式披露架构，技能发现、条件激活、密钥管理\n- **[[memory-system-architecture]]** — 冻结快照模式、原子写入、安全扫描\n- **[[agent-loop-and-prompt-assembly]]** — Agent 循环、系统提示构建、平台提示、执行指导\n- **[[skills-and-memory-interaction]]** — Skills 与 Memory 的互补关系和决策树\n- **[[toolsets-system]]** — 工具分组系统、递归解析、14+ 平台工具集\n- **[[session-search-and-sessiondb]]** — FTS5 搜索 + LLM 摘要的跨会话回忆\n- **[[parallel-tool-execution]]** — 智能并发安全检测，三层分类 + 路径冲突检测\n- **[[prompt-caching-optimization]]** — Anthropic system_and_3 缓存策略，75% 成本节省\n- **[[fuzzy-matching-engine]]** — 8 策略链模糊匹配，从精确到相似度匹配\n- **[[smart-model-routing]]** — 智能模型路由，10级上下文长度解析链+本地服务器自动探测\n- **[[model-metadata-and-routing]]** — 模型元数据缓存、提供商路由、定价估算\n- **[[large-tool-result-handling]]** — 大型结果文件化、预飞行压缩、Surrogate 清理\n- **[[security-defense-system]]** — 5 层防御体系，100+ 威胁模式检测\n- **[[interrupt-and-fault-tolerance]]** — 中断传播、凭证池轮换、Fallback 模型链\n- **[[credential-pool-and-isolation]]** — 多密钥自动轮换、Profile 隔离\n- **[[multi-agent-architecture]]** — 多 Agent 体系，子代理委派+批量处理+跨平台通信\n- **[[iteration-budget-and-delegation]]** — 迭代预算、子代理委派、并行任务\n- **[[cli-architecture]]** — CLI 架构、斜杠命令补全、Skin 引擎\n- **[[gateway-multi-platform]]** — 14+ 平台统一网关、会话共享、服务管理\n- **[[configuration-and-profiles]]** — 分层配置、Profile 隔离、自动迁移\n- **[[hook-system-architecture]]** — Hook 系统（Gateway Hooks + Plugin System），事件驱动+工具注册+上下文注入\n- **[[mcp-and-plugins]]** — MCP 集成、插件钩子系统、OAuth 支持\n- **[[terminal-backends]]** — 6 种终端后端、环境抽象、持久化 Shell\n- **[[cron-scheduling]]** — 内置调度器、自然语言调度、多平台投递\n- **[[trajectory-and-data-generation]]** — 轨迹保存、批量运行器、RL 训练环境\n- **[[prompt-builder-architecture]]** — 系统提示模块化组装，注入防护+技能缓存+模型特定指导\n- **[[context-compressor-architecture]]** — 自动上下文压缩，结构化摘要+迭代更新+工具对完整性保障\n- **[[context-compression]]** — 自动上下文压缩、摘要生成、阈值控制\n- **[[model-tools-dispatch]]** — 工具编排与调度，异步桥接+动态 schema 调整+参数类型强制\n- **[[gateway-session-management]]** — 网关会话管理，多平台会话隔离+PII 脱敏+重置策略\n- **[[messaging-gateway-architecture]]** — 消息网关架构、平台适配器、DM 配对\n\n
---

## 🛠️ 使用方式

### 1. GitHub 在线浏览
直接点击上方的目录链接，或通过侧边栏浏览文件树。

### 2. Obsidian 本地知识库
克隆本仓库即可作为 Obsidian Vault 使用：
```bash
git clone https://github.com/cclank/Hermes-Wiki.git ~/Hermes-Wiki
```
- 打开 Obsidian → Open folder as vault → 选择 `~/Hermes-Wiki`
- 所有 `[[wikilinks]]` 均可直接点击跳转
- 支持 Graph View 查看知识图谱

### 3. 配合 Hermes Agent 使用
Hermes Agent 内置 `llm-wiki` 技能，可直接引用本文档内容：
```yaml
# config.yaml
skills:
  config:
    wiki:
      path: ~/Hermes-Wiki
```

---

## 📊 统计信息

- **总页面数**: 37
- **核心模块**: 9 个
- **源码覆盖**: 4753+ 行关键代码分析
- **最后更新**: 2026-04-08

---

## 📝 更新日志

- **2026-04-08**: 新增 Smart Model Routing、Hook System、Prompt Caching
- **2026-04-07**: 初始化 Wiki，覆盖 Core、Agent、Gateway 等核心架构

---

## 🙏 致谢

- **Nous Research** — 开发 Hermes Agent
- **Models.dev** — 提供 4000+ 模型数据库
- **Karpathy's LLM Wiki** — 提供知识库架构范式

---

*本文档由 Hermes Agent 自动生成并维护。*
