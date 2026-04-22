
## [LeaderWorkerSet](https://lws.sigs.k8s.io/docs/overview/) ##

LLM 서빙이 본격적으로 프로덕션에 들어오면서, 기존 Kubernetes 워크로드 리소스만으로는 다루기 어려운 영역이 생겼다. 대표적인 사례가 모델을 여러 노드에 쪼개서 서빙해야 하는 경우다. Llama 3.1 405B, DeepSeek V3 같은 초대형 모델은 단일 노드의 GPU 메모리로는 감당이 안 된다. H100 80GB 8장짜리 노드(640 GiB) 두 대를 묶어 텐서 병렬(TP)과 파이프라인 병렬(PP)을 조합해야 겨우 돌아간다.

메모리 계산
```
1 B  = 10⁹  = 1,000,000,000         (10억)
405B = 405 × 10⁹ = 405,000,000,000  (4,050억 파라미터)
```
FP16 가중치 메모리:
* 2 bytes × 405 × 10⁹ = 810 × 10⁹ bytes = 810 GB ≈ 754 GiB

여기에 KV 캐시와 활성화 메모리까지 더하면 실서빙에는 800 GiB 이상이 필요하다. H100 노드 한 대(640 GiB)로는 가중치조차 올릴 수 없고, 두 대를 묶어야 비로소 여유가 생긴다.

### 기존 워크로드 리소스의 한계 ###
Deployment와 StatefulSet은 파드에 문제가 생기면 해당 파드만 재시작한다. 단일 파드로 완결되는 워크로드에는 자연스러운 동작이지만, 멀티노드 GPU 서빙에는 맞지 않는다.
TP+PP 구조에서는 여러 파드가 NCCL로 서로 통신하며 하나의 모델을 함께 서빙한다. 파드 하나가 죽으면 NCCL 통신 그룹 전체가 깨지기 때문에, 그룹 내 모든 파드를 함께 재시작해야 한다. Deployment와 StatefulSet은 이 "그룹 단위 생명주기"라는 개념을 다루지 못한다.  
이 공백을 메우기 위해 Kubernetes SIG가 새롭게 도입한 리소스가 LeaderWorkerSet(LWS) 이다. 이 글에서는 LWS가 해결하려는 문제, 내부 구조, 실제 사용 방법을 살펴본다.

### 왜 기존 리소스로는 부족한가 ###
Deployment와 StatefulSet은 모두 "각 Pod가 동등한 복제본"이라는 전제 위에서 설계됐다. 하지만 분산 추론은 역할이 비대칭이다.

* Leader: 외부 요청을 받고, 텐서/파이프라인 병렬 연산을 조정한다. 보통 rank 0.
* Worker: 모델 가중치의 일부만 들고 있으며, Leader의 지시를 받아 연산한다.

이 구조를 Deployment로 표현하려고 하면 몇 가지 불편한 지점이 생긴다.

`1. 부분 실패 처리가 어렵다`

Worker 하나가 OOM으로 죽었다고 가정해 보자. Deployment는 그 Pod 하나만 재시작하지만, 분산 추론에서는 Worker 하나가 빠진 상태의 그룹은 무용지물이다. 새로 뜬 Worker는 기존 그룹의 통신 채널에 합류하지 못하고, Leader 또한 재초기화가 필요하다. 사실상 그룹 전체를 같이 재시작해야 정상 복구된다.

`2. 스케일링 단위가 맞지 않는다`

replicas: 3을 원하는 상황에서 Deployment의 replicas는 "Pod 3개"를 의미한다. 하지만 분산 추론에서는 "Leader+Worker 묶음 3세트"가 필요하다. 이 단위 차이를 HPA나 Karpenter에 그대로 맞추기 어렵다.

`3. 피어 디스커버리를 직접 구현해야 한다`

