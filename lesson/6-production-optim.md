## 장시간 실행되는 에이전트의 상태 관리, 복구, 모니터링 ##
에이전트가 단순 질의응답이 아닌 수분에서 수시간에 걸치는 멀티스텝 작업을 수행하는 경우, 중간 상태를 외부 저장소에 체크포인트로 저장하여 장애 발생 시 마지막 체크포인트부터 재개할 수 있도록 구성해야 한다. LangGraph는 Redis, PostgreSQL 등을 체크포인터 백엔드로 지원하며, 그래프의 노드가 하나 실행될 때마다 자동으로 상태를 저장한다. 모니터링은 LangFuse를 통해 각 스텝별 실행 시간, 토큰 사용량, 실패 지점을 추적할 수 있다.

### 상태 관리 ###
에이전트의 실행 상태를 외부 저장소에 체크포인트로 저장해서, 중간에 죽어도 이어서 작업을 진행할 수 있게 한다.
```python
from langgraph.checkpoint.postgres import PostgresSaver

# 체크포인터 설정 - 매 노드 실행 후 상태를 DB에 저장
checkpointer = PostgresSaver(conn_string="postgresql://...")

graph = workflow.compile(checkpointer=checkpointer)

# 실행 시 thread_id로 세션 구분
config = {"configurable": {"thread_id": "task-123"}}
result = graph.invoke(input, config)
```
매 스텝마다 그래프 상태(현재 노드, 중간 결과, 메모리)가 DB에 저장된다. Redis, PostgreSQL, SQLite 등을 백엔드로 쓸 수 있다.


### 복구 ###
체크포인트가 있으면 복구는 간단한다.
```python
# 같은 thread_id로 다시 실행하면 마지막 체크포인트부터 이어서 진행
config = {"configurable": {"thread_id": "task-123"}}
result = graph.invoke(None, config)  # input=None이면 마지막 상태에서 재개
```
#### 추가로 고려할 것들: ####
* 타임아웃: 특정 스텝이 너무 오래 걸리면 강제 종료 후 폴백
* 재시도: LLM API 호출 실패 시 exponential backoff로 재시도
* 데드레터 큐: 반복 실패하는 작업은 별도 큐로 빼서 나중에 처리

### 모니터링 ###
```python
from langfuse.callback import CallbackHandler

handler = CallbackHandler(
    public_key="...",
    secret_key="...",
)

# 에이전트 실행 시 콜백 연결
result = graph.invoke(input, config, callbacks=[handler])
```

#### LangFuse에서 추적할 수 있는 것들: ####
* 각 스텝별 실행 시간, 토큰 사용량, 비용
* 어느 노드에서 실패했는지
* 전체 에이전트 실행 트레이스

#### 프로덕션에서는 여기에 Prometheus 메트릭도 추가해서: ####
* 에이전트 실행 중인 수 (active agents)
* 평균 완료 시간
* 실패율
* 스텝별 지연 시간


## 비용 최적화 ##
### 캐싱전략 ###
같은 질문이 반복될 때 LLM을 다시 호출하지 않고 캐시된 응답을 반환한다.
```python
from langchain.cache import RedisCache
from langchain.globals import set_llm_cache
import redis

# Redis 캐시 설정
set_llm_cache(RedisCache(redis_client=redis.Redis()))

# 이후 같은 프롬프트로 호출하면 캐시에서 반환
# → LLM 호출 안 함 → 토큰 비용 0, 응답 즉시
```

### 모델 라우팅 ###
```python
def route_to_model(query: str):
    # 간단한 분류기로 질문 복잡도 판단
    classifier_response = small_llm.invoke(
        f"이 질문이 단순한지 복잡한지 판단해: {query}\n답변: simple 또는 complex"
    )
    if "simple" in classifier_response:
        return small_llm   # 3B 모델 - 빠르고 저렴
    else:
        return large_llm   # 27B 모델 - 느리지만 정확
```
실제로는 분류기 자체도 비용이므로, 프롬프트 길이나 키워드 기반으로 단순하게 라우팅하는 경우도 많다.
셀프 호스팅(vLLM)이면 API 비용은 없지만 GPU 시간이 비용이라, 작은 모델로 처리할 수 있는 건 작은 모델로 보내서 GPU 리소스를 아끼는 게 핵심이다.

## 에러 핸들링/폴백 전략 ##
프로덕션 환경에서 에이전트는 다양한 이유로 실패할 수 있다. LLM API 호출 시 타임아웃이나 rate limit에 걸리거나, 외부 도구 호출 대상이 다운되거나, LLM이 예상과 다른 형식의 응답을 반환하거나, 에이전트가 무한 루프에 빠지는 경우가 대표적이다. 이러한 실패에 대비하여 재시도 로직, 폴백 전략, 타임아웃 처리를 구성하는 것은 프로덕션 필수 요소이다.

#### 1. 재시도 (Retry with backoff) ####
```
def call_llm_with_retry(state, max_retries=3):
    for attempt in range(max_retries):
        try:
            return llm.invoke(state["messages"])
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)  # 1초, 2초, 4초
```

#### 2. 폴백 (Fallback) - 큰 모델 실패 시 작은 모델로 대체 ####
```python
def llm_with_fallback(state):
    try:
        return primary_llm.invoke(state["messages"])
    except Exception:
        return fallback_llm.invoke(state["messages"])
```

#### 3. 타임아웃 - 에이전트 전체 실행 시간 제한 ####
```python
graph = workflow.compile()
try:
    result = graph.invoke(
        input,
        config={"recursion_limit": 25}  # 최대 25스텝으로 제한 (무한루프 방지)
    )
except Exception:
    result = "처리 시간이 초과되었습니다."
```

#### 4. 조건부 라우팅 - 실패 시 다른 경로로 ####
```python
def route_on_error(state):
    if state.get("error"):
        return "error_handler"  # 에러 처리 노드로
    return "next_step"          # 정상 진행
```
