## 1. 인프라/엔지니어링 관점: "LLM 부하/서빙 성능 (Serving Performance)"
인프라가 얼마나 빠르고 안정적으로 결과를 뱉어내는지를 뜻하며, 'LLM 서빙 성능 평가', '인프라 벤치마크(Benchmark)', 또는 **'부하 테스트(Load Testing)'**라고 명명합니다.
지적하신 레이턴시의 경우, LLM은 한 글자씩 출력되는 특성 때문에 일반 웹 서비스와 달리 더 세분화해서 측정합니다.
용어	설명	비유
TTFT
(Time to First Token)	유저가 질문을 던지고 첫 번째 글자가 나올 때까지 걸리는 레이턴시. 인프라의 초기 반응 속도를 뜻합니다.	면접관이 질문했을 때 첫 마디를 떼기까지 걸린 시간
ITL
(Inter-Token Latency)	첫 글자가 나온 이후, 다음 글자가 나오는 데 걸리는 평균 레이턴시. 모델이 답변을 생성하는 속도입니다.	말을 시작한 뒤 다음 단어를 이어 나가는 속도
TPS / RPS
(Tokens/Requests Per Second)	처리량(Throughput). 시스템(GPU/인프라)이 1초당 뱉어낼 수 있는 토큰(글자) 수 또는 처리할 수 있는 유저 요청 수입니다.	마트 계산대가 1초에 처리할 수 있는 손님 수



# LLM 부하 및 서빙 성능 측정 가이드

LLM 부하 및 서빙 성능 측정은 단순 응답 속도뿐만 아니라 **토큰 단위 지연 시간(Latency)과 시스템 전체 처리량(Throughput)의 균형**을 파악하는 것이 핵심입니다.

---

## 1. 핵심 측정 지표 (Metrics)

일반적인 웹 API와 달리 LLM 서빙에서는 스트리밍 응답 특성을 반영한 지표를 측정해야 합니다.

| 구분 | 지표명 | 의미 및 중요도 |
| :--- | :--- | :--- |
| **지연 시간**<br>(사용자 체감) | **TTFT** (Time To First Token) | 요청 후 첫 번째 토큰이 생성되기까지 걸리는 시간입니다. 입력 프롬프트 처리(Prefill) 속도를 반영하며, 높을수록 사용자가 먹통으로 느낍니다. |
| **지연 시간**<br>(사용자 체감) | **TPOT / ITL** | **TPOT**는 출력 토큰 1개당 평균 생성 시간, **ITL**은 토큰과 토큰 사이의 실제 간격입니다. 글자가 화면에 찍히는 부드러움을 결정합니다. |
| **지연 시간**<br>(전체) | **E2E Latency** | 요청 전송부터 마지막 토큰 생성 완료까지의 총시간입니다. |
| **처리량**<br>(시스템 효율) | **Throughput** | 초당 처리 요청 수(RPS/QPS) 및 초당 생성 토큰 수(Output tokens/sec)를 의미합니다. |
| **품질 기준** | **Goodput** | 서비스 목표 기준(SLO, 예: TTFT 1초 이내)을 만족하면서 처리한 유효 처리량입니다. |

> **참고:** 평균값 외에 상위 1% 최악의 응답 시간을 보여주는 **P99 지표**를 반드시 함께 확인해야 일부 사용자의 긴 대기 시간을 잡아낼 수 있습니다.

---

## 2. 주요 벤치마크 및 부하 테스트 도구

현재 실무에서 가장 널리 쓰이는 오픈소스 도구들은 OpenAI 호환 API 엔드포인트를 지원합니다.

* **vLLM 내장 벤치마크 (`vllm bench serve`):** vLLM을 사용 중이라면 별도 설치 없이 바로 활용할 수 있습니다. 동시 실행 수(`--max-concurrency`)나 초당 요청 수(`--request-rate`)를 지정해 세밀한 테스트가 가능합니다.
* **GuideLLM:** vLLM 프로젝트에서 공개한 도구로, 부하를 단계별로 자동 증가시키는 **Sweep 모드**를 지원해 서버의 한계점(Saturation point)을 자동으로 찾아줍니다.
* **NVIDIA GenAI-Perf / AIPerf:** NVIDIA Triton이나 TensorRT-LLM 환경 등에서 표준화된 LLM 지표를 측정할 때 유용합니다.
* **Locust / k6:** API 게이트웨이, 인증, RAG 파이프라인 등 전체 서비스 아키텍처를 묶어 실제 사용자 시나리오대로 부하를 줄 때 적합합니다.

