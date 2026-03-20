## @tool 콜링 ##

* [셀 1] 임포트
```python
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
import random
```

* [셀 2] @tool 선언
```python
# ──────────────────────────────────────
# 1. IT 운영 도구 정의
# ──────────────────────────────────────

@tool
def check_server_status(hostname: str) -> str:
    """서버의 현재 상태(CPU, 메모리, 디스크)를 조회합니다."""
    # 실제로는 Prometheus API, SSH 등으로 조회
    data = {
        "api-server-01": {"cpu": 72, "memory": 85, "disk": 45, "status": "running", "uptime": "32일"},
        "api-server-02": {"cpu": 23, "memory": 41, "disk": 38, "status": "running", "uptime": "32일"},
        "db-master":     {"cpu": 91, "memory": 93, "disk": 78, "status": "warning", "uptime": "120일"},
        "redis-01":      {"cpu": 15, "memory": 62, "disk": 20, "status": "running", "uptime": "45일"},
    }
    info = data.get(hostname)
    if not info:
        return f"호스트 '{hostname}'을 찾을 수 없습니다. 사용 가능: {list(data.keys())}"
    return (f"[{hostname}] 상태: {info['status']}, "
            f"CPU: {info['cpu']}%, MEM: {info['memory']}%, "
            f"DISK: {info['disk']}%, 업타임: {info['uptime']}")


@tool
def query_database(sql: str) -> str:
    """데이터베이스에 SQL 쿼리를 실행합니다. SELECT 쿼리만 허용됩니다."""
    # 실제로는 DB 커넥션으로 실행
    if not sql.strip().upper().startswith("SELECT"):
        return "오류: SELECT 쿼리만 허용됩니다."

    # 더미 결과
    if "error_log" in sql.lower():
        return ("최근 에러 로그:\n"
                "| timestamp           | level | service    | message                    |\n"
                "|---------------------|-------|------------|----------------------------|\n"
                "| 2026-03-21 04:32:11 | ERROR | auth-api   | Connection timeout to DB   |\n"
                "| 2026-03-21 04:33:45 | ERROR | auth-api   | Connection timeout to DB   |\n"
                "| 2026-03-21 04:35:02 | WARN  | payment-api| Slow query detected (3.2s) |\n"
                f"총 3건")
    elif "active_user" in sql.lower() or "session" in sql.lower():
        return "현재 활성 세션: 1,247개, 최근 1시간 신규 로그인: 342건"
    else:
        return "쿼리 실행 완료. 결과: 0건"


@tool
def check_pod_status(namespace: str) -> str:
    """Kubernetes 네임스페이스의 Pod 상태를 조회합니다."""
    pods = {
        "production": [
            {"name": "auth-api-7d8f9-xk2lm", "status": "Running", "restarts": 0, "age": "5d"},
            {"name": "auth-api-7d8f9-mn4qr", "status": "Running", "restarts": 0, "age": "5d"},
            {"name": "payment-api-3b2c1-ab8cd", "status": "Running", "restarts": 2, "age": "3d"},
            {"name": "gateway-5f4e3-zz9yy", "status": "CrashLoopBackOff", "restarts": 15, "age": "1d"},
        ],
        "staging": [
            {"name": "auth-api-staging-abc12", "status": "Running", "restarts": 0, "age": "2d"},
            {"name": "payment-api-staging-def34", "status": "Running", "restarts": 0, "age": "2d"},
        ]
    }
    pod_list = pods.get(namespace)
    if not pod_list:
        return f"네임스페이스 '{namespace}'를 찾을 수 없습니다."

    lines = [f"[{namespace}] Pod 목록:"]
    for p in pod_list:
        icon = "✅" if p["status"] == "Running" else "❌"
        lines.append(f"  {icon} {p['name']} | {p['status']} | 재시작: {p['restarts']}회 | {p['age']}")
    return "\n".join(lines)


@tool
def rollback_deployment(service: str, version: str) -> str:
    """서비스를 특정 버전으로 롤백합니다. 주의: 프로덕션에 영향을 줍니다."""
    valid_services = ["auth-api", "payment-api", "gateway", "user-api"]
    if service not in valid_services:
        return f"서비스 '{service}'를 찾을 수 없습니다. 사용 가능: {valid_services}"
    return f"✅ [{service}] v{version}으로 롤백 완료. 새 Pod 생성 중... (예상 소요: 30초)"


@tool
def get_deploy_history(service: str) -> str:
    """서비스의 최근 배포 이력을 조회합니다."""
    history = {
        "gateway": [
            "v2.3.1 (2026-03-21 03:00) ← 현재 ❌ CrashLoopBackOff",
            "v2.3.0 (2026-03-20 14:00) ← 정상 운영됨",
            "v2.2.9 (2026-03-18 10:00)",
        ],
        "auth-api": [
            "v1.8.2 (2026-03-16 09:00) ← 현재",
            "v1.8.1 (2026-03-10 11:00)",
        ]
    }
    h = history.get(service)
    if not h:
        return f"'{service}'의 배포 이력이 없습니다."
    return f"[{service}] 배포 이력:\n" + "\n".join(f"  {i+1}. {v}" for i, v in enumerate(h))

tools = [check_server_status, query_database, check_pod_status, rollback_deployment, get_deploy_history]
```

