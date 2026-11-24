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

### 4. DestinationRule 만들기 ###

DestinationRule은 특정 Service로 가는 트래픽에 적용할 부하 분산 방식을 정한다. 여기서는 vLLM Service로 가는 요청을 `x-session-id` 해시로 나누게 한다.

```
kubectl apply -f - <<'EOF'
apiVersion: networking.istio.io/v1
kind: DestinationRule
metadata:
  name: gemma4-12b-vllm
  namespace: llm-serving
spec:
  host: gemma4-12b-vllm.llm-serving.svc.cluster.local
  trafficPolicy:
    loadBalancer:
      consistentHash:
        httpHeaderName: x-session-id      # LiteLLM 훅이 vLLM 쪽 요청에 붙이는 헤더
        ringHash:
          minimumRingSize: 1024
      localityLbSetting:
        enabled: false                    # AZ와 상관없이 모든 사이드카가 같은 결과를 내도록
EOF
```

| 항목 | 설명 |
|---|---|
| `host` | LiteLLM `api_base`가 가리키는 vLLM Service의 FQDN이다. 다르면 규칙이 적용되지 않는다. |
| `httpHeaderName` | 이 헤더 값을 해시한다. 헤더가 없는 요청은 무작위로 분산된다. |
| `ringHash` | 링 해시를 쓴다고 명시한다. Envoy 문서에 따르면 Maglev는 호스트가 빠질 때 링 해시보다 약 두 배 많은 키가 옮겨 간다. KEDA로 파드 수가 자주 바뀌므로 링 해시를 고른다. `minimumRingSize`는 가상 노드 수이고, 기본값과 같은 1024다. |
| `localityLbSetting.enabled: false` | LiteLLM 파드는 AZ마다 하나씩 있다. locality 부하 분산이 켜지면 사이드카마다 자기 AZ의 vLLM 파드를 먼저 골라서, 같은 세션이 다른 파드로 갈 수 있다. Istio 문서도 consistent hash와 locality 부하 분산을 함께 쓰지 말라고 경고한다. |

- **VirtualService:** 만들지 않는다. DestinationRule만으로 이 Service로 가는 모든 요청에 적용된다.
- **outlierDetection:** 넣지 않는다. 잠깐 제외되는 파드가 생길 때마다 해시 링이 다시 만들어져 세션이 옮겨 간다.

```
kubectl get destinationrule -n llm-serving
istioctl analyze -n llm-serving
```

`istioctl analyze`에 Error나 Warning이 없으면 된다. 네임스페이스에 주입 레이블이 없다는 Info 메시지가 나올 수 있다. 이 구성은 파드 단위로 주입하므로 그 메시지는 무시한다.

### 5. 접근 로그 켜기 (확인용) ###

2.2절에서 정의한 `session-access-log` 형식을 LiteLLM 사이드카의 아웃바운드 요청에만 켠다.

```
kubectl apply -f - <<'EOF'
apiVersion: telemetry.istio.io/v1
kind: Telemetry
metadata:
  name: litellm-session-log
  namespace: llm-serving
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: litellm
  accessLogging:
    - providers:
        - name: session-access-log
      match:
        mode: CLIENT                      # LiteLLM에서 나가는 요청(vLLM 쪽)만 기록
EOF
```

- **mode: CLIENT:** 이 파드가 보내는 쪽일 때만 기록한다. ALB에서 들어오는 요청은 기록하지 않는다.
- **로그 내용:** 로그에는 `session=<x-session-id 값> upstream=<vLLM 파드 IP:8000>`이 남는다.
- **정리 시점:** 세션 ID는 사용자를 구분하는 값이다. 그래서 확인이 끝나면 6.4절에서 이 설정을 지운다.

### 6. 동작 확인 ###

#### 6.1 사이드카 설정 확인 ####