Leader 주소를 Worker가 어떻게 알 것인가? 각자의 rank는 어떻게 배정할 것인가? StatefulSet의 안정적 네트워크 ID로 엇비슷하게 흉내낼 수는 있지만, init container와 사이드카, 별도 ConfigMap을 얹어가며 조립해야 한다. 결과물은 보통 fragile하다.

이런 요구사항을 손쉽게  풀어낸 것이 바로 LWS다.

### LWS의 그룹 ###
LWS의 가장 중요한 개념은 Group 이다. 한 Group은 Leader 1개와 Worker N개로 구성되며, LWS의 replicas는 Pod 수가 아니라 Group 수를 의미한다.
```
LeaderWorkerSet (replicas: 2)
├── Group 0
│   ├── Leader Pod  (rank 0)
│   ├── Worker Pod  (rank 1)
│   ├── Worker Pod  (rank 2)
│   └── Worker Pod  (rank 3)
└── Group 1
    ├── Leader Pod  (rank 0)
    ├── Worker Pod  (rank 1)
    ├── Worker Pod  (rank 2)
    └── Worker Pod  (rank 3)
```
Group 하나가 독립된 추론 단위로, 외부에서 보면 Group 하나가 Deployment의 파드 하나처럼 동작한다. 트래픽은 리더 파드로만 들어가고, 그 안에서 워커들과 협력해 응답을 만들어 낸다.


### 해결된 문제들 ###
이 아키텍처 덕분에 자연스럽게 해결되는 문제들이 있다.

`그룹 단위 생명주기`

RecreateGroupOnPodRestart 정책을 쓰면, Group 내 어떤 Pod가 죽어도 그 Group 전체가 재시작된다. 일부만 살아있는 애매한 상태가 남지 않는다.

`자동 환경변수 주입`

LWS 컨트롤러는 각 Pod에 필요한 환경변수를 자동으로 주입해 준다.

* LWS_LEADER_ADDRESS: 같은 Group의 Leader Pod DNS 이름
* LWS_WORKER_INDEX: Group 내 rank (0 = leader)
* LWS_GROUP_SIZE: Group 내 Pod 총 수
애플리케이션은 이 값을 읽어서 torchrun의 --master_addr, --rank 같은 파라미터로 넘기면 된다.

`Headless Service 자동 생성`

Group마다 Headless Service가 자동으로 만들어지고, Pod들은 안정적인 DNS 이름으로 서로를 찾는다. 별도로 Service YAML을 쓸 필요가 없다.

`순차 기동`

startupPolicy: LeaderCreated로 설정하면 Leader가 먼저 Ready된 뒤에 Worker가 동작한다. AI 인퍼런스 분산 환경에서는 master가 먼저 대기 상태여야 worker가 동작할 수 있기 때문이다. 

### YAML 예시 ###
vLLM으로 Llama 3.1 405B를 2노드에 걸쳐 서빙하는 예시다.
```
apiVersion: leaderworkerset.x-k8s.io/v1
kind: LeaderWorkerSet
metadata:
  name: vllm-llama-405b
  namespace: llm-serving
spec:
  replicas: 1

  # 업데이트 전략: 한 번에 하나씩 교체, 추가 그룹 생성 안 함
  rolloutStrategy:
    type: RollingUpdate
    rollingUpdateConfiguration:
      maxUnavailable: 1
      maxSurge: 0

  leaderWorkerTemplate:
    size: 2                                    # Leader 1 + Worker 1
    restartPolicy: RecreateGroupOnPodRestart

    # 서브그룹 배치 정책: 같은 zone에 묶어서 배치
    subGroupPolicy:
      subGroupSize: 2
      type: TopologyAwarePlacement
      topology:
        - topologyKey: topology.kubernetes.io/zone

    leaderTemplate:
      metadata:
        labels:
          role: leader
      spec:
        containers:
          - name: vllm-leader
            image: vllm/vllm-openai:latest
            command: ["/bin/bash", "-c"]
            args:
              - |
                bash /vllm-workspace/ray_init.sh leader \
                  --ray_cluster_size=$LWS_GROUP_SIZE;
                python -m vllm.entrypoints.openai.api_server \
                  --model=meta-llama/Llama-3.1-405B-Instruct \
                  --tensor-parallel-size=8 \
                  --pipeline-parallel-size=2 \
                  --distributed-executor-backend=ray
            resources:
              limits:
                nvidia.com/gpu: 8
            ports:
              - containerPort: 8000

    workerTemplate:
      spec:
        containers:
          - name: vllm-worker
            image: vllm/vllm-openai:latest
            command: ["/bin/bash", "-c"]
            args:
              - |
                bash /vllm-workspace/ray_init.sh worker \
                  --ray_address=$LWS_LEADER_ADDRESS
            resources:
              limits:
                nvidia.com/gpu: 8
```
주목할 포인트는 Leader와 Worker의 command가 다르다는 점으로, Leader는 Ray 클러스터를 시작하고 vLLM 서버를 띄우고, Worker는 Leader가 띄운 Ray에 join만 한다. 이 비대칭 구조가 LWS가 필요한 이유 그 자체다.

