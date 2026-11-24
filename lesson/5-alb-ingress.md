
## 서비스 엔드포인트 만들기: ALB Ingress ##

AWS Load Balancer Controller(LBC)를 설치하고 Ingress를 만들어, LiteLLM 파드 앞에 ALB를 둔다. ALB는 IP 모드로 LiteLLM 파드 IP를 타깃으로 직접 등록한다. 이 장의 ALB는 internal이라 VPC 안에서만 접근할 수 있다. 인터넷 공개는 8절에서 따로 다룬다.

### 구성 ###

```
클라이언트 (VPC 안: VS Code 서버, 클러스터 안의 파드 등)
  → ALB (internal, HTTP 80, idle timeout 600초, 접근 허용: VPC CIDR)
  → LiteLLM 파드 IP:4000 (target-type: ip, 파드 readiness gate)
  → (LiteLLM 사이드카가 x-session-id로 vLLM 파드 선택, Istio 장)
```

Ingress를 만들면 LBC가 아래 AWS 리소스를 만들고, Ingress를 지우면 함께 지운다.

| 리소스 | 설명 |
|---|---|
| ALB | internal 스킴, 프라이빗 서브넷 2개(AZ 2개)에 생성 |
| 리스너 | HTTP 80. 모든 경로(`/`)를 LiteLLM 타깃 그룹으로 보낸다. |
| 타깃 그룹 | IP 타입, 포트 4000. LiteLLM 파드 IP가 등록된다. |
| TargetGroupBinding | 타깃 그룹과 `litellm` Service를 잇는 쿠버네티스 리소스. 파드가 바뀌면 LBC가 타깃을 갱신한다. |
| 보안 그룹 | ALB용 보안 그룹(VPC CIDR → 80 허용)을 만든다. 노드 보안 그룹에는 ALB → 파드 4000 규칙을 추가한다. |

### 사전 준비 ###

| 항목 | 조건 |
|---|---|
| LiteLLM | LiteLLM 배포 장의 Deployment와 Service(`litellm`, ClusterIP, 포트 이름 `http` 4000) |
| Istio | Istio 장을 적용했다면 LiteLLM 사이드카는 PERMISSIVE여야 한다. ALB는 평문으로 보낸다. |
| 확인용 클라이언트 | internal ALB는 VPC 밖에서 접근할 수 없다. VS Code 서버가 같은 VPC에 없으면 6절의 클러스터 안 파드로 확인한다. |
| 도구 | aws, eksctl, helm, kubectl, jq |

### 환경 설정 ###

```
export AWS_REGION=$(aws ec2 describe-availability-zones --query 'AvailabilityZones[0].RegionName' --output text)
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export CLUSTER_NAME="infer-on-eks"
export VPC_ID=$(aws ec2 describe-vpcs --filters Name=tag:Name,Values="${CLUSTER_NAME}" --query "Vpcs[].VpcId" --output text)
export VPC_CIDR=$(aws ec2 describe-vpcs --vpc-ids "${VPC_ID}" --query "Vpcs[0].CidrBlock" --output text)
export LBC_VERSION="v3.6.3"           # AWS Load Balancer Controller
export LBC_CHART_VERSION="3.6.3"      # Helm 차트 버전

echo "AWS Region: ${AWS_REGION}"
echo "AWS Account ID: ${AWS_ACCOUNT_ID}"
echo "Cluster Name: ${CLUSTER_NAME}"
echo "VPC ID: ${VPC_ID} (${VPC_CIDR})"
```

### 1. AWS Load Balancer Controller 설치 ###

#### 1.1 설치 여부 확인 ####

```
kubectl get deployment aws-load-balancer-controller -n kube-system
```

`NotFound`가 나오면 1.2절부터 설치한다. 이미 있으면 2절로 넘어간다.

#### 1.2 IAM 정책 만들기 ####

LBC는 ALB, 타깃 그룹, 보안 그룹을 만들고 고치는 AWS API를 호출하므로 IAM 권한이 필요하다. 정책 파일은 설치할 LBC 버전에 맞는 것을 받는다.

```
curl -o lbc-iam-policy.json \
  https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/${LBC_VERSION}/docs/install/iam_policy.json

aws iam create-policy \
  --policy-name AWSLoadBalancerControllerIAMPolicy \
  --policy-document file://lbc-iam-policy.json

export LBC_POLICY_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:policy/AWSLoadBalancerControllerIAMPolicy"
echo "${LBC_POLICY_ARN}"
```

