
## Agentic AI 아키텍처 ##
![](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/images/agentic-arch.png)

### Open WebUI 설치 ###
```
helm repo add open-webui https://helm.openwebui.com/
helm repo update
```
open-webui-values.yaml 파일을 만든다.
```
cat << 'EOF' > open-webui-values.yaml
ollama:
  enabled: false

# 일단 이 필드 빼두고 WebUI 띄우기 / 로그인 후 Settings에서 나중에 추가 가능
openaiBaseApiUrls: []
openaiApiKey: "dummy"

persistence:
  enabled: true
  size: 20Gi
  storageClass: gp3

service:
  type: LoadBalancer
  port: 80
  annotations:
    service.beta.kubernetes.io/aws-load-balancer-type: "external"
    service.beta.kubernetes.io/aws-load-balancer-nlb-target-type: "ip"
    service.beta.kubernetes.io/aws-load-balancer-scheme: "internet-facing"

resources:
  requests:
    cpu: "2"
    memory: "4Gi"
  limits:
    cpu: "4"
    memory: "8Gi"

extraEnvVars:
  - name: WEBUI_NAME
    value: "Agentic AI Workshop"
  - name: DEFAULT_USER_ROLE
    value: "user"
  - name: ENABLE_SIGNUP
    value: "true"
EOF
```
> [!TIP] 
> 현재 차트의 기본 values.yaml 확인    
> helm show values open-webui/open-webui > default-values.yaml  
> 
> 필요한 부분만 grep    
> grep -A1 -iE "openai|ollama|env" default-values.yaml    
> 

helm 차트를 이용하여 배포한다. 
```
helm upgrade --install open-webui open-webui/open-webui \
  -n webui --create-namespace \
  -f open-webui-values.yaml
```







----

#### 필수 구현해야 할 3개 엔드포인트 ####
* GET  /v1/models              → 사용 가능한 모델 목록
* POST /v1/chat/completions    → 실제 채팅 (stream / non-stream 모두)
* GET  /health                 → 헬스체크 (선택이지만 권장)


## FastAPI + LangGraph ##
```
import json
import time
import uuid
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langgraph.graph import StateGraph
from langchain_aws import ChatBedrock
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# (여기서는 간단히 구조만. 실제 LangGraph 에이전트는 별도 모듈로 분리 추천)
from my_agent import build_agent   # LangGraph 워크플로우 빌드 함수


app = FastAPI(title="Agentic AI Gateway")

# 에이전트는 프로세스 시작 시 한 번만 빌드
agent = build_agent()


# ---------- Pydantic 모델 (OpenAI 스펙) ----------

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float | None = 0.2
    max_tokens: int | None = None


# ---------- /v1/models ----------

@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": "agentic-rag",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "workshop",
            }
        ],
    }


# ---------- /v1/chat/completions ----------

@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    # OpenAI 메시지 → LangChain 메시지로 변환
    lc_messages = []
    for m in req.messages:
        if m.role == "system":
            lc_messages.append(SystemMessage(content=m.content))
        elif m.role == "user":
            lc_messages.append(HumanMessage(content=m.content))
        elif m.role == "assistant":
            lc_messages.append(AIMessage(content=m.content))

    if req.stream:
        return StreamingResponse(
            stream_agent(lc_messages, req.model),
            media_type="text/event-stream",
        )

    # Non-stream: 한 번에 결과 반환
    result = await agent.ainvoke({"messages": lc_messages})
    answer = result["messages"][-1].content

    return {
        "id": f"chatcmpl-{uuid.uuid4()}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": answer},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }


# ---------- 스트리밍 ----------

async def stream_agent(messages, model: str) -> AsyncIterator[str]:
    """LangGraph의 astream으로 토큰 단위 스트리밍."""
    chat_id = f"chatcmpl-{uuid.uuid4()}"
    created = int(time.time())

    # LangGraph가 노드 단위로 결과를 흘려보냄
    async for chunk in agent.astream(
        {"messages": messages},
        stream_mode="messages",   # 토큰 단위
    ):
        # chunk 구조는 LangGraph 설정에 따라 다름
        # 예시: (message_chunk, metadata) 튜플
        if isinstance(chunk, tuple):
            msg_chunk = chunk[0]
            content = getattr(msg_chunk, "content", "")
        else:
            content = str(chunk)

        if not content:
            continue

        payload = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {"content": content},
                "finish_reason": None,
            }],
        }
        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    # 마지막에 종료 시그널
    done_payload = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(done_payload)}\n\n"
    yield "data: [DONE]\n\n"


# ---------- 헬스체크 ----------

@app.get("/health")
async def health():
    return {"status": "ok"}
```

실행:
```
pip install fastapi uvicorn langgraph langchain-aws
uvicorn agent_gateway:app --host 0.0.0.0 --port 8000
```

----

고려할 포인트

1. 스트리밍이 중요
Open WebUI는 스트리밍을 기대해요. 한 번에 답 주면 사용자가 몇 초씩 기다려야 함. LangGraph의 astream(stream_mode="messages") 꼭 쓰세요.

2. Tool 호출 진행 표시
고급 사용자 경험을 위해, Tool 실행 중 상태를 사용자에게 보여주면 좋아요:

🔍 Milvus에서 검색 중...
📊 재순위화 중...
💭 답변 생성 중...
Open WebUI가 "thinking" 블록을 지원하는데 <thinking>...</thinking> 태그나 o1 스타일 reasoning_content 포맷 쓰면 접어서 보여줘요.

3. 세션/메모리 관리
Open WebUI는 대화 이력을 messages 배열로 매번 다시 보내요. LangGraph의 Checkpointer(Memory)와 겹치면 이중 저장 돼서 혼란스러울 수 있어요.

두 전략 중 선택:

A. Open WebUI에만 맡기기: LangGraph는 매 요청 stateless, messages 그대로 사용
B. LangGraph가 주도: conversation_id를 커스텀 헤더로 받아 Checkpointer 관리
워크샵용이면 A가 간단.

4. 에러 처리
LangGraph에서 예외 나면 Open WebUI는 응답이 오기를 계속 기다려요. 에러도 OpenAI 포맷으로 반환:

from fastapi import HTTPException

try:
    result = await agent.ainvoke({"messages": lc_messages})
except Exception as e:
    return {
        "error": {
            "message": str(e),
            "type": "internal_error",
            "code": 500,
        }
    }
5. 인증 (프로덕션)
"API Key: dummy"는 교육용. 프로덕션이면:

API Key 검증 미들웨어
ALB + Cognito
mTLS (사내 Zero Trust 환경)
