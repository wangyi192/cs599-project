FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY . .

# 预留给 MCP Server HTTP/SSE 模式使用；默认演示入口仍走 LangGraph。
EXPOSE 8000

CMD ["python", "-m", "src.agent.graph"]