`EntityAlreadyExists` 오류가 나오면 같은 이름의 정책이 이미 있는 것이다. 그 정책을 그대로 쓴다.

#### 1.3 IRSA 서비스 어카운트 만들기 ####

vLLM의 S3 읽기 권한과 같은 방식(IRSA)으로 LBC 파드에 IAM 역할을 준다.

```
eksctl create iamserviceaccount \
  --cluster "${CLUSTER_NAME}" \
  --namespace kube-system \
  --name aws-load-balancer-controller \
  --role-name "${CLUSTER_NAME}-aws-lbc" \
  --attach-policy-arn "${LBC_POLICY_ARN}" \
  --override-existing-serviceaccounts \
  --region "${AWS_REGION}" \
  --approve

kubectl get sa aws-load-balancer-controller -n kube-system \
  -o jsonpath='{.metadata.annotations.eks\.amazonaws\.com/role-arn}'; echo
```

[예상 결과]
```
arn:aws:iam::<계정 ID>:role/infer-on-eks-aws-lbc
```

#### 1.4 Helm으로 설치 ####

```
helm repo add eks https://aws.github.io/eks-charts
helm repo update

helm install aws-load-balancer-controller eks/aws-load-balancer-controller \
  -n kube-system \
  --version "${LBC_CHART_VERSION}" \
  --set clusterName="${CLUSTER_NAME}" \
  --set serviceAccount.create=false \
  --set serviceAccount.name=aws-load-balancer-controller \
  --set region="${AWS_REGION}" \
  --set vpcId="${VPC_ID}"

kubectl rollout status deployment/aws-load-balancer-controller -n kube-system
kubectl get pods -n kube-system -l app.kubernetes.io/name=aws-load-balancer-controller
kubectl get ingressclass
```

[예상 결과]
```
NAME                                            READY   STATUS    RESTARTS   AGE
aws-load-balancer-controller-<해시>-<해시>       1/1     Running   0          1m
aws-load-balancer-controller-<해시>-<해시>       1/1     Running   0          1m
```
```
NAME   CONTROLLER            PARAMETERS   AGE
alb    ingress.k8s.aws/alb   <none>       1m
```

- **eks 저장소:** EFA 장에서 이미 추가했다면 `helm repo add`가 `already exists`를 출력한다. 그대로 진행하면 된다.
- **region, vpcId:** 이 값을 주면 LBC가 노드의 인스턴스 메타데이터(IMDS)를 거치지 않고 리전과 VPC를 찾는다.
- **IngressClass:** 차트가 `alb` IngressClass를 만든다. 4절의 Ingress는 `ingressClassName: alb`로 이 컨트롤러를 지정한다.
- **웹훅 포트:** LBC 웹훅은 컨트롤 플레인에서 노드의 9443 포트로 호출된다. eksctl로 만든 클러스터는 기본으로 허용돼 있다.
- **LoadBalancer Service 동작 변경:** LBC를 설치하면 새로 만드는 `type: LoadBalancer` Service는 CLB 대신 LBC가 만드는 NLB를 쓴다. EKS 장에서 설명한 CLB 동작과 달라진다.

### 2. ALB를 둘 서브넷 확인 ###

internal ALB는 프라이빗 서브넷에 둔다. ALB는 서로 다른 AZ의 서브넷이 2개 이상 필요하다. 서브넷을 Ingress에 직접 지정하므로, 서브넷 자동 검색용 태그(`kubernetes.io/role/internal-elb`)는 붙이지 않아도 된다.

```
export PRIVATE_SUBNETS=$(aws ec2 describe-subnets \
  --filters "Name=tag:Name,Values=IOE-priv-subnet-*" "Name=vpc-id,Values=${VPC_ID}" \
  --query "Subnets[].SubnetId" --output text | tr '\t' ',')
echo "${PRIVATE_SUBNETS}"
```

[예상 결과]
```
subnet-<AZ-a 프라이빗 서브넷>,subnet-<AZ-b 프라이빗 서브넷>
```

### 3. Ingress 만들기 ###

서브넷, VPC CIDR, 클러스터 이름을 셸 변수에서 넣기 위해 heredoc을 따옴표 없이(`<<EOF`) 쓴다.

