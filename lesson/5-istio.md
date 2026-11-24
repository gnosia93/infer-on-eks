같은 세션의 요청을 계속 같은 vLLM 파드로 보내면, 그 파드에 남아 있는 앞선 대화의 KV 캐시(prefix 캐시)를 다시 쓸 수 있다. 멀티턴 대화에서는 prefill이 줄어 TTFT가 짧아진다. 이 장에서는 Istio를 설치하고 LiteLLM 파드에 사이드카(Envoy)를 붙여, 사이드카가 `x-session-id` 헤더 값으로 vLLM 파드를 고르게 한다.

### 트래픽 흐름 ###

```
클라이언트 (헤더 session_id)
  → ALB (IP 모드, LiteLLM 파드 IP:4000으로 직접)
  → LiteLLM 파드의 istio-proxy (인바운드, 평문 허용)
  → litellm 컨테이너 (session_id를 검사해 x-session-id 헤더로 붙임)
  → LiteLLM 파드의 istio-proxy (아웃바운드, x-session-id 해시로 vLLM 파드 선택)
  → vLLM 파드 IP:8000 (vLLM 파드에는 사이드카 없음)
```

- **해시하는 위치:** 해시는 요청을 보내는 쪽, 즉 LiteLLM 파드의 사이드카가 한다. vLLM 파드에는 사이드카를 넣지 않는다.
- **해시 키:** 사이드카가 보는 것은 LiteLLM이 vLLM으로 보내는 요청이다. 그래서 해시 키는 클라이언트가 보낸 `session_id`가 아니라, LiteLLM 훅이 붙인 `x-session-id`다.
- **파드 간 일관성:** LiteLLM 사이드카는 모두 istiod에게서 같은 vLLM 엔드포인트 목록을 받는다. 그래서 어느 LiteLLM 파드를 거쳐도 같은 세션은 같은 vLLM 파드로 간다.
- **연결 재사용 문제 해결:** 사이드카가 요청마다 vLLM 파드 IP를 직접 고른다. 그래서 kube-proxy가 연결 단위로 나눌 때 생기던 연결 재사용 문제(KEDA 장 9절)가 없어진다.

### Istio 구성 요소 ###

| 구성 요소 | 위치 | 역할 |
|---|---|---|
| istio-base | 클러스터 전체 | Istio CRD(DestinationRule, Telemetry 등), 기본 RBAC, 설정 검증 웹훅을 설치한다. |
| istiod | `istio-system` 네임스페이스 | 사이드카에 라우팅·부하 분산 설정과 엔드포인트 목록을 보낸다. mTLS 인증서를 발급하고, 사이드카 주입 웹훅을 처리한다. |
| istio-init | 사이드카가 들어간 파드 (init 컨테이너) | iptables 규칙을 만들어 파드로 들어오고 나가는 트래픽을 istio-proxy로 돌린다. |
| istio-proxy | 사이드카가 들어간 파드 (네이티브 사이드카) | Envoy와 istio-agent로 구성된다. 실제로 요청을 받아 해시로 vLLM 파드를 고른다. |

### 사전 준비 ###

| 항목 | 조건 |
|---|---|
| EKS | 1.34. Istio 1.32가 지원하는 Kubernetes는 1.33~1.37이다. |
| LiteLLM | LiteLLM 배포 장의 Deployment. `session_hook.py`가 `session_id`를 `x-session-id`로 바꿔 vLLM 쪽 요청에 붙인다. |
| vLLM Service | `gemma4-12b-vllm`, ClusterIP(헤드리스 아님), 포트 이름 `http` |
| NetworkPolicy | vLLM NetworkPolicy를 적용했다면 LiteLLM 파드가 이미 허용돼 있으므로 그대로 둔다. |
| 도구 | helm, kubectl, jq. istioctl은 1절에서 설치한다. |

### 환경 설정 ###

```
export ISTIO_VERSION="1.32.0"

kubectl config current-context        # infer-on-eks 클러스터인지 확인
echo "Istio Version: ${ISTIO_VERSION}"
```

### 1. istioctl 설치 ###

istioctl은 Istio 설정을 확인하고 진단하는 CLI다. Istio 설치는 2절에서 Helm으로 하고, istioctl은 확인용으로만 쓴다. 클라이언트 버전은 설치할 Istio 버전과 맞춘다.

```
curl -sL https://istio.io/downloadIstio | ISTIO_VERSION=${ISTIO_VERSION} sh -
sudo install -m 0755 istio-${ISTIO_VERSION}/bin/istioctl /usr/local/bin/istioctl
istioctl version --remote=false
```

[예상 결과]
```
client version: 1.32.0
```

현재 디렉터리에 `istio-1.32.0/` 폴더가 생긴다. 예제(`samples/`)도 들어 있지만 이 장에서는 쓰지 않는다.

### 2. Istio 설치 ###

istio-base와 istiod만 설치한다. 외부 트래픽은 ALB가 LiteLLM 파드로 바로 보내므로 인그레스 게이트웨이는 설치하지 않는다.

```
helm repo add istio https://blob.istio.io/istio-release/charts
helm repo update

helm search repo istio/istiod --versions | head -5     # 1.32.0이 있는지 확인
```

#### 1. istiod 설정 파일 ####

`meshConfig`는 메시 전체에 적용되는 설정이다. 여기서는 확인용 접근 로그 형식(extensionProvider) 하나만 추가한다. 형식을 정의하기만 하므로 이 단계에서는 로그가 찍히지 않는다. 실제로 켜는 것은 5절의 Telemetry이고, LiteLLM 파드에만 켠다.

```
cat > istiod-values.yaml <<'EOF'
meshConfig:
  extensionProviders:
    # 확인용 접근 로그 형식: 세션 ID와 사이드카가 고른 vLLM 파드 IP를 남긴다
    - name: session-access-log
      envoyFileAccessLog:
        path: /dev/stdout
        logFormat:
          text: "[%START_TIME%] %REQ(:METHOD)% %REQ(X-ENVOY-ORIGINAL-PATH?:PATH)% %RESPONSE_CODE% %RESPONSE_FLAGS% session=%REQ(X-SESSION-ID)% upstream=%UPSTREAM_HOST% duration=%DURATION%ms"
EOF
```

| 로그 항목 | 뜻 |
|---|---|
| `%REQ(X-SESSION-ID)%` | 요청 헤더 `x-session-id`의 값. 헤더가 없으면 `-` |
| `%UPSTREAM_HOST%` | 사이드카가 고른 vLLM 파드의 IP:포트 |
| `%RESPONSE_FLAGS%` | Envoy가 남기는 실패 원인 코드. 정상이면 `-`, 정상 엔드포인트가 없으면 `UH` |
| `%DURATION%` | 요청 하나에 걸린 시간(ms) |
