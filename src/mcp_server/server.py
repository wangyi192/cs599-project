"""Chaos-Tuner Agent 的 MCP Server。

本模块使用官方 ``mcp`` Python SDK 中的 ``FastMCP`` 实现两个工具：

1. ``get_redis_qps()``：返回 FlashSaleSimulator 最近一次演练的 QPS/TPS 指标。
2. ``get_system_logs()``：返回 FlashSaleSimulator 最近一次演练产生的系统日志。

默认启动方式为 stdio，便于后续被 LangChain / LangGraph / MCP Client 以
子进程方式连接。也可以通过环境变量 ``MCP_TRANSPORT`` 切换为其他传输方式。
"""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from src.target_system.flash_sale import default_simulator


# FastMCP 是官方 MCP SDK 提供的便捷封装。这里的名字会出现在客户端工具列表中。
mcp = FastMCP("chaos-tuner-monitoring")


@mcp.tool()
def get_redis_qps(
    concurrency: int = 500,
    inventory: int = 800,
    duration_seconds: int = 10,
    run_new_round: bool = True,
) -> dict[str, Any]:
    """获取 Redis QPS / TPS 指标快照。

    参数说明：
    - ``concurrency``：模拟压测并发量，默认 500。
    - ``inventory``：模拟库存量，默认 800。
    - ``duration_seconds``：模拟压测持续时间，默认 10 秒。
    - ``run_new_round``：是否先执行一轮新的秒杀模拟。

    返回内容：
    - ``redis_qps``：模拟 Redis 每秒请求数。
    - ``tps``：业务侧每秒成功订单数。
    - ``success_orders``：成功订单数。
    - ``failed_requests``：失败请求数。
    - ``anomaly_type``：异常类型，可能为 none、oversell 或 deadlock。

    设计上，这个工具既可以在 Chaos Agent 生成新压测参数后触发新一轮模拟，
    也可以在 Monitor Agent 中只读取最新快照。
    """

    if run_new_round:
        default_simulator.run(
            concurrency=concurrency,
            inventory=inventory,
            duration_seconds=duration_seconds,
        )

    metrics = default_simulator.get_latest_metrics()
    return {
        "status": "ok",
        "source": "FlashSaleSimulator",
        "metrics": metrics,
    }


@mcp.tool()
def get_system_logs(limit: int = 20) -> dict[str, Any]:
    """获取秒杀模拟器最近一次运行产生的系统日志。

    参数说明：
    - ``limit``：最多返回多少条日志。小于等于 0 时返回全部日志。

    返回内容：
    - ``logs``：日志字符串列表。
    - ``has_oversell``：日志中是否包含 oversell。
    - ``has_deadlock``：日志中是否包含 deadlock。
    - ``latest_anomaly``：根据日志推断出的最近异常类型。
    """

    logs = default_simulator.get_logs(limit=limit)
    normalized_logs = [line.lower() for line in logs]
    has_oversell = any("oversell" in line for line in normalized_logs)
    has_deadlock = any("deadlock" in line for line in normalized_logs)

    if has_oversell:
        latest_anomaly = "oversell"
    elif has_deadlock:
        latest_anomaly = "deadlock"
    else:
        latest_anomaly = "none"

    return {
        "status": "ok",
        "source": "FlashSaleSimulator",
        "logs": logs,
        "has_oversell": has_oversell,
        "has_deadlock": has_deadlock,
        "latest_anomaly": latest_anomaly,
    }


if __name__ == "__main__":
    # MCP 客户端最常见的本地集成方式是 stdio，因此这里默认使用 stdio。
    # 如果后续需要调试 SSE，可设置环境变量：MCP_TRANSPORT=sse。
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)
