# AWS ALB + LiteLLM + Istio + vLLM Prefix Caching 아키텍처 가이드

**AWS ALB → LiteLLM Pod (with Istio Sidecar) → vLLM GPU Pods** 구조로 직결하고, Istio `DestinationRule`의 **Consistent Hash**를 이용해 **vLLM의 Prefix Caching(KV Cache) 적중률을 극대화**하는 구성 가이드입니다.

ALB를 거친 외부 트래픽이 Istio IngressGateway 없이 파드 사이드카로 바로 인입되므로, **mTLS 설정(`PERMISSIVE`)**과 **헤더 전달(Header Propagation)**이 핵심입니다.

---

## 1. 트래픽 및 캐시 라우팅 아키텍처

```text
[Client] (HTTP Header: x-session-id: user-123)
   │
   ▼
[AWS ALB] (TargetGroup: IP 모드 → LiteLLM Pod IP 직결)
   │
   ▼
[LiteLLM Pod]
   ├─ (1) Istio Envoy Sidecar (인입: PERMISSIVE mTLS 허용)
   ├─ (2) LiteLLM App (x-session-id 헤더를 업스트림 요청으로 전달)
   └─ (3) Istio Envoy Sidecar (송출: x-session-id 해싱 → 특정 vLLM Pod 고정)
          │
          ▼
[vLLM GPU Pods] (동일 세션의 이전 KV Cache가 메모리에 남아있어 TTFT 대폭 단축)
```

---

## 2. 핵심 구현 단계별 설정

### ① AWS ALB → LiteLLM 직결 및 mTLS 우회 (`PeerAuthentication`)
Istio IngressGateway를 거치지 않고 AWS ALB가 LiteLLM 파드 IP로 직접 평문(HTTP) 트래픽을 쏘기 때문에, Mesh 기본 정책이 `STRICT` mTLS라면 연결이 거부됩니다. LiteLLM 파드에 한해 `PERMISSIVE` 모드를 적용해야 합니다.

```yaml
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: litellm-permissive-mtls
  namespace: llm-ns
spec:
  selector:
    matchLabels:
      app: litellm
  mtls:
    mode: PERMISSIVE # ALB(Mesh 외부)에서 오는 평문 트래픽 허용
```

* **ALB Ingress 필수 어노테이션:**
  ```yaml
  alb.ingress.kubernetes.io/target-type: ip
  alb.ingress.kubernetes.io/healthcheck-path: /health/readiness
  alb.ingress.kubernetes.io/load-balancing-attributes: idle_timeout.timeout_seconds=300
  ```

---

### ② LiteLLM의 세션 ID 헤더 전달 설정 (`config.yaml`)
LiteLLM이 클라이언트로부터 받은 `x-session-id` 헤더를 버리지 않고, 백엔드 vLLM을 호출할 때 그대로 복사해서 넘겨주어야 Envoy가 이 헤더를 읽고 해싱할 수 있습니다.

```yaml
model_list:
  - model_name: llama-3-70b
    litellm_params:
      model: hosted_vllm/meta-llama/Meta-Llama-3-70B-Instruct
      api_base: "http://vllm-service.llm-ns.svc.cluster.local:8000/v1"
      api_key: "EMPTY"

litellm_settings:
  drop_params: true
  # 클라이언트가 보낸 x-session-id 헤더를 vLLM 요청 헤더로 그대로 전달
  forward_client_headers_to_llm_api: true 

general_settings:
  master_key: "sk-1234"
  database_url: "postgresql://user:pass@postgres-host:5432/litellm"
  redis_host: "redis-host"
  redis_port: 6379
```

> **참고:** 만약 클라이언트가 헤더가 아닌 JSON Body의 `user` 필드나 `metadata.session_id`로 값을 보낸다면, LiteLLM Custom Callback이나 Envoy Lua 필터를 통해 이를 `x-session-id` 헤더로 추출해 주는 작업이 추가로 필요합니다.

---

### ③ Istio `DestinationRule` (Consistent Hashing 적용)
LiteLLM 파드의 아웃바운드 Envoy 사이드카가 `x-session-id` 헤더 값을 기준으로 **Ring Hash**를 수행하여, 항상 동일한 vLLM 파드로 라우팅하도록 설정합니다.

```yaml
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: vllm-prefix-cache-dr
  namespace: llm-ns
spec:
  host: vllm-service.llm-ns.svc.cluster.local
  trafficPolicy:
    loadBalancer:
      consistentHash:
        httpHeaderName: "x-session-id" # 이 헤더 값을 기준으로 해싱하여 파드 고정
        minimumRingSize: 1024 # 파드 증감(Scale-out/in) 시 캐시 재분배(Re-hashing) 최소화
    connectionPool:
      http:
        http1MaxPendingRequests: 1024
        maxRequestsPerConnection: 100
    outlierDetection: # 특정 vLLM GPU 파드 장애 시 즉시 풀에서 제외
      consecutive5xxErrors: 3
      interval: 10s
      baseEjectionTime: 30s
```

---

### ④ vLLM Prefix Caching 활성화 옵션
Istio가 동일한 파드로 요청을 꽂아주더라도 vLLM 엔진 단에서 Automatic Prefix Caching(APC)이 켜져 있어야 GPU 메모리(KV Cache)를 재사용합니다.

* **vLLM 실행 커맨드 플래그:**
  ```bash
  vllm serve meta-llama/Meta-Llama-3-70B-Instruct \
    --enable-prefix-caching \
    --gpu-memory-utilization 0.90
  ```

---

## 3. 아키텍처 운영 시 핵심 체크리스트

| 점검 항목 | 설명 및 권장 조치 |
| :--- | :--- |
| **헤더 누락 시 Fallback** | 요청에 `x-session-id` 헤더가 없으면 Envoy는 기본적으로 **랜덤(Random)**으로 파드를 선택합니다. 장애는 나지 않지만 캐시 히트율이 떨어지므로 클라이언트단에서 UUID 등을 필수로 주입하도록 강제하세요. |
| **K8s Service 포트 이름** | `vllm-service`의 `ports[].name`을 반드시 **`http`** 또는 `http-vllm`처럼 `http` 접두사로 지정해야 합니다. 이름이 `tcp`이거나 비어있으면 Istio가 L7(HTTP 헤더)을 읽지 못해 해싱이 작동하지 않습니다. |
| **헤더 대소문자** | HTTP/2 환경에서는 헤더 이름이 소문자로 변환되므로 `DestinationRule`과 클라이언트 모두 소문자(`x-session-id`)로 통일하는 것이 안전합니다. |
| **스케일링 시 캐시 유실** | vLLM 파드 개수가 변하면 일부 세션의 해시 매핑이 바뀌어 초기 1회 캐시 미스(Cache Miss)가 발생합니다. `minimumRingSize`를 크게 잡으면 영향을 받는 세션 비율을 최소화할 수 있습니다. |