```
LITELLM_POD=$(kubectl get pod -n llm-serving -l app.kubernetes.io/name=litellm -o jsonpath='{.items[0].metadata.name}')
VLLM_HOST=gemma4-12b-vllm.llm-serving.svc.cluster.local

# 1) 부하 분산 방식
istioctl proxy-config cluster "${LITELLM_POD}.llm-serving" --fqdn "${VLLM_HOST}" -o json \
  | jq '.[] | select(.name | startswith("outbound|8000")) | {name, lbPolicy, ringHashLbConfig}'

# 2) 해시 키
istioctl proxy-config route "${LITELLM_POD}.llm-serving" --name 8000 -o json \
  | jq '.[].virtualHosts[] | select(any(.domains[]; startswith("gemma4-12b-vllm"))) | .routes[].route.hashPolicy'

# 3) 해시 대상 엔드포인트
istioctl proxy-config endpoint "${LITELLM_POD}.llm-serving" --cluster "outbound|8000||${VLLM_HOST}"
```

[예상 결과]
```json
{
  "name": "outbound|8000||gemma4-12b-vllm.llm-serving.svc.cluster.local",
  "lbPolicy": "RING_HASH",
  "ringHashLbConfig": {
    "minimumRingSize": "1024"
  }
}
```
```json
[
  {
    "header": {
      "headerName": "x-session-id"
    }
  }
]
```
```
ENDPOINT                 STATUS      OUTLIER CHECK     CLUSTER
<vLLM 파드1 IP>:8000     HEALTHY     OK                outbound|8000||gemma4-12b-vllm.llm-serving.svc.cluster.local
```

엔드포인트 목록에는 Ready인 vLLM 파드만 `HEALTHY`로 나온다. 해시는 이 목록 안에서만 고른다.

#### 6.2 세션별 라우팅 확인 ####

vLLM 파드를 2개로 고정한다. 그다음 LiteLLM 파드 2개를 차례로 거쳐, 세션 3개를 세션마다 3번씩 보낸다. 두 번째 GPU 노드가 뜨고 파드가 Ready가 되기까지 약 7분이 걸린다.

```
# vLLM을 2개로 고정 (KEDA 자동 조절을 잠시 멈춤)
kubectl annotate scaledobject gemma4-12b-vllm -n llm-serving \
  autoscaling.keda.sh/paused-replicas="2" --overwrite
kubectl rollout status deployment/gemma4-12b-vllm -n llm-serving --timeout=15m
kubectl get pods -n llm-serving -l app.kubernetes.io/name=gemma4-12b-vllm -o wide

for POD in $(kubectl get pod -n llm-serving -l app.kubernetes.io/name=litellm -o name); do
  kubectl -n llm-serving port-forward "${POD}" 4000:4000 >/dev/null 2>&1 &
  PF_PID=$!
  sleep 3
  for SID in chat-aaaa-0001 chat-bbbb-0002 chat-cccc-0003; do
    for i in 1 2 3; do
      curl -s -o /dev/null -w "${POD##*/} ${SID} %{http_code}\n" http://localhost:4000/v1/chat/completions \
        -H "Authorization: Bearer ${MASTER_KEY}" \
        -H "Content-Type: application/json" \
        -H "session_id: ${SID}" \
        -d '{"model": "gemma-4-12b", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 8}'
    done
  done
  kill "${PF_PID}"; wait "${PF_PID}" 2>/dev/null
done
```

모든 줄의 응답 코드가 200이어야 한다. 그다음 두 LiteLLM 사이드카의 로그를 모아, 세션별로 어느 vLLM 파드로 갔는지 센다.

```
kubectl logs -n llm-serving -l app.kubernetes.io/name=litellm -c istio-proxy --tail=-1 \
  | grep -o 'session=chat-[^ ]* upstream=[^ ]*:8000' | sort | uniq -c
```

[예상 결과] (IP는 환경마다 다르고, 어느 세션이 어느 파드로 갈지는 해시로 정해진다)
```
      6 session=chat-aaaa-0001 upstream=<vLLM 파드1 IP>:8000
      6 session=chat-bbbb-0002 upstream=<vLLM 파드2 IP>:8000
      6 session=chat-cccc-0003 upstream=<vLLM 파드1 IP>:8000
```