```
kubectl apply -f - <<EOF
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: litellm
  namespace: llm-serving
  labels:
    app.kubernetes.io/name: litellm
  annotations:
    alb.ingress.kubernetes.io/scheme: internal
    alb.ingress.kubernetes.io/target-type: ip
    alb.ingress.kubernetes.io/subnets: ${PRIVATE_SUBNETS}
    alb.ingress.kubernetes.io/listen-ports: '[{"HTTP": 80}]'
    alb.ingress.kubernetes.io/inbound-cidrs: ${VPC_CIDR}
    alb.ingress.kubernetes.io/healthcheck-path: /health/liveliness
    alb.ingress.kubernetes.io/success-codes: "200"
    alb.ingress.kubernetes.io/load-balancer-attributes: idle_timeout.timeout_seconds=600,routing.http.drop_invalid_header_fields.enabled=false
    alb.ingress.kubernetes.io/target-group-attributes: deregistration_delay.timeout_seconds=180
    alb.ingress.kubernetes.io/tags: Project=${CLUSTER_NAME}
spec:
  ingressClassName: alb
  rules:
    - http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: litellm
                port:
                  name: http
EOF
```

| 애노테이션 | 값 | 설명 |
|---|---|---|
| `scheme` | `internal` | VPC 안에서만 접근할 수 있는 ALB를 만든다. 나중에 스킴을 바꾸면 ALB가 새로 만들어지고 DNS 이름도 바뀐다. |
| `target-type` | `ip` | LiteLLM 파드 IP를 타깃으로 직접 등록한다. 노드 포트를 거치지 않는다. |
| `subnets` | 프라이빗 서브넷 2개 | ALB를 둘 서브넷이다. |
| `listen-ports` | HTTP 80 | HTTPS는 7절에서 다룬다. |
| `inbound-cidrs` | VPC CIDR | ALB 보안 그룹에서 허용할 출발지다. 기본값이 `0.0.0.0/0`이므로 internal이어도 명시한다. |
| `healthcheck-path` | `/health/liveliness` | LiteLLM이 인증 없이 응답하는 가벼운 헬스 체크다. `/health`는 모델을 실제로 호출하므로 쓰지 않는다. |
| `idle_timeout.timeout_seconds` | 600 | 기본값 60초로는 긴 스트리밍 응답이 끊길 수 있어 늘린다. LiteLLM `timeout`(600초)과 같다. |
| `drop_invalid_header_fields.enabled` | false | `session_id`처럼 밑줄이 든 헤더를 통과시킨다. 기본값과 같지만 일부러 명시한다. |
| `deregistration_delay.timeout_seconds` | 180 | LiteLLM의 `terminationGracePeriodSeconds`(180초)와 맞춘다. 파드가 응답을 마치기 전에 ALB가 먼저 연결을 끊지 않게 한다. |
| `tags` | `Project=infer-on-eks` | ALB와 타깃 그룹에 붙는 태그. 비용을 구분할 때 쓴다. |

ALB가 만들어지기까지 2~3분 걸린다.

```
kubectl get ingress litellm -n llm-serving
kubectl describe ingress litellm -n llm-serving | sed -n '/^Events:/,$p'
```

[예상 결과]
```
NAME      CLASS   HOSTS   ADDRESS                                                                  PORTS   AGE
litellm   alb     *       internal-k8s-llmservi-litellm-<해시>.ap-northeast-2.elb.amazonaws.com    80      2m
```

Events에 `Successfully reconciled`가 보이면 된다. ADDRESS가 비어 있으면 10절 문제 해결을 본다.

ALB 상태와 속성을 확인한다.

```
export ALB_DNS=$(kubectl get ingress litellm -n llm-serving -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
export ALB_ARN=$(aws elbv2 describe-load-balancers \
  --query "LoadBalancers[?DNSName=='${ALB_DNS}'].LoadBalancerArn" --output text)

aws elbv2 describe-load-balancers --load-balancer-arns "${ALB_ARN}" \
  --query 'LoadBalancers[0].[Scheme, State.Code]' --output text

aws elbv2 describe-load-balancer-attributes --load-balancer-arn "${ALB_ARN}" \
  --query "Attributes[?Key=='idle_timeout.timeout_seconds' || Key=='routing.http.drop_invalid_header_fields.enabled']" \
  --output table
```

스킴이 `internal`, 상태가 `active`인지 본다. 속성은 `idle_timeout.timeout_seconds`가 600, `routing.http.drop_invalid_header_fields.enabled`가 false로 나오면 된다.

타깃 그룹에 LiteLLM 파드가 healthy로 등록됐는지 확인한다.

