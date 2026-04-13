## 멀티 노드 인프런스 최적화 ##
단일 노드에 담기 어려운 대규모 모델을 여러 노드에 걸쳐 서빙할 때, 노드 간 통신 오버헤드를 최소화하고 GPU 활용률을 최대화하는 것이 핵심이다. 모델 크기, 지연시간 요구사항, 처리량 목표에 따라 병렬화 전략과 최적화 기법의 조합이 달라진다. 일반적으로 노드 내부는 TP, 노드 간은 PP를 사용하는 하이브리드 구성을 적용한다.

### 텐서 병렬리즘 (Tensor Parallelism, TP) ###

* 레이어의 가중치 텐서를 행또는 열 방향으로 분할해서 여러 GPU에 나눔
* 레이어 내부에서 GPU 간 통신(all-reduce)이 발생하므로 노드 내부(NVLink 등 고속 인터커넥트)에서 주로 사용

### 파이프라인 병렬리즘 (Pipeline Parallelism, PP) ###

* 모델의 레이어를 순차적으로 여러 노드에 배치
* 노드 간 통신량이 TP보다 적어서 멀티노드에 적합. 다만 파이프라인 버블(유휴 시간)이 발생하므로, 마이크로배칭으로 이를 줄이는 것이 핵심.

### 실무에서 쓰이는 도구들 ###
* vLLM: PagedAttention + 텐서/파이프라인 병렬리즘 지원
* TensorRT-LLM: NVIDIA 최적화, 멀티노드 지원


### TP + PP 하이브리드 구성 시 고려사항 ###
* TP degree 선택: 노드 내 GPU 수(보통 8)를 넘지 않도록 설정. NVLink 대역폭(예: A100 NVSwitch 600GB/s)을 넘어 노드 간 TP를 걸면 all-reduce 지연이 급격히 증가.
* PP stage 분할: 레이어를 균등 분할하는 것이 기본이지만, 임베딩 레이어나 LM head가 있는 첫/마지막 스테이지는 연산량이 다르므로 불균형이 발생한다. vLLM이나 TensorRT-LLM에서는 이를 자동 밸런싱하는 옵션이 있다.
* 마이크로배치 수: PP 버블을 줄이려면 마이크로배치 수를 PP 스테이지 수의 4배 이상으로 잡는 것이 경험적으로 효과적이다. 다만 인퍼런스에서는 배치 크기가 제한적이라 트레이닝만큼 효과를 보기 어려울 수 있다.

### 노드 간 통신 최적화 ###
* NCCL 튜닝: NCCL_ALGO, NCCL_PROTO 환경변수로 통신 알고리즘/프로토콜 선택 가능. InfiniBand 환경에서는 NCCL_IB_HCA로 HCA 디바이스를 명시적으로 지정하면 성능이 개선된다.
* PP 에서의 비동기 전송: 스테이지 간 activation 전달을 비동기로 처리하면 computation과 communication을 오버랩할 수 있다.
* KV Cache 관리: 멀티노드에서 continuous batching을 쓸 때, 각 노드의 KV cache 상태를 동기화하는 오버헤드가 존재한다. vLLM의 PagedAttention이 이 부분에서 메모리 효율을 크게 높여준다.

### 추가로 고려할 만한 기법들 ###
* Speculative Decoding: 작은 draft 모델로 여러 토큰을 먼저 생성하고 큰 모델로 검증. 멀티노드 환경에서 draft 모델을 별도 노드에 배치하면 지연시간을 줄일 수 있다.
* Expert Parallelism: MoE 모델의 경우 expert를 노드별로 분산 배치하는 전략이 TP/PP와 별도로 필요하다.
* Disaggregated Prefill/Decode: prefill(프롬프트 처리)과 decode(토큰 생성)를 별도 노드 그룹에서 처리하는 아키텍처. 처리량과 지연시간을 독립적으로 스케일링할 수 있다.


### 인퍼런스 특화 PP 버블 문제 ###
트레이닝과 달리 인퍼런스에서는 PP 버블 문제가 다른 양상을 보이게 된다.

* Prefill 단계: 입력 시퀀스 전체를 한 번에 처리하므로 마이크로배칭이 가능하고, 트레이닝과 유사하게 버블을 줄일 수 있다.
* Decode 단계: 토큰 하나씩 순차 생성하므로 마이크로배칭 효과가 제한적이다. 이 단계에서 PP는 본질적으로 스테이지 수만큼의 지연시간 패널티가 발생한다.
Prefill 노드 그룹은 PP로 처리량을 높이고, Decode 노드 그룹은 TP 위주로 지연시간을 최소화하는 식으로 분리할 수 있다.

### KV Cache 동기화의 실제 병목 ###
멀티노드 continuous batching에서 KV cache 관련 실질적 이슈는:

