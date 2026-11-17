# Kubernetes 환경에서 ServiceMonitor로 vLLM 메트릭 수집하기

Prometheus Operator(예: `kube-prometheus-stack`)가 설치된 환경에서는 `ServiceMonitor` 리소스를 통해 vLLM 파드의 메트릭을 자동으로 감지하고 수집할 수 있습니다.

---

## 1. 사전 확인 사항 (중요)

`ServiceMonitor`가 정상 작동하려면 아래 두 가지 라벨(Label) 매칭이 정확해야 합니다.

1. **Prometheus가 인식하는 라벨 확인**
   Prometheus가 어떤 `ServiceMonitor`를 감시할지 결정하는 라벨을 먼저 확인합니다. (보통 `release: prometheus` 또는 `release: kube-prometheus-stack`)
   ```bash
   kubectl get prometheus -A -o yaml | grep -A 5 serviceMonitorSelector
   ```
2. **Service의 포트 이름(name) 지정**
   `ServiceMonitor`는 포트 번호(`8000`)가 아닌 **포트 이름(`name`)**을 기준으로 타겟을 찾습니다.

---

## 2. 배포 매니페스트 작성

### ① vLLM Deployment (`vllm-deployment.yaml`)
vLLM 컨테이너가 실행되며 `8000` 포트로 `/metrics`를 노출하도록 구성합니다.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vllm-server
  namespace: default
  labels:
    app: vllm
spec:
  replicas: 1
  selector:
    matchLabels:
      app: vllm
  template:
    metadata:
      labels:
        app: vllm
    spec:
      containers:
        - name: vllm
          image: vllm/vllm-openai:latest
          args:
            - "--model"
            - "facebook/opt-125m"
            - "--port"
            - "8000"
          ports:
            - name: http # 포트 이름 지정
              containerPort: 8000
              protocol: TCP
```

### ② vLLM Service (`vllm-service.yaml`)
`ServiceMonitor`가 이 서비스를 찾을 수 있도록 `metadata.labels`와 `ports.name`을 명확히 지정합니다.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: vllm-service
  namespace: default
  labels:
    app: vllm # ServiceMonitor의 selector와 일치해야 함
spec:
  type: ClusterIP
  selector:
    app: vllm
  ports:
    - name: http-metrics # ServiceMonitor의 endpoints.port와 일치해야 함
      port: 8000
      targetPort: 8000
      protocol: TCP
```

### ③ ServiceMonitor (`vllm-servicemonitor.yaml`)
Prometheus에게 `vllm-service`의 `/metrics` 경로를 15초마다 긁어가도록 지시합니다.

```yaml
apiVersion: ://coreos.com
kind: ServiceMonitor
metadata:
  name: vllm-servicemonitor
  namespace: monitoring # 보통 Prometheus가 설치된 네임스페이스에 생성
  labels:
    # [필수] 1번 사전 확인에서 조회한 Prometheus의 serviceMonitorSelector 라벨 입력
    release: kube-prometheus-stack 
spec:
  # vLLM Service가 위치한 네임스페이스 지정
  namespaceSelector:
    matchNames:
      - default
  # vLLM Service의 metadata.labels와 일치해야 함
  selector:
    matchLabels:
      app: vllm
  endpoints:
    - port: http-metrics # vLLM Service의 ports.name과 일치해야 함
      path: /metrics
      interval: 15s
      scrapeTimeout: 10s
```

---

## 3. 적용 및 동작 확인

### 리소스 배포
```bash
kubectl apply -f vllm-deployment.yaml
kubectl apply -f vllm-service.yaml
kubectl apply -f vllm-servicemonitor.yaml
```

### Prometheus Targets 등록 확인
1. Prometheus 웹 UI에 접속합니다. (`kubectl port-forward svc/prometheus-operated 9090:9090 -n monitoring`)
2. 상단 메뉴에서 **Status > Targets**로 이동합니다.
3. 목록에 `serviceMonitor/monitoring/vllm-servicemonitor/0` 항목이 나타나고, **State**가 `UP`인지 확인합니다.

---

## 4. 트러블슈팅 체크리스트 (Targets에 안 뜰 때)