```
kubectl get targetgroupbinding -n llm-serving

export TG_ARN=$(kubectl get targetgroupbinding -n llm-serving -o jsonpath='{.items[0].spec.targetGroupARN}')
aws elbv2 describe-target-health --target-group-arn "${TG_ARN}" \
  --query 'TargetHealthDescriptions[].[Target.Id, Target.Port, TargetHealth.State]' --output table

kubectl get pods -n llm-serving -l app.kubernetes.io/name=litellm -o wide
```

LiteLLM 파드 IP 두 개가 포트 4000, `healthy`로 나오면 된다. 처음 1분 정도는 `initial`로 보일 수 있다.

### 4. 파드 readiness gate 켜기 ###

IP 모드에서는 쿠버네티스의 파드 Ready와 ALB 타깃의 healthy가 따로 판정된다. 롤링 업데이트 중에 새 파드가 쿠버네티스에서 먼저 Ready가 되면 문제가 생긴다. 그 파드가 ALB에서 healthy가 되기 전에 기존 파드가 내려가서 502가 날 수 있다. readiness gate를 켜면 ALB 타깃이 healthy가 된 뒤에야 파드가 Ready가 된다.

readiness gate는 파드가 만들어질 때 주입된다. 주입되려면 그 파드를 가리키는 TargetGroupBinding이 이미 있어야 한다. 그래서 3절의 Ingress를 먼저 만들고, 그 뒤에 네임스페이스에 레이블을 붙여 LiteLLM 파드를 다시 만든다.

```
kubectl label namespace llm-serving elbv2.k8s.aws/pod-readiness-gate-inject=enabled

kubectl rollout restart deployment/litellm -n llm-serving
kubectl rollout status deployment/litellm -n llm-serving

kubectl get pods -n llm-serving -l app.kubernetes.io/name=litellm -o wide
```

[예상 결과]
```
NAME                    READY   STATUS    RESTARTS   AGE   IP          NODE        NOMINATED NODE   READINESS GATES
litellm-<해시>-<해시>    2/2     Running   0          1m    <파드 IP>   <노드 이름>  <none>           1/1
litellm-<해시>-<해시>    2/2     Running   0          2m    <파드 IP>   <노드 이름>  <none>           1/1
```

- **READINESS GATES:** `1/1`이면 readiness gate가 주입되고 ALB에서 healthy인 상태다.
- **READY:** Istio 사이드카를 붙인 상태면 `2/2`, 붙이지 않았으면 `1/1`이다.
- **주입 대상:** 레이블은 네임스페이스 단위로 붙지만, 주입은 TargetGroupBinding이 가리키는 파드(LiteLLM)에만 된다. vLLM 파드는 ALB 타깃이 아니므로 바뀌지 않는다.

롤링 업데이트 때 파드는 다음 순서로 교체된다.

1. 새 파드가 뜨고 ALB 타깃에 등록된다.
2. 새 파드가 healthy가 되면 Ready가 되고, 기존 파드가 종료를 시작한다.
3. 기존 파드는 타깃에서 빠지고(draining) preStop 30초 동안 계속 요청을 받는다.
4. 그다음 진행 중인 응답을 마치고 내려간다.

### 5. HTTP 헤더와 경로 정리 ###

| 경로 | 인증 | 용도 |
|---|---|---|
| `/health/liveliness` | 없음 | ALB 헬스 체크 |
| `/v1/models` | 마스터 키 | 모델 목록 |
| `/v1/chat/completions` | 마스터 키 | 채팅 요청. `session_id`(또는 `x-session-id`) 헤더로 세션을 지정한다. |

클라이언트는 `Authorization: Bearer <마스터 키>`와 `session_id: <세션 ID>`를 보낸다. ALB는 두 헤더를 그대로 LiteLLM에 넘긴다.

### 6. 엔드포인트 확인 ###

VS Code 서버에서 실행한다.