### Topology-aware 스케줄링 ###
```
spec:
  leaderWorkerTemplate:
    subGroupPolicy:
      subGroupSize: 2
      type: TopologyAwarePlacement
      topology:
        - topologyKey: topology.kubernetes.io/zone
```
이 설정으로 같은 Group의 Pod들은 가능한 한 같은 AZ에, 이상적으로는 같은 rack이나 같은 EFA fabric에 배치된다. AWS UltraCluster 같은 고성능 네트워크 환경에서 특히 효과가 크다.

### 롤링 업데이트 ###
일반 Deployment의 롤링 업데이트는 "Pod 하나씩 교체"다. LWS는 "Group 하나씩 교체"다.

```
spec:
  rolloutStrategy:
    type: RollingUpdate
    rollingUpdateConfiguration:
      maxUnavailable: 1
      maxSurge: 0
```
Group 0이 완전히 새 버전으로 교체된 다음 Group 1로 넘어간다. Group 내 Pod들은 동시에 교체되므로 중간에 "절반만 새 버전인 Group" 같은 이상한 상태가 안 생긴다.


### 설치하기 ###
LWS는 별도 컨트롤러로 동작한다.
```
kubectl apply --server-side -f \
  https://github.com/kubernetes-sigs/lws/releases/latest/download/manifests.yaml
```
이 한 줄로 CRD와 컨트롤러가 모두 설치되며 EKS, GKE, AKS 에서 동일하게 사용가능하다.

주요 프레임워크 지원 현황:

* vLLM: 공식 가이드에 LWS 예제 수록
* Ray: 분산 추론용 Ray 클러스터를 LWS로 표현 가능
* TensorRT-LLM: Triton Inference Server와 조합해 사용
* SGLang: 멀티노드 서빙 문서에 LWS 언급

### LWS가 적합한 경우 ###

* 70B 이상 대형 모델의 멀티노드 분산 추론
* 텐서 병렬 + 파이프라인 병렬 조합이 필요한 경우
* Ray, MPI 같은 head-worker 구조 시스템 위에서 도는 워크로드
* KubeRay 대신 더 가볍게 Ray를 묶고 싶은 경우

### 마치며 ###
LWS는 "대형 LLM 분산 추론을 선언적으로 표현하고 싶다"는 요구에서 출발해, 기존 StatefulSet + Service + Init Container 조합으로 어거지로 만들던 구성을 간결하게 바꿀 수 있다. 특히 vLLM 커뮤니티가 LWS를 표준 배포 방식으로 밀고 있어서, 생태계 호환성 측면에서도 이점이 있다.

```
독자가 "왜 필요한가 → 무엇이 다른가 → 어떻게 쓰는가 → 언제 쓰나"로 자연스럽게 따라갈 수 있게 구성
```

## 레퍼런스 ##
* [vllm lws](https://docs.vllm.ai/en/latest/deployment/frameworks/lws/)