* **라벨 불일치**: `ServiceMonitor`의 `metadata.labels`가 Prometheus CR의 `serviceMonitorSelector`와 다른 경우.
* **네임스페이스 누락**: `vLLM`과 `Prometheus`가 다른 네임스페이스에 있는데, `ServiceMonitor`에 `namespaceSelector`를 빼먹은 경우.
* **포트 이름 불일치**: `Service`에 `ports.name`을 안 적었거나, `ServiceMonitor`의 `endpoints.port`에 숫자를 적은 경우.


## 4. Grafana 데이터 조회 및 대시보드 구성

Prometheus에 정상적으로 데이터가 쌓이고 있다면, Grafana에서 대시보드를 연결하여 실시간으로 추이를 모니터링할 수 있습니다.

### ① Grafana 접속 및 데이터 소스(Data Source) 확인
1. Grafana 웹 UI에 접속합니다.
   ```bash
   kubectl port-forward svc/kube-prometheus-stack-grafana 3000:80 -n monitoring
   ```
   *(기본 접속 정보: `http://localhost:3000` / ID: `admin`, PW: `prom-operator`)*
2. 좌측 메뉴에서 **Connections > Data sources**로 이동하여 **Prometheus**가 등록되어 있는지 확인합니다. (`kube-prometheus-stack` 설치 시 자동 등록됨)

---

### ② 공식 vLLM 대시보드 Import (가장 빠른 방법)
vLLM 공식 GitHub 저장소에서 제공하는 대시보드 JSON을 그대로 불러와 사용할 수 있습니다.

1. Grafana 좌측 메뉴에서 **Dashboards > New > Import**를 클릭합니다.
2. 아래 공식 대시보드 JSON URL 내용을 복사하여 **Import via dashboard JSON model** 입력란에 붙여넣고 **Load**를 클릭합니다.
   * **공식 대시보드 경로**: `https://githubusercontent.com`
3. 하단의 Prometheus 데이터 소스를 선택한 뒤 **Import**를 클릭합니다.

---

### ③ 주요 vLLM 메트릭 PromQL 쿼리 (직접 패널 생성 시)
대시보드를 직접 커스텀할 경우, **Explore** 또는 **Dashboard > Add visualization**에서 아래 PromQL 쿼리를 입력하여 데이터를 조회합니다.

| 모니터링 항목 | PromQL 쿼리 예시 | 설명 |
| :--- | :--- | :--- |
| **초당 생성 토큰 수 (Throughput)** | `rate(vllm:generation_tokens_total[1m])` | 1분 평균 초당 출력 토큰 수 (Tokens/sec) |
| **초당 프롬프트 토큰 수** | `rate(vllm:prompt_tokens_total[1m])` | 1분 평균 초당 입력 토큰 수 |
| **실행 중 / 대기 중 요청 수** | `vllm:num_requests_running`<br>`vllm:num_requests_waiting` | 현재 처리 중인 요청과 큐에서 대기 중인 요청 수 |
| **GPU KV 캐시 사용률 (%)** | `vllm:gpu_cache_usage_perc * 100` | GPU 메모리 내 KV 캐시 점유율 |
| **TTFT (첫 토큰 응답 시간, P95)** | `histogram_quantile(0.95, sum(rate(vllm:time_to_first_token_seconds_bucket[5m])) by (le))` | 요청 후 첫 토큰이 나오기까지 걸리는 시간 (상위 95%) |
| **TPOT (토큰당 생성 시간, P95)** | `histogram_quantile(0.95, sum(rate(vllm:time_per_output_token_seconds_bucket[5m])) by (le))` | 출력 토큰 하나당 생성되는 평균 시간 (상위 95%) |

> **💡 참고 (vLLM 버전별 메트릭 명칭 차이):**
> * 일부 구버전 또는 엔진 설정에 따라 메트릭 앞부분의 콜론(`:`)이 언더바(`_`)로 수집될 수 있습니다. (예: `vllm:num_requests_running` → `vllm_num_requests_running`)
> * Grafana **Explore** 메뉴에서 `vllm`을 입력해 자동 완성되는 메트릭 이름을 먼저 확인해 보세요.








-----------

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
