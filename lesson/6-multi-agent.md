![](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/images/muti-agent-1.png)

```python
from langgraph.graph import StateGraph, MessagesState
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI

# LLM 초기화 (vLLM 엔드포인트)
llm = ChatOpenAI(model="qwen", base_url="http://vllm-qwen-svc/v1", api_key="dummy")

# 개별 에이전트 정의
def search_agent(state: MessagesState):
    """검색 전문 에이전트 - 문서 검색 후 답변 생성"""
    query = state["messages"][-1].content
    # 벡터DB 검색
    docs = vectordb.similarity_search(query, k=3)
    context = "\n".join([doc.page_content for doc in docs])
    # 검색 결과 기반으로 LLM 답변 생성
    result = llm.invoke(
        f"다음 문서를 참고하여 질문에 답변하세요.\n\n문서:\n{context}\n\n질문: {query}"
    )
    return {"messages": [AIMessage(content=result.content)]}

def code_agent(state: MessagesState):
    """코드 전문 에이전트 - 코드 생성 및 분석"""
    result = llm.invoke([
        {"role": "system", "content": "당신은 코드 전문가입니다. 코드 생성, 분석, 디버깅을 수행합니다."},
        {"role": "user", "content": state["messages"][-1].content},
    ])
    return {"messages": [AIMessage(content=result.content)]}

def analysis_agent(state: MessagesState):
    """분석 전문 에이전트 - 데이터 분석 및 요약"""
    result = llm.invoke([
        {"role": "system", "content": "당신은 데이터 분석 전문가입니다. 데이터를 분석하고 요약합니다."},
        {"role": "user", "content": state["messages"][-1].content},
    ])
    return {"messages": [AIMessage(content=result.content)]}

# Supervisor: 어떤 에이전트에게 보낼지 결정
def supervisor(state: MessagesState):
    response = llm.invoke([
        {"role": "system", "content": (
            "당신은 작업 분배 관리자입니다. 사용자의 질문을 분석하여 "
            "적절한 에이전트를 선택하세요.\n"
            "선택지: search, code, analysis, FINISH\n"
            "- search: 문서 검색이 필요한 질문\n"
            "- code: 코드 생성, 분석, 디버깅\n"
            "- analysis: 데이터 분석, 요약\n"
            "- FINISH: 충분한 답변이 완성된 경우\n"
            "에이전트 이름만 답하세요."
        )},
        {"role": "user", "content": state["messages"][-1].content},
    ])
    return {"next": response.content.strip()}

# 그래프 구성
workflow = StateGraph(MessagesState)
workflow.add_node("supervisor", supervisor)
workflow.add_node("search", search_agent)
workflow.add_node("code", code_agent)
workflow.add_node("analysis", analysis_agent)

# 라우팅: Supervisor가 선택한 에이전트로 분기
workflow.add_conditional_edges("supervisor", lambda s: s["next"], {
    "search": "search",
    "code": "code",
    "analysis": "analysis",
    "FINISH": "__end__",
})

# 각 에이전트 완료 후 Supervisor로 복귀
workflow.add_edge("search", "supervisor")
workflow.add_edge("code", "supervisor")
workflow.add_edge("analysis", "supervisor")

workflow.set_entry_point("supervisor")
graph = workflow.compile()

# 실행
result = graph.invoke(
    {"messages": [HumanMessage(content="NCCL 통신 최적화 방법을 알려줘")]},
    config={"recursion_limit": 10},
)
print(result["messages"][-1].content)
```
각 에이전트가 시스템 프롬프트로 역할을 구분하고, 같은 LLM을 공유하되 역할에 따라 다른 지시를 받는 구조이다. 에이전트별로 다른 모델을 쓰고 싶으면 LLM 인스턴스를 따로 만들면 된다.