```
MASTER_KEY=$(kubectl get secret litellm-secrets -n llm-serving -o jsonpath='{.data.LITELLM_MASTER_KEY}' | base64 -d)

# 1) 헬스 체크 (인증 없음) → "I'm alive!"
curl -s http://${ALB_DNS}/health/liveliness; echo

# 2) 키 없이 → 401
curl -s -o /dev/null -w '%{http_code}\n' http://${ALB_DNS}/v1/models

# 3) 모델 목록 → gemma-4-12b
curl -s http://${ALB_DNS}/v1/models -H "Authorization: Bearer ${MASTER_KEY}" | jq -r '.data[].id'

# 4) 채팅 요청 (session_id 헤더 포함)
curl -s http://${ALB_DNS}/v1/chat/completions \
  -H "Authorization: Bearer ${MASTER_KEY}" \
  -H "Content-Type: application/json" \
  -H "session_id: chat-alb-0001" \
  -d '{"model": "gemma-4-12b", "messages": [{"role": "user", "content": "안녕하세요"}], "max_tokens": 64}' \
  | jq '.choices[0].message'

# 5) 스트리밍 응답 (SSE)
curl -sN http://${ALB_DNS}/v1/chat/completions \
  -H "Authorization: Bearer ${MASTER_KEY}" \
  -H "Content-Type: application/json" \
  -H "session_id: chat-alb-0001" \
  -d '{"model": "gemma-4-12b", "stream": true, "messages": [{"role": "user", "content": "쿠버네티스를 세 문장으로 설명해 줘"}], "max_tokens": 128}'
```

- **스트리밍 응답:** `data: {...}` 줄이 차례로 나오고 마지막에 `data: [DONE]`이 나오면 ALB를 거친 스트리밍이 정상이다.
- **ALB DNS 조회:** ALB를 만든 직후에는 DNS가 조회되지 않을 수 있다. 1~2분 뒤 다시 시도한다.
- **VS Code 서버가 다른 VPC에 있을 때:** 클러스터 안의 임시 파드에서 확인한다. 파드 IP는 VPC CIDR 안에 있으므로 `inbound-cidrs`에 걸린다.

```
kubectl run alb-test -n llm-serving --rm -it --restart=Never --image=curlimages/curl:8.23.0 \
  -- curl -s http://${ALB_DNS}/health/liveliness
```

Istio 장 5절의 접근 로그(Telemetry)를 켠 상태라면, ALB를 거친 요청도 세션별로 같은 vLLM 파드로 가는지 볼 수 있다.

```
kubectl logs -n llm-serving -l app.kubernetes.io/name=litellm -c istio-proxy --tail=-1 \
  | grep -o 'session=chat-alb-0001 upstream=[^ ]*:8000' | sort | uniq -c
```

### 7. HTTPS로 바꾸기 (도메인과 ACM 인증서가 있을 때) ###

HTTP에서는 마스터 키가 담긴 `Authorization` 헤더가 VPC 안에서 평문으로 오간다. 운영에서는 HTTPS를 쓴다. ACM 인증서가 있으면 3절 Ingress의 애노테이션을 아래처럼 바꾼다.

```yaml
    alb.ingress.kubernetes.io/listen-ports: '[{"HTTPS": 443}]'
    alb.ingress.kubernetes.io/certificate-arn: arn:aws:acm:<리전>:<계정 ID>:certificate/<인증서 ID>
    alb.ingress.kubernetes.io/ssl-policy: ELBSecurityPolicy-TLS13-1-2-2021-06
```

- **도메인 연결:** 인증서의 도메인 이름은 Route 53에서 ALB DNS를 가리키는 별칭(alias) 레코드로 연결한다. internal ALB라면 프라이빗 호스팅 영역에 만든다.
- **ssl-policy:** 지정하지 않으면 `ELBSecurityPolicy-2016-08`이 쓰인다. TLS 1.2 이상만 허용하도록 명시한다.

### 8. 인터넷에 공개하려면 ###

이 장의 ALB는 VPC 안에서만 접근할 수 있다. 스킴을 `internet-facing`으로 바꾸면 인터넷의 누구나 이 엔드포인트에 요청을 보낼 수 있게 되고, 이를 막는 것은 LiteLLM 마스터 키뿐이다. 그래서 이 장에서는 공개 구성을 다루지 않는다. 공개가 필요하면 먼저 아래 조건을 갖춘다.

- **HTTPS:** 7절처럼 HTTPS 리스너만 연다.
- **접근 IP 제한:** `inbound-cidrs`를 `0.0.0.0/0`이 아니라 실제 클라이언트의 IP 대역으로 좁힌다.
- **앱별 키:** 마스터 키를 나눠 주지 않는다. Postgres를 붙여 앱마다 virtual key를 발급하고, 키별 요청 한도를 건다.
- **스킴 변경 영향:** 스킴을 바꾸면 ALB가 새로 만들어지고 DNS 이름이 바뀐다. 클라이언트 설정도 함께 바꿔야 한다.

### 9. 운영할 때 알아 둘 점 ###