* PP 구성에서는 각 스테이지가 자기 레이어의 KV cache만 관리하므로 노드 간 KV cache 동기화는 불필요하다. 다만 스케줄링 메타데이터(어떤 요청이 활성 상태인지, 어떤 슬롯이 비었는지)는 동기화해야 한다.
* Disaggregated 구성에서는 prefill 노드에서 생성된 KV cache를 decode 노드로 전송해야 하는데, 이 전송량이 상당하다. 예를 들어 Llama 70B에서 시퀀스 길이 2048이면 KV cache가 수 GB에 달할 수 있다. RDMA 기반 전송이 사실상 필수이다.

### Expert Parallelism 심화 ###
MoE 모델에서 EP를 적용할 때의 핵심 트레이드오프:

* All-to-All 통신: 각 토큰이 라우팅된 expert가 있는 노드로 이동해야 하므로 all-to-all 통신이 발생한다. expert 수가 많을수록(DeepSeek-V3는 256개) 통신 패턴이 복잡해진다.
* Expert 로드 밸런싱: 특정 expert에 토큰이 몰리면 해당 노드가 병목이 된다. 트레이닝 시 auxiliary loss로 밸런싱을 유도하지만, 인퍼런스에서는 입력 분포에 따라 불균형이 발생할 수 있다.
* EP + TP + PP 3중 병렬화: 초대형 MoE 모델에서는 세 가지를 모두 조합해야 한다. 예를 들어 노드 내 8 GPU 중 4개씩 2그룹으로 TP를 걸고, expert를 노드 간 EP로 분산하고, attention 레이어는 PP로 나누는 식이다.

### 배포 고려사항 ###
* Health check와 failover:  
멀티노드 서빙에서 한 노드가 죽으면 전체 파이프라인이 멈추게 된다. Kubernetes 환경에서 pod 단위 재시작보다는 전체 replica 단위 관리가 필요하다. Kubernetes 기본 기능만으로는 이런 "그룹 단위 lifecycle 관리"가 안 되기 때문에, [LeaderWorkerSet](https://lws.sigs.k8s.io/docs/overview/) 같은 커스텀 리소스나 별도의 오케스트레이션 로직이 필요하다.
![](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/images/multi-node-inf-3.png)

* 웜업:   
첫 요청 시 CUDA 커널 컴파일, NCCL 초기화 등으로 지연이 크게 발생한다. 배포 후 더미 요청으로 웜업하는 것이 필수이다.   
* 네트워크 토폴로지 인식:  
클라우드 환경에서 노드 간 대역폭이 균일하지 않을 수 있기 때문에 placement group(AWS)이나 compact placement policy(GCP)로 노드를 물리적으로 가까이 배치해야 한다.


## [LWS](https://lws.sigs.k8s.io/docs/overview/) ##
LeaderWorkerSet는 Kubernetes SIG에서 관리하는 커스텀 리소스로, pod 그룹을 하나의 복제 단위로 관리하기 위해 만들어 졌다.

### 구조 ###
```
LeaderWorkerSet (replicas: 2, size: 3)
├── Worker Group 0 (= Replica 0)
│   ├── Leader Pod (pod-0)      ← 요청 진입점, 워커 조율
│   ├── Worker Pod (pod-0-1)
│   └── Worker Pod (pod-0-2)
└── Worker Group 1 (= Replica 1)
    ├── Leader Pod (pod-1)
    ├── Worker Pod (pod-1-1)
    └── Worker Pod (pod-1-2)
```
* replicas: Worker Group의 수 (수평 스케일링 단위)
* size: 한 그룹 내 pod 수 (leader + workers)

### 핵심 기능들 ###
* All-or-nothing restart
* 그룹 단위 롤링 업데이트
* 토폴로지 인식 배치 - 같은 그룹의 pod들을 같은 노드/서브넷/존에 배치해서 GPU 간 통신 지연을 최소화.
* 듀얼 템플릿 - Leader pod과 Worker pod에 서로 다른 스펙을 지정 가능.
* HPA 연동

### 실제 vLLM 배포 예시 ###
```
apiVersion: leaderworkerset.x-k8s.io/v1
kind: LeaderWorkerSet
metadata:
  name: vllm-llama70b
spec:
  replicas: 2                    # 2개의 독립적인 서빙 그룹
  leaderWorkerTemplate:
    size: 3                      # 그룹당 3개 pod (leader 1 + worker 2)
    restartPolicy: RecreateGroupOnPodRestart  # ← all-or-nothing
    leaderTemplate:
      spec:
        containers:
        - name: vllm-leader
          image: vllm/vllm-openai:latest
          args:
          - --tensor-parallel-size=24  # 3노드 × 8GPU
          - --model=meta-llama/Llama-3.1-70B-Instruct
          resources:
            limits:
              nvidia.com/gpu: 8
    workerTemplate:
      spec:
        containers:
        - name: vllm-worker
          image: vllm/vllm-openai:latest
          resources:
            limits:
              nvidia.com/gpu: 8
```
