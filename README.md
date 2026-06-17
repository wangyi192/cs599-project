# Chaos-Tuner Agent

## 项目简介
Chaos-Tuner Agent 是一个面向高并发秒杀系统的智能演练与调优项目，用多智能体闭环模拟压测、监控和调优，帮助定位超卖、死锁、热点 Key 和连接池拥堵等问题。

## 方向
方向二：企业级应用软件的 Agent 改造

## 技术栈
- AI IDE: Trae CN
- LLM: 阿里云通义千问 DashScope OpenAI 兼容 API
- 框架: LangGraph, LangChain, MCP
- 容器: Docker, Docker Compose
- 语言: Python 3.10+
- 依赖: pydantic, python-dotenv, redis

## 目录结构
- `src/agent/`：多智能体编排逻辑，包含大模型配置、Agent 节点和 LangGraph 状态机。
- `src/mcp_server/`：MCP 工具服务器，提供 `get_redis_qps()` 和 `get_system_logs()`。
- `src/target_system/`：简易秒杀靶机模拟器，生成 TPS、Redis QPS、成功订单、失败请求和异常日志。
- `docs/`：产品规格与架构规格文档。
- 根目录：工程配置文件，包括 `Dockerfile`、`docker-compose.yml`、`requirements.txt`、`.env.example`。

## 环境搭建
1. 依赖安装
   ```powershell
   cd E:\cs599-project
   conda activate cs599_env
   pip install -r requirements.txt
   ```

2. 环境变量配置（⚠️ 不硬编码 API Key）
   复制 `.env.example` 为 `.env`，然后把你的阿里云通义千问 DashScope API Key 填进去：
   ```env
   ENABLE_LLM=true
   OPENAI_API_KEY=你的DashScope密钥
   OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
   OPENAI_MODEL=qwen-plus
   ```

3. 启动步骤
   ```powershell
   cd E:\cs599-project
   conda activate cs599_env
   python -m src.agent.graph
   ```

   如果 PowerShell 里 `conda activate` 不可用：
   ```powershell
   cd E:\cs599-project
   conda run -n cs599_env python -m src.agent.graph
   ```

   Docker 方式：
   ```powershell
   cd E:\cs599-project
   docker compose up --build
   ```

## 项目状态
- [x] Proposal
- [x] MVP
- [ ] Final

## 项目背景
秒杀系统在短时间内承受大量并发请求，常见风险包括 Redis 热点 Key 过载、库存扣减非原子导致超卖、数据库锁等待放大、连接池耗尽和重试风暴。传统排查通常依赖人工观察压测结果、日志和监控指标，反馈链路较长。

本项目希望用 Agentic AI 的方式演示一个更自动化的闭环：Chaos Agent 生成压测指令，Monitor Agent 调用 MCP 工具获取指标和日志，Tuner Agent 基于异常上下文生成优化建议。

## 文档
- `docs/Product_Spec.md`：产品规格，描述背景、用户、目标、功能需求、非功能需求和验收标准。
- `docs/Architecture_Spec.md`：架构规格，描述组件职责、状态模型、LangGraph 状态机、MCP 工具边界和部署视图。

## SDD 映射关系
1. 产品规格定义问题背景、目标用户、功能需求和验收标准。
2. 架构规格定义组件边界、状态机、MCP 工具协议和部署模型。
3. 源码实现按规格拆分为 `target_system`、`mcp_server` 和 `agent` 三层。
4. 容器化配置提供可复现运行环境。
