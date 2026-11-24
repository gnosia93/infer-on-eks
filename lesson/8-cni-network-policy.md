## vLLM NetworkPolicy ##

vLLM 파드의 8000 포트로 들어오는 트래픽을 아래 출발지에서만 받도록 막는다. 대상은 vLLM 파드뿐이고 나가는 트래픽(S3, STS)은 막지 않는다. LiteLLM 파드에는 정책을 걸지 않으므로 ALB → LiteLLM 경로도 그대로다.


| 허용하는 출발지 | 용도 |
| :--- | :--- |
| LiteLLM 파드 (`llm-serving`, `app.kubernetes.io/name=litellm`) | 추론 요청 |
| Prometheus 파드 (`monitoring`, `app.kubernetes.io/name=prometheus`) | `/metrics` 수집 (KEDA가 쓰는 지표) |
| `vllm-client=true` 레이블을 붙인 파드 (`llm-serving`) | 벤치마크, 부하 테스트 |


### 1. VPC CNI 네트워크 정책 켜기 ###

NetworkPolicy 객체는 VPC CNI의 네트워크 정책 기능이 켜져 있어야 실제로 적용된다. 기능이 꺼져 있으면 정책을 만들어도 아무것도 막지 않는다. AWS 문서 기준으로 VPC CNI 1.21 이상이 필요하다.

```
# 현재 버전과 설정 확인
aws eks describe-addon --cluster-name "${CLUSTER_NAME}" --addon-name vpc-cni \
  --query 'addon.[addonVersion, configurationValues]' --output text
```
* 버전이 1.21 미만일 때: 먼저 애드온을 올린다. VPC CNI는 한 번에 한 마이너 버전씩 올리는 것이 권장된다.
* configurationValues가 비어 있지 않을 때: 아래 명령은 설정 JSON 전체를 바꾼다. 기존 JSON에 "enableNetworkPolicy": "true"를 더해서 넣는다.

```
aws eks update-addon --cluster-name "${CLUSTER_NAME}" --addon-name vpc-cni \
  --resolve-conflicts PRESERVE \
  --configuration-values '{"enableNetworkPolicy": "true"}'

aws eks wait addon-active --cluster-name "${CLUSTER_NAME}" --addon-name vpc-cni
kubectl rollout status daemonset/aws-node -n kube-system
kubectl get pods -n kube-system -l k8s-app=aws-node
```
aws-node 파드가 모두 2/2 Running이면 켜진 것이다. 두 번째 컨테이너가 정책을 적용하는 aws-network-policy-agent다.

클러스터를 다시 만들 때 이 설정이 빠지지 않도록 cluster.yaml의 vpc-cni 항목에도 적어 둔다.
```
addons:
  - name: vpc-cni
    configurationValues: '{"enableNetworkPolicy": "true"}'
    podIdentityAssociations:
      ...
```

### 2. NetworkPolicy 만들기 ###
먼저 Prometheus 파드에 예상한 레이블이 붙어 있는지 확인한다. prometheus-kube-prometheus-stack-prometheus-0이 나오면 된다.

```
kubectl get pods -n monitoring -l app.kubernetes.io/name=prometheus
```

```
kubectl apply -f - <<'EOF'
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: gemma4-12b-vllm-ingress
  namespace: llm-serving
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: gemma4-12b-vllm     # vLLM 파드에만 적용
  policyTypes:
    - Ingress                                     # 나가는 트래픽(S3, STS)은 막지 않음
  ingress:
    - from:
        - podSelector:                            # LiteLLM 파드 (같은 네임스페이스)
            matchLabels:
              app.kubernetes.io/name: litellm
        - podSelector:                            # 레이블을 붙인 벤치마크·부하 테스트 파드
            matchLabels:
              vllm-client: "true"
      ports:
        - protocol: TCP
          port: 8000
    - from:
        - namespaceSelector:                      # monitoring 네임스페이스의
            matchLabels:
              kubernetes.io/metadata.name: monitoring
          podSelector:                            # Prometheus 파드 (두 조건을 모두 만족해야 함)
            matchLabels:
              app.kubernetes.io/name: prometheus
      ports:
        - protocol: TCP
          port: 8000
EOF
```
* Prometheus 규칙: namespaceSelector와 podSelector가 같은 항목 안에 있어서 AND 조건이다. 앞에 -를 붙여 따로 쓰면 OR가 되어 monitoring 네임스페이스의 모든 파드가 허용되므로 들여쓰기를 바꾸지 않는다.
* 포트: VPC CNI는 Service 포트와 컨테이너 포트가 같아야 정책이 맞게 적용된다. vLLM Service는 8000 → 8000이라 조건을 만족한다.
* Istio를 붙인 뒤: LiteLLM 사이드카도 LiteLLM 파드 IP에서 출발하므로 첫 번째 규칙에 그대로 걸린다.

### 3. 벤치마크·부하 테스트 파드에 레이블 추가 ###
정책을 적용한 뒤에는 vLLM을 직접 호출하는 파드에 레이블이 없으면 연결이 막힌다. 해당하는 파드는 4장의 vllm-bench와 KEDA 가이드 7절의 vllm-load다. 두 파드의 metadata에 레이블을 추가한다.

```
metadata:
  name: vllm-bench            # vllm-load도 같은 방식
  namespace: llm-serving
  labels:
    vllm-client: "true"       # 추가
```
AWS 문서에 따르면 Deployment나 Job 없이 단독으로 만든 파드는 정책 처리가 불안정할 수 있다. 레이블을 붙였는데도 벤치마크가 막히면 같은 파드 spec을 Job의 spec.template에 넣어 실행한다.

### 4. 확인 ###
```
# 1) vLLM 파드가 Ready를 유지하는지 (kubelet 헬스 체크가 막히지 않았는지)
kubectl get pods -n llm-serving -l app.kubernetes.io/name=gemma4-12b-vllm

URL=http://gemma4-12b-vllm.llm-serving.svc.cluster.local:8000/health

# 2) 레이블이 없는 파드 → 000 (5초 시간 초과, 막힘)
kubectl run np-deny -n llm-serving --rm -it --restart=Never --image=curlimages/curl:8.23.0 \
  --command -- sh -c "sleep 10; curl -s -m 5 -o /dev/null -w '%{http_code}\n' $URL"

# 3) vllm-client=true 레이블을 붙인 파드 → 200 (허용)
kubectl run np-allow -n llm-serving --rm -it --restart=Never --image=curlimages/curl:8.23.0 \
  --labels=vllm-client=true \
  --command -- sh -c "sleep 10; curl -s -m 5 -o /dev/null -w '%{http_code}\n' $URL"
```
* sleep 10을 넣은 이유: 새 파드의 IP가 vLLM 쪽 허용 목록에 반영되기까지 몇 초가 걸린다. 그래서 테스트 명령에 sleep 10을 넣었다.
* LiteLLM 경로: LiteLLM 가이드 5절의 "2) session_id 헤더를 넣은 정상 요청"을 다시 보내 응답이 오는지 본다.
* Prometheus 수집: KEDA 가이드 3절의 수집 대상 확인 명령에서 vLLM 파드의 health가 계속 up인지 본다. down이 되면 KEDA 지표가 비어 스케일링이 멈춘다.

### 5. 되돌리기 ###
문제가 생기면 정책만 지워도 바로 모든 트래픽이 다시 허용된다. VPC CNI의 네트워크 정책 기능은 켜 둔 채로 두어도 된다. 정책이 없는 파드에는 아무 영향이 없다.

```
kubectl delete networkpolicy gemma4-12b-vllm-ingress -n llm-serving
```
