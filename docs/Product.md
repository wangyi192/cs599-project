# Chaos-Tuner Agent Product Spec

## 1. 产品概述

Chaos-Tuner Agent 是一个面向高并发秒杀系统的智能演练与调优原型项目。系统通过模拟秒杀流量、采集运行指标、识别异常日志，并调用云端大模型 API 生成优化建议，形成一个可重复执行的多智能体闭环。

本项目采用 SDD（Specification-Driven Development，规格驱动开发）方式推进：先定义产品目标、用户场景、功能边界与验收标准，再将规格映射到目标靶机、MCP Server、LangGraph 多智能体工作流与容器化工程配置。

## 2. 项目背景

秒杀、抢券、限量发售等业务常见于电商、票务、游戏和营销活动中。这类系统在短时间内承受突发并发请求，容易触发以下问题：

- 热点库存 Key 被集中访问，Redis QPS 激增。
- 扣减库存缺乏原子性，导致 oversell（超卖）。
- 数据库连接池、行锁或事务等待被放大，导致 deadlock（死锁）或拥堵。
- 压测、监控、诊断、调优建议之间缺少统一闭环。

Chaos-Tuner Agent 的目标不是替代真实生产压测平台，而是提供一个课程项目级、可运行、可解释的演示系统，用于展示 Agentic AI、MCP、LangGraph 和云端大模型 API 如何协同完成高并发系统的智能演练。

## 3. 目标用户

- 后端研发工程师：关注库存扣减正确性、吞吐、并发异常与调优策略。
- SRE / 稳定性工程师：关注压测闭环、异常检测和演练报告。
- 架构师 / 技术负责人：关注高并发链路中的缓存、队列、数据库和连接池边界。
- AI Native 开发学习者：关注 MCP 工具调用、多智能体协作和 LangGraph 状态机建模。

## 4. 产品目标

1. 提供一个简易秒杀靶机，能根据并发量输出正常 TPS，并在并发过高时产生 oversell 或 deadlock 日志。
2. 提供一个 MCP Server，暴露标准工具接口，让 Agent 通过工具协议获取 Redis QPS 与系统日志。
3. 提供一个多智能体闭环：Chaos Agent 生成压测指令，Monitor Agent 采集指标并判断异常，Tuner Agent 基于异常日志输出调优建议。
4. 使用云端大模型 API，并通过 OpenAI 兼容接口接入 LangChain，不依赖本地 Ollama 或高端 GPU。
5. 所有敏感配置通过 `.env` 管理，不在代码中硬编码 API Key。

## 5. 功能需求

### 5.1 秒杀演练

- 支持输入并发量、库存量和演练轮次。
- 在正常并发下生成稳定 TPS 数据。
- 在高并发下模拟 Redis 热点 Key 压力。
- 在并发超过阈值时产生 oversell 或 deadlock 日志。
- 输出每轮演练的 TPS、成功订单数、失败请求数和异常日志。

### 5.2 MCP 工具

MCP Server 必须暴露以下工具：

- `get_redis_qps()`：返回当前或最近一次演练中的 Redis QPS、TPS、并发量等指标。
- `get_system_logs()`：返回最近一次演练产生的系统日志，包括 oversell、deadlock 或正常运行日志。

工具接口用于隔离 Agent 与底层靶机实现。未来替换为 Prometheus、Redis、ELK 或数据库观测工具时，Agent 工作流无需大幅调整。

### 5.3 多智能体协作

- Chaos Agent 负责生成压测配置，例如并发量、库存量、持续时间和风险假设。
- Monitor Agent 负责调用 MCP 工具，解析 TPS、Redis QPS 和异常日志，判断是否出现超卖或拥堵。
- Tuner Agent 负责接收异常上下文，并使用云端大模型 API 生成调优建议。
- LangGraph 负责将上述节点编排为“压测 -> 监控 -> 异常调优 -> 重新压测”的闭环。

### 5.4 调优建议

调优建议需要尽量结构化，并包含：

- 异常类型：oversell、deadlock、hot_key、connection_pool_saturation 等。
- 风险等级：LOW、MEDIUM、HIGH、CRITICAL。
- 根因分析：基于日志和指标解释判断依据。
- 建议动作：例如引入 Redis Lua 脚本保证原子扣减、增加令牌桶限流、调整数据库连接池大小、缩短事务范围、增加库存分片。
- 验证方式：下一轮压测应观察哪些指标是否改善。

## 6. 非功能需求

- 可运行性：在本地 Python 环境和 Docker Compose 环境中均可运行。
- 可解释性：每条调优建议都应能关联到指标或日志证据。
- 可扩展性：MCP 工具、Agent 节点和靶机模拟器应保持松耦合。
- 安全性：API Key 必须通过 `.env` 注入，`.env` 不应提交到版本库。
- 教学友好：目录结构清晰，文档能够说明从规格到实现的映射关系。

## 7. 技术约束

- 编程语言：Python 3.10+。
- 多智能体编排：LangGraph。
- LLM 接入：`langchain-openai`，使用 OpenAI 兼容云端 API。
- 可选模型服务：DeepSeek API、通义千问 DashScope 兼容模式，或其他 OpenAI 兼容服务。
- 工具协议：官方 MCP Python SDK。
- 容器化：Docker 与 Docker Compose。
- 缓存服务：Redis，用于工程环境预留与后续扩展。

## 8. 验收标准

Phase 1 验收标准：

- `docs/Product_Spec.md` 描述产品背景、目标用户、功能需求、非功能需求和验收标准。
- `docs/Architecture_Spec.md` 描述组件、数据流、状态机、MCP 工具边界和部署形态。
- `README.md` 描述项目背景、技术栈、目录结构和启动说明。
- 所有文档均移除本地 Ollama、RTX 4090D 或硬编码 API Key 的设定。

整体项目验收标准：

- 可以运行一次完整闭环：Chaos -> Monitor -> Tuner -> 重新压测或结束。
- 在模拟 oversell 或 deadlock 时，Monitor Agent 能识别异常。
- Tuner Agent 能输出与异常类型匹配的优化建议。
- Docker Compose 能启动 Python 应用和 Redis 实例。
