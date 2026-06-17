"""简易秒杀靶机模拟器。

本模块用于课程项目中的 Phase 2：目标靶机开发。它不会连接真实 Redis
或数据库，而是用可控的规则模拟高并发秒杀链路中的核心现象：

1. 正常并发下 TPS 随并发量上升，订单成功数受库存限制。
2. 并发过高时系统吞吐下降，失败请求数激增。
3. 高并发压力下生成 oversell（超卖）或 deadlock（死锁）日志。

后续 MCP Server 和 Monitor Agent 都可以读取该模拟器的最新快照。
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any


DEFAULT_SKU_ID = "sku:flash-sale-demo"
HIGH_CONCURRENCY_THRESHOLD = 1000


@dataclass
class FlashSaleResult:
    """单轮秒杀演练结果。

    使用 dataclass 是为了让字段含义更清晰，同时通过 ``to_dict`` 给 MCP
    工具返回普通字典，避免协议层依赖 Python 内部对象。
    """

    sku_id: str
    concurrency: int
    inventory: int
    duration_seconds: int
    request_count: int
    success_orders: int
    failed_requests: int
    tps: float
    redis_qps: float
    remaining_inventory: int
    oversold_units: int
    anomaly_type: str
    logs: list[str]
    timestamp: float

    def to_dict(self) -> dict[str, Any]:
        """转换为 MCP 和 Agent 更容易消费的普通字典。"""
        return {
            "sku_id": self.sku_id,
            "concurrency": self.concurrency,
            "inventory": self.inventory,
            "duration_seconds": self.duration_seconds,
            "request_count": self.request_count,
            "success_orders": self.success_orders,
            "failed_requests": self.failed_requests,
            "tps": self.tps,
            "redis_qps": self.redis_qps,
            "remaining_inventory": self.remaining_inventory,
            "oversold_units": self.oversold_units,
            "anomaly_type": self.anomaly_type,
            "logs": list(self.logs),
            "timestamp": self.timestamp,
        }


@dataclass
class FlashSaleSimulator:
    """简易 Flash Sale 秒杀模拟器。

    参数说明：
    - ``concurrency``：默认并发量，调用 ``run`` 时可以覆盖。
    - ``inventory``：默认库存量，调用 ``run`` 时可以覆盖。
    - ``duration_seconds``：默认压测持续时间，调用 ``run`` 时可以覆盖。
    - ``seed``：随机种子，使演示结果具备一定可复现性。

    设计原则：
    - 并发量 <= 1000 时视为合理范围，TPS 与成功订单较稳定。
    - 并发量 > 1000 时视为危险范围，模拟线程争抢、锁等待、重试风暴等现象。
    - 高并发异常会二选一生成 oversell 或 deadlock，也可能在极端情况下同时出现。
    """

    concurrency: int = 500
    inventory: int = 800
    duration_seconds: int = 10
    seed: int | None = 599
    sku_id: str = DEFAULT_SKU_ID
    latest_result: FlashSaleResult | None = field(default=None, init=False)
    system_logs: list[str] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        # 使用独立 Random 实例，避免污染其他模块的全局随机状态。
        self._random = random.Random(self.seed)

    def run(
        self,
        concurrency: int | None = None,
        inventory: int | None = None,
        duration_seconds: int | None = None,
    ) -> dict[str, Any]:
        """执行一轮秒杀模拟，并返回完整结果快照。

        MCP Server 的 ``get_redis_qps`` 会读取这里产生的最新指标，
        ``get_system_logs`` 会读取这里产生的日志。
        """

        current_concurrency = self._positive_int(
            concurrency if concurrency is not None else self.concurrency,
            fallback=self.concurrency,
        )
        current_inventory = self._non_negative_int(
            inventory if inventory is not None else self.inventory,
            fallback=self.inventory,
        )
        current_duration = self._positive_int(
            duration_seconds if duration_seconds is not None else self.duration_seconds,
            fallback=self.duration_seconds,
        )

        request_count = self._estimate_request_count(
            concurrency=current_concurrency,
            duration_seconds=current_duration,
        )
        is_overloaded = current_concurrency > HIGH_CONCURRENCY_THRESHOLD

        if is_overloaded:
            result = self._run_overloaded_case(
                concurrency=current_concurrency,
                inventory=current_inventory,
                duration_seconds=current_duration,
                request_count=request_count,
            )
        else:
            result = self._run_normal_case(
                concurrency=current_concurrency,
                inventory=current_inventory,
                duration_seconds=current_duration,
                request_count=request_count,
            )

        self.latest_result = result
        self.system_logs = list(result.logs)
        return result.to_dict()

    def get_latest_metrics(self) -> dict[str, Any]:
        """返回最近一次演练的指标。

        如果还没有任何演练，就先按默认参数自动执行一轮。这样 MCP 工具在
        冷启动时也能返回稳定结构的数据。
        """

        if self.latest_result is None:
            self.run()

        assert self.latest_result is not None
        result = self.latest_result
        return {
            "sku_id": result.sku_id,
            "concurrency": result.concurrency,
            "inventory": result.inventory,
            "duration_seconds": result.duration_seconds,
            "request_count": result.request_count,
            "success_orders": result.success_orders,
            "failed_requests": result.failed_requests,
            "tps": result.tps,
            "redis_qps": result.redis_qps,
            "remaining_inventory": result.remaining_inventory,
            "oversold_units": result.oversold_units,
            "anomaly_type": result.anomaly_type,
            "timestamp": result.timestamp,
        }

    def get_logs(self, limit: int | None = None) -> list[str]:
        """返回最近一次演练的系统日志。"""

        if self.latest_result is None:
            self.run()

        if limit is None or limit <= 0:
            return list(self.system_logs)
        return list(self.system_logs[-limit:])

    def _run_normal_case(
        self,
        concurrency: int,
        inventory: int,
        duration_seconds: int,
        request_count: int,
    ) -> FlashSaleResult:
        """模拟合理并发下的健康秒杀链路。"""

        # 正常情况下成功数主要受库存和请求量限制，失败请求来自库存售罄或少量抖动。
        natural_failures = int(request_count * self._random.uniform(0.01, 0.04))
        success_orders = min(inventory, max(0, request_count - natural_failures))
        failed_requests = max(0, request_count - success_orders)
        remaining_inventory = max(0, inventory - success_orders)

        # 合理并发时 TPS 接近请求吞吐，Redis QPS 略高于业务 TPS。
        tps = round(success_orders / duration_seconds, 2)
        redis_qps = round(tps * self._random.uniform(1.8, 2.6), 2)

        logs = [
            self._format_log(
                "INFO",
                "flash sale round finished normally; inventory deduction is consistent",
            )
        ]

        return FlashSaleResult(
            sku_id=self.sku_id,
            concurrency=concurrency,
            inventory=inventory,
            duration_seconds=duration_seconds,
            request_count=request_count,
            success_orders=success_orders,
            failed_requests=failed_requests,
            tps=tps,
            redis_qps=redis_qps,
            remaining_inventory=remaining_inventory,
            oversold_units=0,
            anomaly_type="none",
            logs=logs,
            timestamp=time.time(),
        )

    def _run_overloaded_case(
        self,
        concurrency: int,
        inventory: int,
        duration_seconds: int,
        request_count: int,
    ) -> FlashSaleResult:
        """模拟过高并发下的异常链路。

        过载时我们刻意让 TPS 下降、失败请求上升，并生成异常日志：
        - oversell：模拟库存扣减不是原子操作，多个请求读到旧库存。
        - deadlock：模拟数据库行锁竞争和连接池拥堵。
        """

        overload_ratio = concurrency / HIGH_CONCURRENCY_THRESHOLD
        base_capacity = int(HIGH_CONCURRENCY_THRESHOLD * duration_seconds * 0.75)

        # 并发越高，系统有效处理能力越差，表现为吞吐下降。
        capacity_drop = min(0.75, (overload_ratio - 1.0) * 0.28)
        effective_capacity = max(1, int(base_capacity * (1.0 - capacity_drop)))

        # 异常类型使用随机但可复现的方式生成。
        anomaly_type = self._random.choice(["oversell", "deadlock"])

        oversold_units = 0
        if anomaly_type == "oversell":
            # 超卖时成功订单可能超过库存，模拟非原子扣减导致的脏窗口。
            oversold_units = max(1, int((concurrency - HIGH_CONCURRENCY_THRESHOLD) * 0.03))
            success_orders = min(request_count, inventory + oversold_units)
        else:
            # 死锁时大量请求失败，成功订单反而低于库存和有效容量。
            success_orders = min(inventory, int(effective_capacity * self._random.uniform(0.35, 0.65)))

        failed_requests = max(0, request_count - success_orders)
        remaining_inventory = max(0, inventory - min(success_orders, inventory))

        # 过载时 Redis QPS 仍可能很高，但业务 TPS 因锁等待、重试和失败而下降。
        tps = round(success_orders / duration_seconds, 2)
        redis_qps = round(
            request_count / duration_seconds * self._random.uniform(2.8, 4.5),
            2,
        )

        logs = [
            self._format_log(
                "WARN",
                (
                    f"traffic overload detected; concurrency={concurrency}, "
                    f"threshold={HIGH_CONCURRENCY_THRESHOLD}, failed_requests={failed_requests}"
                ),
            )
        ]

        if anomaly_type == "oversell":
            logs.append(
                self._format_log(
                    "ERROR",
                    (
                        "oversell detected: inventory deduction is not atomic; "
                        f"success_orders={success_orders}, inventory={inventory}, "
                        f"oversold_units={oversold_units}"
                    ),
                )
            )
        else:
            logs.append(
                self._format_log(
                    "ERROR",
                    (
                        "deadlock detected: database row locks and connection pool "
                        f"are saturated; concurrency={concurrency}, redis_qps={redis_qps}"
                    ),
                )
            )

        if overload_ratio >= 2.0:
            logs.append(
                self._format_log(
                    "CRITICAL",
                    "retry storm observed; queueing delay is amplifying downstream pressure",
                )
            )

        return FlashSaleResult(
            sku_id=self.sku_id,
            concurrency=concurrency,
            inventory=inventory,
            duration_seconds=duration_seconds,
            request_count=request_count,
            success_orders=success_orders,
            failed_requests=failed_requests,
            tps=tps,
            redis_qps=redis_qps,
            remaining_inventory=remaining_inventory,
            oversold_units=oversold_units,
            anomaly_type=anomaly_type,
            logs=logs,
            timestamp=time.time(),
        )

    def _estimate_request_count(self, concurrency: int, duration_seconds: int) -> int:
        """根据并发量和持续时间估算总请求数。"""

        # 正常并发下，请求速率相对温和，便于展示稳定 TPS 和成功订单。
        # 过载并发下，请求速率明显放大，用于模拟突发流量、重试和热点 Key 压力。
        if concurrency <= HIGH_CONCURRENCY_THRESHOLD:
            requests_per_worker_per_second = self._random.uniform(0.08, 0.16)
        else:
            requests_per_worker_per_second = self._random.uniform(0.7, 1.3)
        return max(1, int(concurrency * duration_seconds * requests_per_worker_per_second))

    def _format_log(self, level: str, message: str) -> str:
        """生成统一格式的模拟系统日志。"""

        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        return f"{timestamp} [{level}] {message}"

    @staticmethod
    def _positive_int(value: int, fallback: int) -> int:
        """把输入规整为正整数，避免外部传入非法参数导致模拟器崩溃。"""

        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = fallback
        return max(1, parsed)

    @staticmethod
    def _non_negative_int(value: int, fallback: int) -> int:
        """把输入规整为非负整数。"""

        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = fallback
        return max(0, parsed)


# MCP Server 与后续 Agent 节点会复用这个默认实例，从而共享“最近一次演练”。
default_simulator = FlashSaleSimulator()


if __name__ == "__main__":
    simulator = FlashSaleSimulator()

    print("=== 正常并发演示 ===")
    print(simulator.run(concurrency=500, inventory=800, duration_seconds=10))

    print("\n=== 高并发异常演示 ===")
    print(simulator.run(concurrency=1500, inventory=800, duration_seconds=10))
