# LiteLLM 프로메테우스(Prometheus) 메트릭 수집 가이드

**LiteLLM 프록시(Proxy)**에서 프로메테우스(Prometheus)로 TTFT를 포함한 추론 지표를 수집하려면 **`config.yaml`에 `prometheus` 콜백을 추가**하고 `/metrics` 엔드포인트를 프로메테우스가 스크랩하도록 연결하면 됩니다.

vLLM을 직접 긁어오는 것과의 가장 큰 차이는 **LiteLLM이 게이트웨이 자체 오버헤드, 전체 API 지연 시간, 토큰당 비용 및 팀/키별 사용량**까지 함께 측정해 준다는 점입니다.

---

## 1. LiteLLM 설정 (`config.yaml` & 실행 옵션)

LiteLLM 설정 파일(`config.yaml`)에 `callbacks: ["prometheus"]` 한 줄만 추가하면 기본적으로 프록시 포트(4000번)의 `/metrics` 경로로 지표가 노출됩니다.

```yaml
model_list:
  - model_name: insurance-customer
    litellm_params:
      model: openai/insurance-customer
      api_base: http://vllm-service.llm-serving.svc.cluster.local:8000/v1
      api_key: "EMPTY"

litellm_settings:
  callbacks: ["prometheus"]        # 프로메테우스 메트릭 활성화
  service_callback: ["prometheus"] # (선택) 연결된 Redis/DB 장애 상태까지 함께 수집
```

> **💡 쿠버네티스 운영 팁 (멀티 워커 & 전용 메트릭 포트 분리):**
> 프로덕션 환경에서 `--num_workers 4`처럼 워커를 여러 개 띄우면 메트릭 집계가 꼬일 수 있고, API 포트로 `/metrics`가 외부에 노출될 위험이 있습니다. 실행 시 **`--prometheus_metrics_port 4001`** 옵션을 주면 전용 포트로 안전하게 분리되어 멀티 워커 메트릭도 자동 통합됩니다.
> ```bash
> litellm --config /app/config.yaml --num_workers 4 --prometheus_metrics_port 4001
> ```
> *(※ 직접 이미지를 빌드하시는 경우 `prometheus-client==0.20.0` 패키지가 설치되어 있어야 합니다.)*

---

### 2. LiteLLM이 노출하는 핵심 메트릭 이름

LiteLLM은 요청 구간을 세분화하여 히스토그램(Histogram) 지표를 제공합니다.

| 측정 구간 | LiteLLM 메트릭 이름 | 설명 |
| :--- | :--- | :--- |
| **TTFT (첫 토큰 응답 시간)** | `litellm_llm_api_time_to_first_token_metric` | 백엔드 LLM(vLLM) 호출 시작부터 첫 토큰 도착까지 시간 (**스트리밍 요청 시에만 기록**) |
| **전체 LLM 응답 시간** | `litellm_llm_api_latency_metric` | 백엔드 LLM 호출 시작부터 마지막 토큰 완료까지 시간 |
| **게이트웨이 오버헤드** | `litellm_overhead_latency_metric` | LLM 호출 시간을 제외한 LiteLLM 자체 처리 지연 시간 |
| **토큰 및 비용** | `litellm_total_tokens_metric`, `litellm_spend_metric` | 모델별, API 키별 입력/출력 토큰 수 및 누적 비용 |
| **처리 중인 요청 수** | `litellm_in_flight_requests` | 현재 프록시 파드에서 동시에 처리 중인 요청 수 (오토스케일링 지표 활용 가능) |

*(참고: LiteLLM은 토큰 간 간격인 TPOT/ITL을 단독 메트릭으로 쪼개지 않으므로, 토큰당 생성 속도는 `(전체 응답 시간 - TTFT) / 출력 토큰 수`로 계산하거나 백엔드 vLLM의 `vllm:time_per_output_token_seconds`를 함께 보는 것이 정확합니다.)*

---

## 3. 쿠버네티스 `ServiceMonitor` 및 PromQL 조회

전용 메트릭 포트(`4001`)를 열었다면 쿠버네티스 Service에 해당 포트를 등록한 뒤 아래와 같이 수집합니다.

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: litellm-metrics-monitor
  namespace: monitoring
spec:
  selector:
    matchLabels:
      app: litellm-proxy
  endpoints:
    - port: metrics       # 4001번 전용 메트릭 포트 이름
      path: /metrics
      interval: 15s
```

### 그라파나(Grafana) 조회용 PromQL
* **모델별 상위 95%(P95) TTFT:**
  ```promql
  histogram_quantile(0.95, sum(rate(litellm_llm_api_time_to_first_token_metric_bucket[5m])) by (le, model))
  ```
* **LiteLLM 게이트웨이 자체 평균 오버헤드 (초):**
  ```promql
  rate(litellm_overhead_latency_metric_sum[5m]) / rate(litellm_overhead_latency_metric_count[5m])
  ```

---

## 💡 실전 아키텍처 권장 조합 (vLLM + LiteLLM 이중 수집)

실무에서는 **두 곳 모두 프로메테우스에 연결**해 두는 것이 장애 원인 파악에 가장 좋습니다.

1. **LiteLLM 메트릭:** 사용자/서비스별 호출량, 모델별 비용, 게이트웨이 오버헤드, 전체 체감 TTFT 파악
2. **vLLM 메트릭:** 실제 GPU KV 캐시 포화도(`gpu_cache_usage_perc`), 큐 대기 시간, 순수 토큰 생성 속도(TPOT/ITL) 파악 및 **KEDA 오토스케일링 트리거**로 활용
