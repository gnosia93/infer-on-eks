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

#### 2.2 istiod 설정 파일 ####

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

#### 2.3 istio-base 설치 ####

```
helm install istio-base istio/base -n istio-system --create-namespace \
  --version ${ISTIO_VERSION} --set defaultRevision=default

helm ls -n istio-system
kubectl get crd -o name | grep 'istio.io'
```

`defaultRevision=default`는 istio-base가 만드는 설정 검증 웹훅을 기본 리비전의 istiod에 연결한다. 리비전을 따로 나누지 않는 이 구성에서는 그대로 둔다.

[예상 결과]
```
NAME         NAMESPACE      REVISION  ...  STATUS    CHART         APP VERSION
istio-base   istio-system   1         ...  deployed  base-1.32.0   1.32.0
```

CRD 목록에 `destinationrules.networking.istio.io`, `telemetries.telemetry.istio.io`, `peerauthentications.security.istio.io` 등이 보이면 된다.

#### 2.4 istiod 설치 ####

```
helm install istiod istio/istiod -n istio-system \
  --version ${ISTIO_VERSION} -f istiod-values.yaml --wait

kubectl get pods -n istio-system
kubectl get mutatingwebhookconfiguration | grep istio
istioctl version
```

[예상 결과]
```
NAME                      READY   STATUS    RESTARTS   AGE
istiod-<해시>-<해시>       1/1     Running   0          1m
```
```
istio-sidecar-injector   ...
```
```
client version: 1.32.0
control plane version: 1.32.0
data plane version: none
```

- **주입 웹훅:** `istio-sidecar-injector`가 사이드카 주입 웹훅이다. 파드가 만들어질 때 3절의 레이블을 보고 사이드카를 넣는다.
- **data plane version:** 아직 사이드카가 들어간 파드가 없어서 `none`이다.
- **mTLS 모드:** 기본값인 PERMISSIVE로 둔다. 메시 밖에 있는 ALB가 보내는 평문 요청을 LiteLLM 사이드카가 받아야 하기 때문이다. 그래서 PeerAuthentication은 만들지 않는다.
- **네임스페이스 레이블:** `llm-serving` 네임스페이스에 `istio-injection` 레이블을 붙이지 않는다. 붙이면 vLLM 파드와 벤치마크 파드에도 사이드카가 들어간다.

### 3. LiteLLM 파드에 사이드카 주입 ###

#### 3.1 주입 방식 ####

- **주입 웹훅:** 파드가 만들어질 때 istiod의 주입 웹훅이 `sidecar.istio.io/inject: "true"` 레이블을 확인한다. 레이블이 있으면 파드 spec에 istio-init과 istio-proxy를 추가한다.
- **istio-init:** 파드가 시작될 때 iptables 규칙을 만든다. 들어오는 트래픽은 15006 포트로, 나가는 트래픽은 15001 포트로 돌려 istio-proxy가 받게 한다. 그래서 LiteLLM 설정은 바꿀 필요가 없다.
- **istio-proxy:** Istio 1.27부터 네이티브 사이드카(`restartPolicy: Always`인 init 컨테이너)로 들어간다. litellm 컨테이너보다 먼저 뜨고, litellm 컨테이너가 끝난 뒤에 내려간다. 그래서 LiteLLM의 preStop 30초와 스트리밍 응답 대기가 끊기지 않는다.
- **적용 시점:** 레이블은 파드가 새로 만들어질 때만 반영된다. 이미 떠 있는 파드에는 사이드카가 붙지 않으므로 롤링 업데이트로 파드를 바꾼다.

#### 3.2 레이블 추가 ####

```
kubectl patch deployment litellm -n llm-serving --type merge \
  -p '{"spec":{"template":{"metadata":{"labels":{"sidecar.istio.io/inject":"true"}}}}}'

kubectl rollout status deployment/litellm -n llm-serving
```

클러스터를 처음부터 다시 만들 때 빠지지 않도록, LiteLLM 배포 장의 Deployment 매니페스트에도 같은 레이블을 넣어 둔다.

```yaml
  template:
    metadata:
      labels:
        app.kubernetes.io/name: litellm
        app.kubernetes.io/component: llm-gateway
        sidecar.istio.io/inject: "true"     # 추가. 이 파드에만 사이드카를 주입
```

#### 3.3 확인 ####

```
kubectl get pods -n llm-serving -l app.kubernetes.io/name=litellm

kubectl get pods -n llm-serving -l app.kubernetes.io/name=litellm \
  -o jsonpath='{range .items[*]}{.metadata.name}{"  init="}{.spec.initContainers[*].name}{"  main="}{.spec.containers[*].name}{"\n"}{end}'

istioctl proxy-status
```

[예상 결과]
```
NAME                    READY   STATUS    RESTARTS   AGE
litellm-<해시>-<해시>    2/2     Running   0          1m
litellm-<해시>-<해시>    2/2     Running   0          2m
```
```
litellm-<해시>-<해시>  init=istio-init istio-proxy  main=litellm
litellm-<해시>-<해시>  init=istio-init istio-proxy  main=litellm
```

- **READY:** 파드마다 `2/2`(litellm, istio-proxy)이면 된다.
- **컨테이너 위치:** `istio-proxy`가 init 쪽에 보이면 네이티브 사이드카로 들어간 것이다.
- **설정 수신:** `istioctl proxy-status`에 LiteLLM 파드 두 개가 보이고 CDS, LDS, EDS, RDS 열이 `SYNCED`면, istiod에게서 설정을 받은 것이다.
- **기존 설정:** LiteLLM 파드의 `runAsNonRoot`, `readOnlyRootFilesystem`, `automountServiceAccountToken: false`는 그대로 둔다. istio-init과 istio-proxy는 자체 securityContext와 토큰 볼륨을 쓴다. HTTP 프로브는 Istio가 istio-agent를 거치도록 바꿔 주므로 고칠 필요가 없다.

사이드카를 붙인 뒤에도 LiteLLM을 거쳐 vLLM까지 요청이 가는지 확인한다.

```
MASTER_KEY=$(kubectl get secret litellm-secrets -n llm-serving -o jsonpath='{.data.LITELLM_MASTER_KEY}' | base64 -d)

kubectl -n llm-serving port-forward svc/litellm 4000:4000 >/dev/null 2>&1 &
PF_PID=$!; sleep 3

curl -s http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer ${MASTER_KEY}" \
  -H "Content-Type: application/json" \
  -H "session_id: chat-check-0001" \
  -d '{"model": "gemma-4-12b", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 16}' \
  | jq '.choices[0].message'

kill ${PF_PID}
```

응답 메시지가 나오면 된다.