* [셀3] 에이전트 구성
```python
# ──────────────────────────────────────
# 2. 에이전트 구성
# ──────────────────────────────────────
llm = ChatOpenAI(model="gpt-4o")
llm_with_tools = llm.bind_tools(tools)

class State(TypedDict):
    messages: Annotated[list, add_messages]

def agent(state: State):
    system_msg = {
        "role": "system",
        "content": "당신은 IT 인프라 운영 전문가입니다. 서버 상태, DB, K8s를 모니터링하고 장애를 진단합니다."
    }
    response = llm_with_tools.invoke([system_msg] + state["messages"])
    return {"messages": [response]}

tool_node = ToolNode(tools)

def should_use_tool(state: State):
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return END

graph_builder = StateGraph(State)
graph_builder.add_node("agent", agent)
graph_builder.add_node("tools", tool_node)
graph_builder.add_edge(START, "agent")
graph_builder.add_conditional_edges("agent", should_use_tool)
graph_builder.add_edge("tools", "agent")

agent = graph_builder.compile()
```

* [셀4] 테스트 / 실행
```python
# ──────────────────────────────────────
# 3. 실행 예시
# ──────────────────────────────────────

# 예시 1: 장애 진단
result = agent.invoke({
    "messages": [{"role": "user", "content": "프로덕션에 문제 있는 것 같아. Pod 상태 확인해줘"}]
})
print(result["messages"][-1].content)

# 예시 2: 연쇄 조사 (도구 여러 번 호출)
result = agent.invoke({
    "messages": [{"role": "user", "content": "db-master 서버 상태 확인하고, 관련 에러 로그도 조회해줘"}]
})
print(result["messages"][-1].content)

# 예시 3: 롤백 판단
result = agent.invoke({
    "messages": [{"role": "user", "content": "gateway가 CrashLoop인데, 배포 이력 보고 이전 버전으로 롤백해줘"}]
})
print(result["messages"][-1].content)
```


## MCP ##

* 패키지 설치
```shell
pip install langchain-mcp-adapters langgraph langchain-openai
```

* MCP 서버 준비
```python
# mcp_server.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("IT운영서버")

@mcp.tool()
def check_server_status(hostname: str) -> str:
    """서버의 CPU, 메모리, 디스크 상태를 조회합니다."""
    data = {
        "api-server-01": "CPU: 72%, MEM: 85%, DISK: 45%, 상태: running",
        "db-master":     "CPU: 91%, MEM: 93%, DISK: 78%, 상태: warning",
    }
    return data.get(hostname, f"'{hostname}' 서버를 찾을 수 없습니다.")

@mcp.tool()
def check_pod_status(namespace: str) -> str:
    """Kubernetes Pod 상태를 조회합니다."""
    if namespace == "production":
        return "gateway-5f4e3: ❌ CrashLoopBackOff (재시작 15회)\nauth-api-7d8f9: ✅ Running"
    return f"'{namespace}' 네임스페이스를 찾을 수 없습니다."

@mcp.tool()
def rollback_deployment(service: str, version: str) -> str:
    """서비스를 특정 버전으로 롤백합니다."""
    return f"✅ {service}를 v{version}으로 롤백 완료."

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

* LangGraph에서 MCP 도구 호출(stdio 방식)
```python
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# ──────────────────────────────────────
# MCP 서버에서 도구 가져오기
# ──────────────────────────────────────
async def build_graph():
    server_params = StdioServerParameters(
        command="python",
        args=["mcp_server.py"],   # MCP 서버 스크립트 경로
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # ✅ MCP 도구 → LangChain 도구로 변환
            tools = await load_mcp_tools(session)

            # LLM에 도구 바인딩
            llm = ChatOpenAI(model="gpt-4o")
            llm_with_tools = llm.bind_tools(tools)

            # 그래프 구성 (이전과 동일!)
            class State(TypedDict):
                messages: Annotated[list, add_messages]

            def agent(state: State):
                response = llm_with_tools.invoke(state["messages"])
                return {"messages": [response]}

            tool_node = ToolNode(tools)

            def should_use_tool(state: State):
                if state["messages"][-1].tool_calls:
                    return "tools"
                return END

            graph_builder = StateGraph(State)
            graph_builder.add_node("agent", agent)
            graph_builder.add_node("tools", tool_node)
            graph_builder.add_edge(START, "agent")
            graph_builder.add_conditional_edges("agent", should_use_tool)
            graph_builder.add_edge("tools", "agent")

            graph = graph_builder.compile()

            # 실행
            result = await graph.ainvoke({
                "messages": [{"role": "user", "content": "프로덕션 Pod 상태 확인해줘"}]
            })
            print(result["messages"][-1].content)

# 실행
import asyncio
asyncio.run(build_graph())
```

> [!TIP]
> 여러 MCP 서버 + @tool 혼합
```
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.tools import tool

# 로컬 도구
@tool
def calculator(expression: str) -> str:
    """수학 계산을 수행합니다."""
    return str(eval(expression))

async def build_graph():
    async with MultiServerMCPClient({
        "it-ops": {
            "command": "python",
            "args": ["mcp_server.py"],
            "transport": "stdio",
        },
        "github": {
            "url": "http://localhost:3002/sse",
            "transport": "sse",
        }
    }) as client:
        # MCP 도구들 가져오기
        mcp_tools = client.get_tools()

        # 로컬 도구 + MCP 도구 합치기
        all_tools = [calculator] + mcp_tools

        llm = ChatOpenAI(model="gpt-4o")
        llm_with_tools = llm.bind_tools(all_tools)

        # 그래프 구성...
        tool_node = ToolNode(all_tools)
        # 이하 동일
```