---

## 3. 실전 테스트 진행 절차

1. **워크로드(데이터셋) 정의:** 실제 서비스와 유사한 입력(Prompt) 길이와 출력(Completion) 길이를 설정합니다. 무작위 토큰(Random)으로 순수 엔진 한계를 먼저 본 뒤, 실제 대화 로그나 ShareGPT 같은 데이터셋으로 테스트하는 것이 좋습니다.
2. **기준점(Baseline) 측정:** 동시 접속자 수(Concurrency)를 `1`로 설정해 단독 요청 시의 최소 TTFT와 최대 토큰 생성 속도를 확인합니다.
3. **부하 증가 테스트 (Concurrency / QPS Sweep):** 동시 요청 수를 `1 → 2 → 4 → 8 → 16 → 32` 순으로 늘리거나 초당 요청 도착률(QPS)을 높여가며 측정합니다.
4. **병목 및 한계점 분석:** 동시 요청이 늘어나면 전체 토큰 처리량(Throughput)은 증가하다가 어느 순간 정체되고, 동시에 TTFT와 ITL이 급격히 나빠집니다. 서비스가 허용할 수 있는 **최대 지연 시간(SLO)을 넘기기 직전의 동시 처리량**이 해당 서버의 적정 수용량입니다.

---

## 4. 측정 시 주의할 함정 (Anti-patterns)

* **Prefix Caching 왜곡:** 동일한 프롬프트를 계속 반복해서 보내면 서빙 엔진의 캐시 기능이 작동해 실제 운영 환경보다 TTFT가 비정상적으로 빠르게 측정됩니다. 요청마다 고유한 접두사(Prefix)를 붙이거나 다양한 프롬프트를 섞어야 합니다.
* **출력 토큰 길이 미고정:** 모델이 답변을 일찍 끝내버리면(EOS 토큰 생성) 정확한 부하 비교가 어렵습니다. 순수 하드웨어/엔진 비교 시에는 `ignore_eos` 옵션을 켜서 지정된 출력 토큰 수만큼 끝까지 생성하도록 강제해야 합니다.
* **클라이언트 병목:** 부하를 생성하는 클라이언트(테스트 실행 서버)의 CPU나 네트워크 대역폭이 부족하면 서버 성능이 낮게 측정될 수 있습니다.

---

## 5. 실전 부하 테스트 스크립트

### 5.1. vLLM 내장 벤치마크 CLI

vLLM을 사용 중이거나 `vllm` 패키지가 설치된 클라이언트 환경이라면 별도 코딩 없이 아래 명령어로 즉시 정밀 측정이 가능합니다.

```bash
# 입력 512 토큰, 출력 256 토큰으로 고정하여 동시 접속자 16명 부하 테스트
vllm bench serve \
  --backend openai-chat \
  --base-url http://localhost:8000 \
  --endpoint /v1/chat/completions \
  --model meta-llama/Llama-3.1-8B-Instruct \
  --dataset-name random \
  --random-input-len 512 \
  --random-output-len 256 \
  --num-prompts 100 \
  --max-concurrency 16 \
  --ignore-eos
```

* `--dataset-name random`: Prefix Caching 왜곡을 막기 위해 요청마다 무작위 프롬프트를 생성합니다.
* `--ignore-eos`: 모델이 중간에 답변을 끊지 않고 정확히 256토큰까지 생성하도록 강제합니다.
* 실행이 끝나면 **Mean/Median/P99 단위의 TTFT, TPOT, ITL, Output Token Throughput**이 표로 출력됩니다.

### 5.2. 범용 Python 부하 테스트 스크립트 (OpenAI API 호환)

Ollama, SGLang, Triton, 상용 API 등 **어떤 서버든 `/v1/chat/completions`만 지원하면 바로 실행**할 수 있는 경량 스크립트입니다. (`pip install openai numpy` 필요)

