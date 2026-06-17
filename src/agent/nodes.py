"""LangGraph 多智能体节点实现。

本文件实现 Phase 3 的三个核心角色：

1. Chaos Agent：生成并发压测配置。
2. Monitor Agent：直接调用 MCP Server 中的工具函数获取指标和日志。
3. Tuner Agent：把异常上下文交给大模型或 MockLLM，生成调优建议。

为了让课程演示尽量简单，本阶段不启动独立 MCP 子进程，而是在 Monitor 节点
中直接导入 ``src.mcp_server.server`` 中的工具函数。这仍然保留了工具边界，
后续可以替换为真正的 MCP Client 调用。
"""

from __future__ import annotations

import json
from typing import Any, TypedDict

from src.agent.llm_config import get_chat_model
from src.mcp_server.server import get_redis_qps, get_system_logs


class State(TypedDict, total=False):
    """LangGraph 工作流状态。

    字段含义：
    - ``round_id``：当前演练轮次。
    - ``max_rounds``：最大演练轮次。
    - ``chaos_profile``：本轮压测配置。
    - ``metrics``：Monitor Agent 获取到的指标。
    - ``logs``：Monitor Agent 获取到的日志列表。
    - ``anomaly_type``：异常类型，可能为 none、oversell 或 deadlock。
    - ``recommendations``：Tuner Agent 输出的调优建议。
    """

    round_id: int
    max_rounds: int
    chaos_profile: dict[str, Any]
    metrics: dict[str, Any]
    logs: list[str]
    anomaly_type: str
    recommendations: str


def chaos_node(state: State) -> State:
    """Chaos Agent：生成本轮压测配置。

    规则：
    - 第一轮使用较温和的并发 ``concurrency=500``，展示健康基线。
    - 如果上一轮发现异常，则继续使用高并发 ``concurrency=1500`` 进行复测。
    - 如果上一轮没有异常但仍有轮次预算，则主动提高并发到 1500，用于寻找边界。
    """

    current_round = int(state.get("round_id", 0)) + 1
    previous_anomaly = state.get("anomaly_type", "none")

    if current_round == 1:
        concurrency = 1500
    elif previous_anomaly != "none":
        concurrency = 1500
    else:
        concurrency = 1500

    chaos_profile = {
        "concurrency": concurrency,
        "inventory": 800,
        "duration_seconds": 10,
    }

    print(f"\n[Chaos Agent] 第 {current_round} 轮压测配置: {chaos_profile}")

    return {
        **state,
        "round_id": current_round,
        "chaos_profile": chaos_profile,
    }


def monitor_node(state: State) -> State:
    """Monitor Agent：调用 MCP 工具获取指标和日志。

    这里直接调用 ``get_redis_qps`` 与 ``get_system_logs``。其中
    ``get_redis_qps`` 会根据 Chaos Agent 生成的参数触发一轮新的靶机模拟，
    ``get_system_logs`` 随后读取同一轮模拟产生的日志。
    """

    chaos_profile = state.get("chaos_profile", {})
    metrics_response = get_redis_qps(
        concurrency=int(chaos_profile.get("concurrency", 500)),
        inventory=int(chaos_profile.get("inventory", 800)),
        duration_seconds=int(chaos_profile.get("duration_seconds", 10)),
        run_new_round=True,
    )
    logs_response = get_system_logs(limit=20)

    metrics = dict(metrics_response.get("metrics", {}))
    logs = list(logs_response.get("logs", []))

    anomaly_type = str(
        metrics.get("anomaly_type")
        or logs_response.get("latest_anomaly")
        or "none"
    )

    # 如果指标未标记异常，但日志中出现关键字，也要提升异常类型。
    lower_logs = "\n".join(logs).lower()
    if anomaly_type == "none":
        if "oversell" in lower_logs:
            anomaly_type = "oversell"
        elif "deadlock" in lower_logs:
            anomaly_type = "deadlock"

    print(
        "[Monitor Agent] 指标快照: "
        f"TPS={metrics.get('tps')}, Redis QPS={metrics.get('redis_qps')}, "
        f"失败请求={metrics.get('failed_requests')}, 异常={anomaly_type}"
    )
    for line in logs:
        print(f"[Monitor Agent] 日志: {line}")

    return {
        **state,
        "metrics": metrics,
        "logs": logs,
        "anomaly_type": anomaly_type,
    }


def tuner_node(state: State) -> State:
    """Tuner Agent：调用大模型或 MockLLM 生成调优建议。

    只有发现异常时才会进入该节点。Prompt 会包含本轮指标与日志，并要求模型
    以资深架构师身份输出排查路径和优化动作。
    """

    metrics = state.get("metrics", {})
    logs = state.get("logs", [])
    anomaly_type = state.get("anomaly_type", "none")

    prompt = f"""
你是一名资深高并发系统架构师。现在有一个秒杀系统压测闭环发现异常。

请基于以下信息输出排查和调优建议：

异常类型：
{anomaly_type}

指标 JSON：
{json.dumps(metrics, ensure_ascii=False, indent=2)}

系统日志：
{json.dumps(logs, ensure_ascii=False, indent=2)}

请重点覆盖：
1. 可能根因。
2. Redis 防超卖与原子扣减机制，例如 Lua 脚本。
3. 数据库连接池、事务范围、死锁和热点行锁优化。
4. 下一轮压测应验证的指标。
"""

    llm = get_chat_model()
    response = llm.invoke(prompt)
    recommendations = str(getattr(response, "content", response))

    print("[Tuner Agent] 调优建议:")
    print(recommendations)

    return {
        **state,
        "recommendations": recommendations,
    }


def route_after_monitor(state: State) -> str:
    """Monitor 后的条件路由。

    - 如果没有异常，结束工作流。
    - 如果出现 oversell 或 deadlock，进入 Tuner Agent。
    """

    if state.get("anomaly_type", "none") != "none":
        return "tuner"
    return "end"


def route_after_tuner(state: State) -> str:
    """Tuner 后的条件路由。

    - 如果当前轮次小于最大轮次，回到 Chaos Agent 重新压测。
    - 否则结束工作流。
    """

    round_id = int(state.get("round_id", 0))
    max_rounds = int(state.get("max_rounds", 1))
    if round_id < max_rounds:
        return "chaos"
    return "end"
