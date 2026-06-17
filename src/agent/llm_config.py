"""大模型配置模块。

Phase 3 要求本项目不再依赖本地 Ollama，而是通过 ``langchain_openai``
中的 ``ChatOpenAI`` 连接云端 OpenAI 兼容 API，例如 DeepSeek API 或
通义千问 DashScope OpenAI 兼容模式。

同时，为了保证课程演示在没有网络、没有 API Key 或依赖尚未安装时仍然
可以跑通，本模块提供 ``MockLLM``。它实现了与 LangChain Chat Model 类似
的 ``invoke()`` 方法，并返回固定的排查和调优建议。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - 依赖缺失时保持模块可导入。
    load_dotenv = None

try:
    from langchain_openai import ChatOpenAI
except ImportError:  # pragma: no cover - 依赖缺失时自动降级到 MockLLM。
    ChatOpenAI = None


@dataclass
class MockLLMResponse:
    """MockLLM 返回对象。

    LangChain 的聊天模型通常返回带有 ``content`` 字段的消息对象。
    为了让调用方可以用同一套逻辑读取结果，这里也提供 ``content`` 字段。
    """

    content: str


class MockLLM:
    """离线兜底大模型。

    当 ``ENABLE_LLM=false``、API Key 缺失，或 ``langchain_openai`` 未安装时，
    ``get_chat_model`` 会返回该对象。这样 Tuner Agent 不需要关心当前是真实
    云端模型还是离线 Mock，都可以直接调用 ``.invoke(prompt)``。
    """

    def invoke(self, prompt: str, *_args: Any, **_kwargs: Any) -> MockLLMResponse:
        """返回预设的资深架构师排查建议。"""

        advice = (
            "【MockLLM 调优建议】检测到秒杀链路存在高并发风险时，优先排查 "
            "Redis 库存扣减是否具备原子性。建议使用 Lua 脚本将校验库存、扣减库存、"
            "写入令牌结果合并为单个原子操作；数据库侧使用 `stock >= n` 条件更新兜底，"
            "并缩短事务范围。若日志包含 deadlock，应检查连接池大小、慢事务和热点行锁，"
            "必要时按 SKU 或活动维度做库存分片，并加入令牌桶限流与请求排队。"
        )
        return MockLLMResponse(content=advice)


def llm_enabled() -> bool:
    """判断是否启用真实云端大模型调用。"""

    value = os.getenv("ENABLE_LLM", "false").strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


@lru_cache(maxsize=1)
def get_chat_model() -> Any:
    """创建聊天模型。

    环境变量：
    - ``ENABLE_LLM``：为 true 时才尝试使用真实云端模型。
    - ``OPENAI_API_KEY``：云端模型 API Key。
    - ``OPENAI_BASE_URL``：OpenAI 兼容 API 地址。
    - ``OPENAI_MODEL``：模型名称。

    任一关键条件不满足时都会返回 ``MockLLM``，保证本地演示不被网络或 Key 阻塞。
    """

    if load_dotenv is not None:
        load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    model = os.getenv("OPENAI_MODEL")

    if not llm_enabled():
        return MockLLM()

    if not api_key or not base_url or not model:
        return MockLLM()

    if ChatOpenAI is None:
        return MockLLM()

    return ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.2")),
        timeout=int(os.getenv("OPENAI_TIMEOUT_SECONDS", "120")),
    )