- **정상 결과:** 세션마다 줄이 하나씩 나오고 숫자가 6(요청 3번 × LiteLLM 파드 2개)이면 정상이다. 같은 세션이 어느 LiteLLM 파드를 거쳐도 같은 vLLM 파드로 갔다는 뜻이다.
- **파드 맞추기:** upstream IP가 어느 vLLM 파드인지는 위 `kubectl get pods -o wide`의 IP 열과 맞춰 본다.
- **같은 파드에 몰린 세션:** 세션이 3개뿐이라 두 세션이 같은 파드로 갈 수도 있다. 확인할 것은 한 세션이 파드 하나로만 간다는 점이다.
- **줄이 두 개 이상일 때:** 한 세션에 줄이 두 개 이상 나오면 8절 문제 해결을 본다.


#### 6.3 헤더 없는 요청 확인 ####

세션 헤더 없이 6번 보내면 요청이 무작위로 나뉜다.

```
kubectl -n llm-serving port-forward svc/litellm 4000:4000 >/dev/null 2>&1 &
PF_PID=$!; sleep 3

for i in $(seq 6); do
  curl -s -o /dev/null http://localhost:4000/v1/chat/completions \
    -H "Authorization: Bearer ${MASTER_KEY}" \
    -H "Content-Type: application/json" \
    -d '{"model": "gemma-4-12b", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 8}'
done
kill ${PF_PID}

kubectl logs -n llm-serving -l app.kubernetes.io/name=litellm -c istio-proxy --tail=-1 \
  | grep -o 'session=- upstream=[^ ]*:8000' | sort | uniq -c
```

`session=-` 줄이 vLLM 파드 두 개에 나뉘어 나오면 된다. 무작위라서 한쪽에 더 많이 갈 수 있다. `:8000`으로 거른 것은 LiteLLM이 기동할 때 외부로 나가는 요청(443)을 빼기 위해서다.

#### 6.4 확인 후 되돌리기 ####

```
kubectl annotate scaledobject gemma4-12b-vllm -n llm-serving autoscaling.keda.sh/paused-replicas-
kubectl delete telemetry litellm-session-log -n llm-serving
```

### 7. 운영할 때 알아 둘 점 ###

- **파드 수가 바뀔 때:** KEDA가 vLLM 파드를 늘리거나 줄이면 해시 링이 다시 만들어진다. 파드가 N개일 때 하나가 늘거나 줄면 세션의 약 1/N이 다른 파드로 옮겨 간다. 옮겨 간 세션은 첫 요청에서 prefix 캐시를 다시 채운다. 롤링 업데이트도 마찬가지다.
- **부하 쏠림:** 해시는 부하를 보지 않는다. 긴 세션이 한 파드에 몰리면 그 파드만 바빠진다. KEDA 트리거는 전체 합계라서 이런 쏠림에는 반응하지 않는다. 그래서 `max by (pod) (vllm:num_requests_running{namespace="llm-serving"})`를 함께 본다.
- **재시도:** Istio 기본 재시도는 연결 실패처럼 요청이 vLLM에서 처리되기 전에 실패한 경우를 다시 보낸다. 그래서 같은 응답이 두 번 생성되지는 않는다. 다만 재시도는 다른 파드로 가므로 그 요청은 캐시를 쓰지 못한다.
- **타임아웃:** Istio 라우트에는 기본 타임아웃이 없다. 요청 시간의 상한은 LiteLLM `timeout`(600초)과 ALB idle timeout(600초)이다.
- **Istio 업그레이드:** 컨트롤 플레인(istiod)을 먼저 올리고, LiteLLM 파드를 재시작해 사이드카를 새 버전으로 바꾼다. 데이터 플레인(사이드카)은 컨트롤 플레인보다 새 버전이면 안 된다.
- **vLLM 파드에 사이드카를 넣지 않는 이유:**
  - 해시는 LiteLLM 쪽 사이드카만으로 충분하다.
  - vLLM 사이드카가 없으면 S3 가중치 스트리밍이 Envoy를 거치지 않는다.
  - Prometheus가 평문으로 지표를 수집하는 데도 문제가 없다.
  - 사이드카 간 mTLS가 필요해지면 그때 넣고, 443 포트는 사이드카에서 제외한다.