- **비용:** ALB는 만들어진 시간과 처리량(LCU)으로 과금된다. 실습이 끝나면 11절에서 Ingress를 지운다.
- **LBC 업그레이드:** `helm upgrade`는 CRD를 갱신하지 않는다. 업그레이드 전에 차트 저장소의 `crds.yaml`을 먼저 적용한다.
- **IAM 정책 범위:** 기본 정책은 보안 그룹 규칙 변경(`ec2:AuthorizeSecurityGroupIngress` 등)을 모든 리소스에 허용한다. LBC 문서의 권장처럼 VPC ID나 클러스터 태그 조건으로 좁힐 수 있다.
- **Ingress 수정:** 애노테이션을 바꾸면 LBC가 ALB 설정을 바로 고친다. `scheme`과 `subnets`처럼 ALB를 새로 만들어야 하는 값은 DNS 이름이 바뀐다.

### 10. 문제 해결 ###

| 증상 | 확인할 것 |
|---|---|
| ADDRESS가 비어 있다 | `kubectl describe ingress litellm -n llm-serving`의 Events와 `kubectl logs -n kube-system deploy/aws-load-balancer-controller`를 본다. `AccessDenied`면 1.2~1.3절의 IAM 설정을 확인한다. |
| 서브넷 관련 오류가 난다 | `alb.ingress.kubernetes.io/subnets` 값이 쉼표로 구분된 서브넷 ID 2개(서로 다른 AZ)인지 본다. |
| 타깃이 `unhealthy`다 | 헬스 체크 경로가 `/health/liveliness`인지, LiteLLM 파드가 Ready인지 본다. 노드 보안 그룹에 ALB 보안 그룹에서 오는 4000 포트 규칙이 생겼는지도 본다. |
| LBC 로그에 `expected exactly one securityGroup tagged with kubernetes.io/cluster/...`가 나온다 | 파드가 쓰는 네트워크 인터페이스에 클러스터 태그가 붙은 보안 그룹이 여러 개 있다. 태그가 붙은 보안 그룹이 하나만 남도록 정리한다. |
| 롤링 업데이트 중 502가 난다 | `kubectl get pods -o wide`의 READINESS GATES가 `1/1`인지 본다. `<none>`이면 4절 순서대로 파드를 다시 만든다. |
| 긴 요청에서 504가 난다 | 3절의 속성 확인 명령으로 `idle_timeout.timeout_seconds`가 600인지 본다. |
| curl이 연결되지 않는다 | internal ALB라 VPC 밖에서는 접근할 수 없다. 클라이언트 IP가 `inbound-cidrs`(VPC CIDR) 안에 있는지 본다. |
| 파드를 만들 때 웹훅 오류가 난다 | 컨트롤 플레인이 노드의 9443 포트(LBC 웹훅)에 닿는지 노드 보안 그룹을 확인한다. |

### 11. 정리 ###

Ingress를 먼저 지운다. LBC가 ALB, 타깃 그룹, 보안 그룹을 함께 지운다. LBC를 먼저 지우면 이 AWS 리소스들이 남는다.

```
kubectl delete ingress litellm -n llm-serving
kubectl label namespace llm-serving elbv2.k8s.aws/pod-readiness-gate-inject-

# ALB가 지워졌는지 확인 (아무것도 나오지 않으면 삭제된 것)
aws elbv2 describe-load-balancers --query "LoadBalancers[?DNSName=='${ALB_DNS}'].LoadBalancerName" --output text

helm uninstall aws-load-balancer-controller -n kube-system
eksctl delete iamserviceaccount --cluster "${CLUSTER_NAME}" --namespace kube-system --name aws-load-balancer-controller
aws iam delete-policy --policy-arn "${LBC_POLICY_ARN}"
```

## 참고자료 ##

* [AWS Load Balancer Controller, Installation Guide](https://kubernetes-sigs.github.io/aws-load-balancer-controller/latest/deploy/installation/)
* [AWS Load Balancer Controller, Ingress annotations](https://kubernetes-sigs.github.io/aws-load-balancer-controller/latest/guide/ingress/annotations/)
* [AWS Load Balancer Controller, Pod Readiness Gate](https://kubernetes-sigs.github.io/aws-load-balancer-controller/latest/deploy/pod_readiness_gate/)
* [Application Load Balancer 속성](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/application-load-balancers.html#load-balancer-attributes)
* [ALB 타깃 그룹 속성 (deregistration delay)](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-target-groups.html#target-group-attributes)
* [ALB 보안 정책 (ssl-policy)](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/describe-ssl-policies.html)
