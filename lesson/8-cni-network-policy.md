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