### 8. 문제 해결 ###

| 증상 | 확인할 것 |
|---|---|
| 같은 세션이 여러 vLLM 파드로 간다 | 6.1에서 lbPolicy가 `RING_HASH`인지, hashPolicy의 헤더가 `x-session-id`인지 본다. DestinationRule의 `host` 오타도 확인한다. |
| 세션 헤더를 보냈는데 로그에 `session=-`로 찍힌다 | LiteLLM 훅이 헤더를 붙이지 않았다. 클라이언트가 `session_id` 또는 `x-session-id`를 보냈는지, ConfigMap의 `callbacks` 설정이 맞는지 본다. |
| LiteLLM 파드마다 다른 vLLM 파드로 간다 | `localityLbSetting.enabled: false`가 적용됐는지 본다. 두 LiteLLM 파드에서 6.1의 3)을 실행해 엔드포인트 목록이 같은지도 비교한다. |
| 사이드카가 주입되지 않는다 | 파드 템플릿에 레이블이 있는지, 레이블을 추가한 뒤 파드가 다시 만들어졌는지 본다. 파드 이벤트에 `failed calling webhook`이 있으면 컨트롤 플레인이 istiod의 15017 포트에 닿지 못하는 것이다. 노드 보안 그룹을 확인한다. |
| ALB가 502를 낸다 | mTLS가 STRICT로 바뀌지 않았는지 본다(`kubectl get peerauthentication -A`). ALB는 평문으로 보낸다. |
| 응답이 503이고 로그의 RESPONSE_FLAGS가 `UH` | 정상 엔드포인트가 없다. vLLM 파드가 Ready인지 본다. |
| vLLM 호출이 시간 초과된다 | vLLM NetworkPolicy가 LiteLLM 파드(`app.kubernetes.io/name=litellm`)를 허용하는지 본다. |
| 설정이 반영됐는지 모르겠다 | `istioctl analyze -n llm-serving`과 `istioctl proxy-status`로 설정 오류와 동기화 상태를 본다. |

### 9. 정리 ###

```
kubectl delete telemetry litellm-session-log -n llm-serving --ignore-not-found
kubectl delete destinationrule gemma4-12b-vllm -n llm-serving

# 사이드카 제거: 레이블을 지우면 롤링 업데이트로 사이드카 없는 파드로 바뀐다
kubectl patch deployment litellm -n llm-serving --type json \
  -p '[{"op": "remove", "path": "/spec/template/metadata/labels/sidecar.istio.io~1inject"}]'
kubectl rollout status deployment/litellm -n llm-serving

helm uninstall istiod -n istio-system
helm uninstall istio-base -n istio-system
kubectl delete namespace istio-system
```

- **JSON 패치 경로:** 레이블 이름의 `/`는 `~1`로 바꿔 적는다.
- **CRD 삭제:** Istio CRD는 남는다. 다시 설치하지 않을 때만 `kubectl get crd -o name | grep 'istio.io' | xargs kubectl delete`로 지운다. CRD를 지우면 그 종류의 리소스가 모두 함께 지워진다.

## 참고자료 ##

* [Istio, Destination Rule](https://istio.io/latest/docs/reference/config/networking/destination-rule/)
* [Istio, Telemetry API](https://istio.io/latest/docs/reference/config/telemetry/)
* [Istio, Global Mesh Options (extensionProviders)](https://istio.io/latest/docs/reference/config/istio.mesh.v1alpha1/)
* [Istio, Install with Helm](https://istio.io/latest/docs/setup/install/helm/)
* [Istio, Supported Releases](https://istio.io/latest/docs/releases/supported-releases/)
* [Istio 1.27 Upgrade Notes (네이티브 사이드카 기본값)](https://istio.io/latest/news/releases/1.27.x/announcing-1.27/upgrade-notes/)
* [Envoy, Supported load balancers (Ring hash, Maglev)](https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/upstream/load_balancing/load_balancers)

