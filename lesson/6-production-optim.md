

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
에이전트가 작업을 실패했을 때 어떻게 복구하는지?, 재시도 로직, 타임아웃 처리는 프로덕션 환경의 필수 요소이다.
에이전트가 실패하는 흔한 케이스는 다음과 같다.
* LLM API 호출 실패 (타임아웃, rate limit, 500 에러)
* 도구 호출 실패 (외부 API 다운, DB 연결 끊김)
* LLM이 잘못된 형식의 응답 반환 (JSON 파싱 에러)
* 에이전트가 무한 루프에 빠짐

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
