"""Chaos-Tuner Agent 的 LangGraph 状态机。

Phase 3 的目标是把三个 Agent 节点组装成闭环：

    chaos_node -> monitor_node -> (有异常) tuner_node -> chaos_node
                               -> (无异常) END

当 Tuner Agent 完成建议生成后，如果 ``round_id < max_rounds``，工作流会
回到 Chaos Agent 重新压测；否则结束。
"""

from __future__ import annotations

import sys
from pathlib import Path
# 💡 新增这两行，确保程序一启动就把 LangSmith 的配置读进来
from dotenv import load_dotenv
load_dotenv()

# 支持直接执行 `python src/agent/graph.py`。
# 这种启动方式下，Python 默认只把 `src/agent` 加入 sys.path，
# 因此需要手动补充项目根目录，保证 `from src...` 导入可用。
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langgraph.graph import END, StateGraph

from src.agent.nodes import (
    State,
    chaos_node,
    monitor_node,
    route_after_monitor,
    route_after_tuner,
    tuner_node,
)


def build_graph():
    """构建并编译 LangGraph 工作流。"""

    workflow = StateGraph(State)

    # 注册三个核心节点。
    workflow.add_node("chaos_node", chaos_node)
    workflow.add_node("monitor_node", monitor_node)
    workflow.add_node("tuner_node", tuner_node)

    # 入口固定为 Chaos Agent。
    workflow.set_entry_point("chaos_node")

    # Chaos Agent 生成压测配置后，Monitor Agent 读取指标和日志。
    workflow.add_edge("chaos_node", "monitor_node")

    # Monitor Agent 判断是否发现异常。
    workflow.add_conditional_edges(
        "monitor_node",
        route_after_monitor,
        {
            "tuner": "tuner_node",
            "end": END,
        },
    )

    # Tuner Agent 输出建议后，按轮次预算决定是否重新压测。
    workflow.add_conditional_edges(
        "tuner_node",
        route_after_tuner,
        {
            "chaos": "chaos_node",
            "end": END,
        },
    )

    return workflow.compile()


def run_demo(max_rounds: int = 2) -> State:
    """运行一次本地演示并返回最终状态。"""

    app = build_graph()
    initial_state: State = {
        "round_id": 0,
        "max_rounds": max_rounds,
        "chaos_profile": {},
        "metrics": {},
        "logs": [],
        "anomaly_type": "none",
        "recommendations": "",
    }

    print("========== Chaos-Tuner Agent Demo Start ==========")
    final_state = app.invoke(initial_state)
    print("\n========== Chaos-Tuner Agent Demo Finished ==========")
    print(f"最终轮次: {final_state.get('round_id')}")
    print(f"最终异常类型: {final_state.get('anomaly_type')}")
    print(f"最终压测配置: {final_state.get('chaos_profile')}")
    print(f"最终指标: {final_state.get('metrics')}")
    print(f"最终建议: {final_state.get('recommendations') or '无异常，无需调优'}")
    return final_state


if __name__ == "__main__":
    # 按 Phase 3 要求，默认跑一个 max_rounds=2 的测试循环。
    run_demo(max_rounds=2)