```python
import asyncio
import time
import uuid
import numpy as np
from openai import AsyncOpenAI

# 1. 테스트 설정
BASE_URL = "http://localhost:8000/v1"
API_KEY = "EMPTY"
MODEL_NAME = "meta-llama/Llama-3.1-8B-Instruct"

TOTAL_REQUESTS = 40      # 총 보낼 요청 수
CONCURRENCY = 8          # 동시 요청 수 (부하 강도)
MAX_TOKENS = 256         # 생성할 최대 토큰 수

client = AsyncOpenAI(base_url=BASE_URL, api_key=API_KEY)

async def send_request(semaphore: asyncio.Semaphore, req_id: int):
    async with semaphore:
        # Prefix Caching 방지를 위해 요청마다 고유 ID 부여
        prompt = f"[Req-{uuid.uuid4().hex[:8]}] 인공지능의 발전이 소프트웨어 엔지니어링에 미치는 영향을 구체적인 사례와 함께 길게 설명해 주세요."
        
        start_time = time.perf_counter()
        first_token_time = None
        token_times = []
        
        try:
            stream = await client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=MAX_TOKENS,
                temperature=0.7,
                stream=True,
                # vLLM/SGLang 서버일 경우 아래 주석 해제 시 정확한 길이 측정 가능
                # extra_body={"ignore_eos": True} 
            )
            
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    now = time.perf_counter()
                    if first_token_time is None:
                        first_token_time = now
                    token_times.append(now)
                    
            end_time = time.perf_counter()
            
            if not token_times:
                return None

            ttft = first_token_time - start_time
            e2e = end_time - start_time
            num_chunks = len(token_times)
            # 첫 토큰 이후 나머지 토큰 생성에 걸린 시간 / 토큰 수
            tpot = (end_time - first_token_time) / max(num_chunks - 1, 1)
            
            return {
                "ttft": ttft,
                "tpot": tpot,
                "e2e": e2e,
                "tokens": num_chunks
            }
        except Exception as e:
            print(f"[에러] 요청 {req_id} 실패: {e}")
            return None

async def main():
    print(f"🚀 부하 테스트 시작 (총 요청: {TOTAL_REQUESTS}, 동시성: {CONCURRENCY})")
    semaphore = asyncio.Semaphore(CONCURRENCY)
    
    bench_start = time.perf_counter()
    tasks = [send_request(semaphore, i) for i in range(TOTAL_REQUESTS)]
    results = await asyncio.gather(*tasks)
    bench_end = time.perf_counter()
    
    valid = [r for r in results if r is not None]
    total_time = bench_end - bench_start
    total_tokens = sum(r["tokens"] for r in valid)
    
    ttfts = [r["ttft"] for r in valid]
    tpots = [r["tpot"] for r in valid]
    e2es = [r["e2e"] for r in valid]

    print("\n" + "="*45)
    print(f"성공 요청: {len(valid)} / {TOTAL_REQUESTS} (총 소요시간: {total_time:.2f}s)")
    print(f"전체 처리량 (Throughput): {total_tokens / total_time:.2f} tokens/sec")
    print(f"초당 요청 수 (RPS): {len(valid) / total_time:.2f} req/sec")
    print("-" * 45)
    print(f"TTFT (첫 토큰 지연)  - 평균: {np.mean(ttfts):.3f}s | P99: {np.percentile(ttfts, 99):.3f}s")
    print(f"TPOT (토큰당 지연)   - 평균: {np.mean(tpots)*1000:.1f}ms | P99: {np.percentile(tpots, 99)*1000:.1f}ms")
    print(f"E2E  (전체 응답시간) - 평균: {np.mean(e2es):.3f}s | P99: {np.percentile(e2es, 99):.3f}s")
    print("="*45)

if __name__ == "__main__":
    asyncio.run(main())
```

### 5.3. 실행 및 활용 팁

* **단계별 부하 테스트:** 위 Python 스크립트에서 `CONCURRENCY` 값을 `1`, `4`, `8`, `16`, `32`로 차례대로 올려가며 실행해 보세요.
* **토큰 수 정확도:** OpenAI 스트리밍 API는 보통 1 chunk당 1 token을 반환하지만, 특수 문자나 한국어 바이트 분할에 따라 약간의 오차가 있을 수 있습니다. 정밀한 엔진 비교가 목적이라면 `vllm bench serve`를 권장합니다.
