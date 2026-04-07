## KEDA ##

[KEDA(Kubernetes Event-Driven Autoscaling)](https://keda.sh/) 는 Prometheus, CloudWatch, SQS 등 다양한 외부 메트릭 소스를 기반으로 Kubernetes 워크로드를 자동 스케일링하는 오픈소스 프레임워크이다. 기존 HPA가 CPU/메모리 같은 기본 메트릭만 지원하는 것과 달리, KEDA는 ScaledObject라는 커스텀 리소스를 통해 Prometheus 쿼리를 직접 스케일링 조건으로 사용할 수 있어, Prometheus Adapter 없이도 커스텀 메트릭 기반 오토스케일링을 간단하게 구성할 수 있다.

아래 명령어로 KEDA 를 설치한다.
```
helm repo add kedacore https://kedacore.github.io/charts
helm repo update
helm install keda kedacore/keda --namespace keda --create-namespace
```

아래와 같이 ScaledObject 를 생성한다. ScaledObject 는 KEDA가 제공하는 CRD(Custom Resource Definition)로 "어떤 Deployment를 어떤 메트릭 기준으로 스케일링할지" 정의하는 리소스이다. ScaledObject를 만들면 KEDA가 알아서 HPA를 생성하고 관리하기 때문에 직접 HPA를 만들 필요 없다.
```
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: vllm-qwen-scaler
spec:
  scaleTargetRef:
    name: vllm-qwen            # 스케일링 대상 Deployment
  minReplicaCount: 2
  maxReplicaCount: 8
  cooldownPeriod: 300          # 축소 전 5분 대기
  triggers:
    - type: prometheus
      metadata:
        serverAddress: http://prometheus-server.monitoring:9090
        query: sum(vllm:num_requests_waiting{namespace="default"})
        threshold: "10"
```
* Prometheus → KEDA (직접 연결) → HPA 자동 생성
* 동작 방식
```
1. 대기 요청 20개 → 파드 8개로 스케일 아웃
2. 트래픽 감소 → 대기 요청 3개 (threshold 10 이하)
3. 5분(cooldownPeriod) 동안 계속 낮은 상태 유지되는지 확인
4. 유지되면 파드 1개 제거 → 7개
5. 또 5분 대기 → 여전히 낮으면 → 6개
6. ...반복...
7. minReplicaCount=2까지만 줄임
```

### 메트릭 ###
#### 1. 추론 서버 메트릭 (vLLM/Triton) ####
```
vllm:num_requests_waiting          대기 중인 요청 수          // 설정 우선 순위 - 1
vllm:num_requests_running          처리 중인 요청 수
vllm:gpu_cache_usage_perc          KV Cache 사용률          // 설정 우선 순위 - 2
vllm:avg_prompt_throughput         초당 프롬프트 처리 토큰
vllm:avg_generation_throughput     초당 생성 토큰
vllm:e2e_request_latency_seconds   요청 전체 지연시간
```
#### 2. GPU 하드웨어 메트릭 (DCGM Exporter) ####
```
DCGM_FI_DEV_GPU_UTIL               GPU 연산 사용률 (%)       // 설정 우선 순위 - 3
DCGM_FI_DEV_MEM_COPY_UTIL          GPU 메모리 대역폭 사용률
DCGM_FI_DEV_FB_USED                GPU 메모리 사용량 (MB)
DCGM_FI_DEV_GPU_TEMP               GPU 온도
DCGM_FI_PROF_SM_ACTIVE             SM(Streaming Multiprocessor) 활성률
```
#### 3. 인프라 메트릭 ####
```
container_cpu_usage_seconds_total  CPU 사용률
container_memory_usage_bytes       메모리 사용량
```

## 테스트 하기 ##
```bash
for i in $(seq 1 100); do
  curl -s http://localhost:8080/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{
      "model": "qwen",
      "messages": [{"role": "user", "content": "Write a 1000 word essay about AI"}],
      "max_tokens": 1000
    }' &
done
wait
```

